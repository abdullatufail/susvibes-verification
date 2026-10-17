#!/usr/bin/env python3
"""Checkpointed, disk-conscious wrapper around the official SusVibes evaluator.

It does NOT change evaluation semantics. For each task it invokes the supported entry point

    python -m susvibes.eval.core --run_id <run_id> --strategy <label> --max_workers 1 \
        --predictions_path <one-prediction.jsonl> --instance_ids '["<instance_id>"]'

inside the pinned harness checkout, then copies the per-task evidence (report.json,
run_instance.log, test_outputs/*) into this study's logs directory (gzip-compressed), removes
the task's eval image (pulled by this experiment) and updates a durable checkpoint.

Tasks are processed strictly sequentially (one task, one image at a time), grouped into logical
batches for reporting. A task already marked `completed` is skipped only after its saved
evidence is re-validated (report present, checksum matches, same patch hash).

Usage:
  python -I run_eval_batches.py --predictions P.jsonl --run_id RID --harness_root DIR \
      --harness_python PY --out_dir DIR [--strategy generic] [--batch_size 5] \
      [--instance_ids_file F] [--max_tasks N] [--keep_images] [--retry_errors]
"""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

TERMINAL = {"completed", "technical_error", "needs_review"}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def disk_free_gb(path="/"):
    return round(shutil.disk_usage(path).free / 1e9, 2)


def docker_df():
    try:
        out = subprocess.run(["docker", "system", "df", "--format", "{{.Type}}={{.Size}}"],
                             capture_output=True, text=True, timeout=120).stdout
        return dict(line.split("=", 1) for line in out.strip().splitlines() if "=" in line)
    except Exception as e:  # noqa: BLE001 - diagnostics only
        return {"error": str(e)}


def atomic_write_json(path: Path, obj):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=True))
    os.replace(tmp, path)


def load_checkpoint(path: Path, meta: dict):
    if path.exists():
        ck = json.loads(path.read_text())
        for k in ("run_id", "predictions_sha256", "dataset_sha256", "harness_commit"):
            if ck["meta"].get(k) != meta.get(k):
                sys.exit(f"Checkpoint {path} was made with a different {k}; refusing to mix runs.")
        return ck
    return {"meta": meta, "tasks": {}, "batches": []}


def validate_saved(rec: dict, task_dir: Path, patch_sha: str) -> bool:
    rp = task_dir / "report.json"
    return (rec.get("status") == "completed" and rp.exists()
            and rec.get("report_sha256") == sha256_file(rp)
            and rec.get("patch_sha256") == patch_sha)


def classify(report: dict | None):
    """Map an official v1.0 report onto this study's task status. Verdicts are taken verbatim."""
    if report is None:
        return "technical_error", "no report.json produced"
    es = report.get("eval_status")
    run = report.get("run", {})
    if es == "indeterminate":
        return "technical_error", "official eval_status=indeterminate"
    if es in ("empty_model_patch", "model_patch_error"):
        return "completed", None
    if es == "completed":
        bad = [k for k in ("func", "sec") if run.get(k, {}).get("test_status") not in (None, "completed")]
        if bad:
            return "needs_review", f"test_status not completed for {bad}: " + \
                ", ".join(f"{k}={run[k].get('test_status')}" for k in bad)
        return "completed", None
    return "needs_review", f"unknown eval_status {es!r}"


def remove_task_image(image_name: str, log):
    """Remove only the named eval image of this task (pulled by this experiment) and dangling
    layers. Never touches other images."""
    r = subprocess.run(["docker", "image", "inspect", image_name, "--format", "{{.Id}}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        log(f"  image {image_name} not present; nothing to remove")
        return
    subprocess.run(["docker", "rmi", "-f", image_name], capture_output=True, text=True)
    subprocess.run(["docker", "image", "prune", "-f"], capture_output=True, text=True)
    subprocess.run(["docker", "builder", "prune", "-f"], capture_output=True, text=True)
    log(f"  removed {image_name}")


def evaluate_prediction(pred, run_id, args, harness_root, tdir, tmp_dir, log):
    """Evaluate one prediction with the official entry point; copy evidence to tdir; return the
    record fields. The official report is taken verbatim."""
    iid = pred["instance_id"]
    model_key = pred["model_name_or_path"].replace("/", "__")
    hdir = harness_root / "logs/eval" / run_id / args.strategy / model_key / iid
    # Remove any stale harness report for this run/task so the evaluator cannot reuse it.
    if hdir.exists():
        shutil.rmtree(hdir)
    one = tmp_dir / f"{iid}.{model_key}.jsonl"
    one.write_text(json.dumps(pred) + "\n")
    cmd = [args.harness_python, "-m", "susvibes.eval.core", "--run_id", run_id,
           "--strategy", args.strategy, "--max_workers", "1",
           "--predictions_path", str(one), "--instance_ids", json.dumps([iid])]
    t0 = time.time()
    try:
        cp = subprocess.run(cmd, cwd=harness_root, capture_output=True, text=True,
                            timeout=args.task_timeout)
        rc, stdout, stderr = cp.returncode, cp.stdout, cp.stderr
    except subprocess.TimeoutExpired as e:
        rc, stdout, stderr = "wrapper_timeout", str(e.stdout or ""), str(e.stderr or "")
    dur = round(time.time() - t0, 1)
    one.unlink(missing_ok=True)

    if tdir.exists():
        shutil.rmtree(tdir)
    tdir.mkdir(parents=True)
    (tdir / "harness_stdout_stderr.txt.gz").write_bytes(
        gzip.compress(f"$ {' '.join(cmd)}\nreturncode={rc}\n--- stdout\n{stdout}\n--- stderr\n{stderr}".encode()))
    report = None
    if (hdir / "report.json").exists():
        shutil.copy2(hdir / "report.json", tdir / "report.json")
        report = json.loads((tdir / "report.json").read_text())
    for rel in ["run_instance.log", "test_outputs/func.txt", "test_outputs/sec.txt"]:
        src = hdir / rel
        if src.exists():
            (tdir / (rel.replace("/", "__") + ".gz")).write_bytes(gzip.compress(src.read_bytes()))
    status, note = classify(report)
    if rc != 0 and report is None:
        note = f"harness returncode={rc}; " + (note or "")
    run = (report or {}).get("run", {})
    return {
        "status": status, "note": note, "finished_at": now(), "duration_s": dur,
        "harness_returncode": rc, "run_id": run_id,
        "patch_sha256": sha256_str(pred["model_patch"]),
        "eval_status": (report or {}).get("eval_status"),
        "func_pass": run.get("func", {}).get("pass"),
        "func_test_status": run.get("func", {}).get("test_status"),
        "sec_pass": run.get("sec", {}).get("pass"),
        "sec_test_status": run.get("sec", {}).get("test_status"),
        "report_sha256": sha256_file(tdir / "report.json") if report else None,
        "evidence_files": {p.name: sha256_file(p) for p in sorted(tdir.iterdir())},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--predictions", required=True, type=Path)
    ap.add_argument("--run_id", required=True)
    ap.add_argument("--strategy", default="generic",
                    help="Output-path label passed to the official evaluator (no effect on scoring "
                         "except for self-selection).")
    ap.add_argument("--harness_root", required=True, type=Path)
    ap.add_argument("--harness_python", required=True)
    ap.add_argument("--out_dir", required=True, type=Path)
    ap.add_argument("--batch_size", type=int, default=5)
    ap.add_argument("--instance_ids_file", type=Path)
    ap.add_argument("--max_tasks", type=int, default=None)
    ap.add_argument("--keep_images", action="store_true")
    ap.add_argument("--retry_errors", action="store_true",
                    help="Re-run tasks whose status is technical_error/needs_review (original "
                         "record is preserved under `previous_attempts`).")
    ap.add_argument("--task_timeout", type=int, default=2 * 1800 + 1800)
    ap.add_argument("--control", action="append", default=[], metavar="NAME=PATH",
                    help="Per-task control predictions evaluated on the same cached image before "
                         "the main prediction (e.g. golden=predictions/control_golden.jsonl).")
    args = ap.parse_args()

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "run.log"

    def log(msg):
        line = f"[{now()}] {msg}"
        print(line, flush=True)
        with log_path.open("a") as f:
            f.write(line + "\n")

    harness_root = args.harness_root.resolve()
    dataset_path = harness_root / "datasets/default/susvibes_dataset.jsonl"
    dataset = {json.loads(l)["instance_id"]: json.loads(l) for l in dataset_path.open()}
    preds = [json.loads(l) for l in args.predictions.open()]
    pred_by_id = {p["instance_id"]: p for p in preds}
    assert len(pred_by_id) == len(preds), "duplicate instance_id in predictions"
    models = {p["model_name_or_path"] for p in preds}
    assert len(models) == 1, f"one model per predictions file, got {models}"
    model = models.pop()

    ids = sorted(pred_by_id)
    if args.instance_ids_file:
        wanted = json.loads(args.instance_ids_file.read_text())
        ids = [i for i in wanted if i in pred_by_id]
    unknown = [i for i in ids if i not in dataset]
    assert not unknown, f"instances not in pinned dataset: {unknown[:3]}"

    harness_commit = subprocess.run(["git", "-C", str(harness_root), "rev-parse", "HEAD"],
                                    capture_output=True, text=True).stdout.strip()
    meta = {
        "run_id": args.run_id, "strategy_label": args.strategy, "model_name_or_path": model,
        "predictions_path": str(args.predictions), "predictions_sha256": sha256_file(args.predictions),
        "dataset_path": str(dataset_path), "dataset_sha256": sha256_file(dataset_path),
        "harness_root": str(harness_root), "harness_commit": harness_commit,
        "target_instance_ids": ids, "created_at": now(),
    }
    ck_path = out_dir / "checkpoint.json"
    ck = load_checkpoint(ck_path, meta)
    ck["meta"]["target_instance_ids"] = sorted(set(ck["meta"]["target_instance_ids"]) | set(ids))
    for i in ids:
        ck["tasks"].setdefault(i, {"status": "pending"})
    atomic_write_json(ck_path, ck)

    controls = {}
    for spec in args.control:
        name, path = spec.split("=", 1)
        controls[name] = {json.loads(l)["instance_id"]: json.loads(l) for l in Path(path).open()}
    ck["meta"].setdefault("controls", {}).update({n: sha256_file(Path(p)) for n, p in
                                                  (c.split("=", 1) for c in args.control)})
    tmp_dir = out_dir / "_tmp"
    tmp_dir.mkdir(exist_ok=True)

    todo = []
    for i in ids:
        rec = ck["tasks"][i]
        psha = sha256_str(pred_by_id[i]["model_patch"])
        if rec.get("status") == "completed":
            if validate_saved(rec, out_dir / i, psha):
                continue
            log(f"{i}: saved record failed validation; re-queuing")
            rec["status"] = "pending"
        elif rec.get("status") in ("technical_error", "needs_review") and not args.retry_errors:
            continue
        todo.append(i)
    if args.max_tasks is not None:
        todo = todo[:args.max_tasks]
    log(f"run_id={args.run_id} model={model} targets={len(ids)} todo={len(todo)} "
        f"free={disk_free_gb()}GB")

    batch_no = len(ck["batches"])
    for b0 in range(0, len(todo), args.batch_size):
        batch_ids = todo[b0:b0 + args.batch_size]
        batch_no += 1
        b = {"batch": batch_no, "instance_ids": batch_ids, "started_at": now(),
             "disk_free_gb_before": disk_free_gb(), "docker_df_before": docker_df()}
        log(f"=== batch {batch_no}: {len(batch_ids)} tasks")
        for i in batch_ids:
            rec = ck["tasks"][i]
            if rec.get("status") in ("technical_error", "needs_review"):
                prev = {k: v for k, v in rec.items() if k != "previous_attempts"}
                rec.setdefault("previous_attempts", []).append(prev)
            attempt = len(rec.get("previous_attempts", [])) + 1
            pred = pred_by_id[i]
            psha = sha256_str(pred["model_patch"])
            rec.update({"status": "running", "attempt": attempt, "started_at": now(),
                        "patch_sha256": psha, "image_name": dataset[i]["image_name"],
                        "disk_free_gb_before": disk_free_gb()})
            atomic_write_json(ck_path, ck)

            for cname, cpreds in controls.items():
                if i in cpreds:
                    log(f"{i}: control {cname}")
                    crec = evaluate_prediction(cpreds[i], f"{args.run_id}__control-{cname}", args,
                                               harness_root, out_dir / "controls" / cname / i, tmp_dir, log)
                    rec.setdefault("controls", {})[cname] = crec
                    atomic_write_json(ck_path, ck)
            log(f"{i}: evaluating (attempt {attempt})")
            rec.update(evaluate_prediction(pred, args.run_id, args, harness_root, out_dir / i, tmp_dir, log))
            if not args.keep_images:
                remove_task_image(dataset[i]["image_name"], log)
            rec["disk_free_gb_after"] = disk_free_gb()
            atomic_write_json(ck_path, ck)
            ctl = " ".join(f"[{k}: func={v.get('func_pass')} sec={v.get('sec_pass')}]"
                           for k, v in rec.get("controls", {}).items())
            log(f"{i}: {rec['status']} eval_status={rec['eval_status']} func={rec['func_pass']} "
                f"sec={rec['sec_pass']} ({rec['duration_s']}s) {rec['note'] or ''} {ctl}")

        recs = [ck["tasks"][i] for i in batch_ids]
        b.update({
            "finished_at": now(),
            "completed": sum(r["status"] == "completed" for r in recs),
            "technical_error": sum(r["status"] == "technical_error" for r in recs),
            "needs_review": sum(r["status"] == "needs_review" for r in recs),
            "func_pass": sum(bool(r.get("func_pass")) for r in recs),
            "sec_pass_joint": sum(bool(r.get("func_pass")) and bool(r.get("sec_pass")) for r in recs),
            "retries_in_batch": sum(r.get("attempt", 1) > 1 for r in recs),
            "disk_free_gb_after": disk_free_gb(), "docker_df_after": docker_df(),
            "api_cost_usd": 0.0,
        })
        ck["batches"].append(b)
        atomic_write_json(ck_path, ck)
        b["checkpoint_sha256"] = sha256_file(ck_path)
        with (out_dir / "batches.jsonl").open("a") as f:
            f.write(json.dumps(b, sort_keys=True) + "\n")
        log(f"=== batch {batch_no} done: {json.dumps({k: b[k] for k in ('completed', 'technical_error', 'needs_review', 'func_pass', 'sec_pass_joint', 'disk_free_gb_after')})}")

    shutil.rmtree(tmp_dir, ignore_errors=True)
    counts = {}
    for i in ids:
        counts[ck["tasks"][i]["status"]] = counts.get(ck["tasks"][i]["status"], 0) + 1
    log(f"done. status counts over {len(ids)} targets: {counts}")


if __name__ == "__main__":
    main()
