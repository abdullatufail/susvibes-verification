#!/usr/bin/env python3
"""Render CHECKPOINT.md from the durable checkpoint files (never hand-edited).

Usage: python -I write_checkpoint_md.py <study_dir>
"""
import datetime as dt
import json
import shutil
import sys
from pathlib import Path


def main(study):
    sd = Path(study)
    e = sd / "logs/eval"
    main_ck = json.loads((e / "reeval_published_v1.0/checkpoint.json").read_text())
    tasks = main_ck["tasks"]
    by = {}
    for i, r in sorted(tasks.items()):
        by.setdefault(r["status"], []).append(i)
    batches = main_ck["batches"]
    last = batches[-1] if batches else None
    errs = [(i, r.get("note")) for i, r in sorted(tasks.items()) if r["status"] in ("technical_error", "needs_review")]
    retries = [i for i, r in sorted(tasks.items()) if r.get("attempt", 1) > 1]
    ctl = {}
    for d in sorted(e.glob("*control*")):
        ck = d / "checkpoint.json"
        if ck.exists():
            t = json.loads(ck.read_text())["tasks"]
            ctl[d.name] = {s: sum(r["status"] == s for r in t.values()) for s in {r["status"] for r in t.values()}}
    free = round(shutil.disk_usage("/").free / 1e9, 1)
    L = []
    L.append("# CHECKPOINT — experiment state\n")
    L.append(f"_Generated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} by `scripts/write_checkpoint_md.py` from `logs/eval/*/checkpoint.json`. Do not edit by hand._\n")
    L.append("## Experiments\n")
    L.append("| Experiment | State |\n|---|---|")
    L.append("| Stage 1 — artifact audit and recomputation (no Docker, no API) | **complete** |")
    L.append(f"| Stage 2 — evaluator pilot (5 tasks × golden / vulnerable / empty / published) | **complete** |")
    n_done = len(by.get("completed", []))
    L.append(f"| Stage 2b — re-score all 186 published patches (`reeval_published_v1.0`) | {n_done}/186 completed; "
             f"{len(by.get('pending', [])) + len(by.get('running', []))} pending/running; "
             f"{len(by.get('technical_error', []))} technical_error; {len(by.get('needs_review', []))} needs_review |")
    L.append(f"| Stage 2c — golden/vulnerable controls on disagreeing tasks | {json.dumps(ctl)} |")
    L.append("| Stage 3/4 — fresh SWE-agent + Claude 4 Sonnet run | **not started**. No API budget was established and no model credentials were provisioned. Requires the unpublished `susvibes_eval` SWE-agent config. See `reproduction_report.md` §8 |")
    L.append("\n## Re-scoring run `reeval_published_v1.0`\n")
    m = main_ck["meta"]
    L.append(f"* predictions: `{Path(m['predictions_path']).name}` sha256 `{m['predictions_sha256']}`")
    L.append(f"* dataset sha256 `{m['dataset_sha256']}`; harness commit `{m['harness_commit']}` (tag v1.0)")
    if last:
        L.append(f"* latest batch: **{last['batch']}** finished {last['finished_at']}: {last['instance_ids']}")
    L.append(f"* batches recorded: {len(batches)} (pilot tasks ran as single-task batches 1–5)")
    L.append(f"* disk free now: {free} GB (one task image is about 1.8 GB and is removed after each task)")
    L.append("* API expenditure: **$0.00**. No model was invoked. Only published patches and reference controls were evaluated.")
    L.append(f"* technical retries: {len(retries)} {retries if retries else ''}")
    L.append("\n### Errors / needs review\n")
    L.extend([f"* `{i}`: {n}" for i, n in errs] or ["* none"])
    L.append("\n### Completed task IDs\n")
    L.append("<details><summary>" + f"{n_done} completed" + "</summary>\n\n" + "\n".join(f"- {i}" for i in by.get("completed", [])) + "\n</details>")
    L.append("\n### Pending task IDs\n")
    pend = by.get("pending", []) + by.get("running", [])
    L.append("<details><summary>" + f"{len(pend)} pending/running" + "</summary>\n\n" + "\n".join(f"- {i}" for i in pend) + "\n</details>")
    L.append("""
## How to resume without duplicating work

1. Start Docker if it is not running: `dockerd > /tmp/dockerd.log 2>&1 &`. Check it with `docker info`.
2. Make sure the pinned harness exists at `/home/user/sources/susvibes-v1.0` (tag `v1.0`) with its venv `/home/user/sources/sv-venv` (see README §Reproduction).
3. Live run output is written **outside the repo** to `$LIVE` (default `/home/user/runs/eval/`), and `scripts/rebuild_results.sh` copies it into `logs/eval/`. If `$LIVE` was lost, for example in a fresh container, seed it from the committed copy: `mkdir -p /home/user/runs/eval && cp -a logs/eval/reeval_published_v1.0 /home/user/runs/eval/`.
4. Run `scripts/run_full_reeval.sh` with the same arguments. `run_eval_batches.py` reloads `logs/eval/reeval_published_v1.0/checkpoint.json`. It refuses to continue if the predictions, dataset, run_id or harness commit differ. It skips every `completed` task whose saved `report.json` checksum and patch hash still validate. It re-queues a task left in `running` state, which is treated as interrupted. It does **not** retry `technical_error`/`needs_review` tasks unless `--retry_errors` is given. With that flag the original record is kept under `previous_attempts`.
5. Finish the 429-exhausted tasks with `scripts/run_full_reeval.sh --retry_errors`. Then run `scripts/run_disagreement_controls.sh` and `scripts/rebuild_results.sh`, and regenerate this file with `python -I scripts/write_checkpoint_md.py .`.
""")
    (sd / "CHECKPOINT.md").write_text("\n".join(L) + "\n")
    print(f"CHECKPOINT.md: completed={n_done} statuses={ {k: len(v) for k, v in by.items()} }")


if __name__ == "__main__":
    main(sys.argv[1])
