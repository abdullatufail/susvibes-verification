#!/usr/bin/env python3
"""Build the authoritative per-task ledger (results/per_task_results.csv).

Inputs (all read-only):
  --dataset        pinned SusVibes v1.0 dataset jsonl (task set, project, CWE/CVE metadata)
  --submission     leaderboard submission dir for claude-4-sonnet_swe-agent_default_2025-12-29
  --dec2025_digest logs/artifact_audit/v0.0_dec2025_record_digest.json (patch sha256 of the
                   historical v0.0 trials, leaderboard commit 4db597e), used only to flag whether
                   each v1.0 patch is byte-identical to the Dec-2025 one
  --screen         output of screen_trajectories.py (prompt variant / git-history flags)
  --reeval_ckpt    optional checkpoint.json from run_eval_batches.py (independent re-scoring)
  --control        optional NAME=checkpoint.json (repeatable) for golden / vulnerable controls run on
                   this machine; several checkpoints may share a NAME (pilot + disagreement runs)

The published outcome columns come from the official per-task lists in the submission's
summary.json (details.completed.func_pass / sec_pass and the error lists); nothing is copied from
aggregate percentages.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

SUB = "claude-4-sonnet_swe-agent_default_2025-12-29"
FIELDS = [
    "instance_id", "project", "benchmark_version", "cwe_ids", "cve_id",
    "agent_status", "agent_exit_status", "prompt_strategy_observed",
    "published_eval_status", "published_func_pass", "published_sec_pass", "published_joint_secure",
    "published_failure_category",
    "reeval_status", "reeval_eval_status", "reeval_func_pass", "reeval_sec_pass",
    "reeval_raw_func_run", "reeval_raw_sec_run",
    "reeval_joint_secure", "reeval_func_test_status", "reeval_sec_test_status",
    "reeval_attempts", "reeval_matches_published",
    "control_golden_func", "control_golden_sec", "control_vulnerable_func", "control_vulnerable_sec",
    "env_valid_here", "reeval_disagreement_cause",
    "retry_status", "patch_identical_to_dec2025_record", "git_history_commands_in_trajectory",
    "needs_manual_review", "review_note",
    "patch_artifact", "patch_sha256", "trajectory_artifact",
    "cost_usd", "tokens_sent", "tokens_received", "num_turns",
    "run_id", "model_identifier", "config_label",
]


def yn(b):
    return "" if b is None else ("pass" if b else "fail")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, type=Path)
    ap.add_argument("--submission", required=True, type=Path)
    ap.add_argument("--dec2025_digest", required=True, type=Path)
    ap.add_argument("--screen", required=True, type=Path)
    ap.add_argument("--reeval_ckpt", type=Path)
    ap.add_argument("--control", action="append", default=[], metavar="NAME=PATH")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    dataset = {json.loads(l)["instance_id"]: json.loads(l) for l in args.dataset.open()}
    tdir = args.submission / "trajectories"
    trials = json.load((tdir / f"{SUB}.trials.json").open())
    summary = json.load((tdir / f"{SUB}.summary.json").open())
    dec = json.load(args.dec2025_digest.open())["dec2025_patch_sha256"]
    screen = json.load(args.screen.open())
    reeval = json.load(args.reeval_ckpt.open())["tasks"] if args.reeval_ckpt and args.reeval_ckpt.exists() else {}

    controls = {}
    for spec in args.control:
        name, path = spec.split("=", 1)
        if Path(path).exists():
            for iid, rec in json.load(open(path))["tasks"].items():
                if rec.get("status") in ("completed", "needs_review", "technical_error"):
                    controls.setdefault(name, {})[iid] = rec

    d = summary["details"]
    func = set(d["completed"]["func_pass"])
    sec = set(d["completed"]["sec_pass"])
    empty, perr, indet = set(d["empty_model_patch"]), set(d["model_patch_error"]), set(d["indeterminate"])
    rh = set(d.get("reward_hack_removed", []))

    rows = []
    for t in sorted(trials, key=lambda t: t["instance_id"]):
        iid = t["instance_id"]
        rec = dataset[iid]
        md = t["run_metadata"]
        if iid in empty:
            es = "empty_model_patch"
        elif iid in perr:
            es = "model_patch_error"
        elif iid in indet:
            es = "indeterminate"
        else:
            es = "completed"  # summary lists only exceptions; every other submitted task completed
        pf, ps = iid in func, iid in sec
        if es != "completed":
            cat = {"empty_model_patch": "empty_patch", "model_patch_error": "patch_apply_error",
                   "indeterminate": "environment_error"}[es]
        elif not pf:
            cat = "functional"
        elif not ps:
            cat = "security"
        else:
            cat = "none"
        sc = screen.get(iid, {})
        strat = "generic_safety_reminder" if sc.get("prompt_has_generic_safety_reminder") else "base"
        if sc.get("prompt_has_cwe_hint"):
            strat += "+cwe_hint"
        rv = reeval.get(iid, {})
        # Official semantics (v1.0 get_summary): a task counts as functional / secure only when its
        # eval_status is "completed"; empty or unappliable patches count as failures even if one of
        # the two runs happened to pass. Raw per-run values are kept in separate columns.
        rv_func = rv_joint = None
        if rv.get("status") == "completed":
            if rv.get("eval_status") == "completed":
                rv_func = bool(rv.get("func_pass"))
                rv_joint = rv_func and bool(rv.get("sec_pass"))
            else:
                rv_func = rv_joint = False
        matches = ""
        if rv.get("status") == "completed":
            matches = str(rv_func == pf and rv_joint == ps)
        cg = controls.get("golden", {}).get(iid, {})
        cv = controls.get("vulnerable", {}).get(iid, {})
        env_valid = ""
        if cg.get("eval_status") == "completed":
            env_valid = str(bool(cg.get("func_pass")) and bool(cg.get("sec_pass")))
        cause = ""
        if matches == "False":
            cause = ("environment: golden patch also fails here" if env_valid == "False" else
                     "unexplained: golden patch passes here" if env_valid == "True" else
                     "undiagnosed: no golden control run")
        notes, review = [], False
        if ps and not pf:
            notes.append("sec_pass without func_pass in published summary"); review = True
        if es != "completed":
            notes.append(f"published eval_status={es}"); review = True
        if rv.get("status") == "completed" and rv.get("eval_status") not in (None, "completed"):
            notes.append(f"re-eval official eval_status={rv.get('eval_status')} (raw func run pass={rv.get('func_pass')})")
            review = True
        if rv.get("status") in ("technical_error", "needs_review"):
            notes.append(f"re-eval {rv['status']}: {rv.get('note')}"); review = True
        if matches == "False":
            notes.append(f"re-eval verdict differs from published ({cause})"); review = True
        if iid in rh:
            notes.append("listed as reward_hack_removed"); review = True
        if sc.get("git_history_commands"):
            notes.append("trajectory ran git-history command(s): " + " | ".join(sc["git_history_commands"]))
        rows.append({
            "instance_id": iid, "project": rec["project"], "benchmark_version": "v1.0",
            "cwe_ids": ";".join(rec["cwe_ids"]), "cve_id": rec.get("cve_id") or "",
            "agent_status": md.get("subtype"), "agent_exit_status": md.get("exit_status"),
            "prompt_strategy_observed": strat,
            # The published summary lists sec_pass only within func_pass, so the standalone security
            # verdict of a functionally failing task is not recorded there.
            "published_eval_status": es,
            "published_func_pass": yn(pf) if es == "completed" else "not_evaluated",
            "published_sec_pass": ("not_evaluated" if es != "completed" else
                                   yn(ps) if pf else "not_recorded"),
            "published_joint_secure": str(pf and ps), "published_failure_category": cat,
            "reeval_status": rv.get("status", "not_run"), "reeval_eval_status": rv.get("eval_status") or "",
            "reeval_func_pass": yn(rv_func),
            "reeval_sec_pass": ("" if rv_func is None else "not_evaluated" if rv.get("eval_status") != "completed"
                                else yn(rv.get("sec_pass")) if rv_func else "not_counted"),
            "reeval_raw_func_run": yn(rv.get("func_pass")), "reeval_raw_sec_run": yn(rv.get("sec_pass")),
            "reeval_joint_secure": "" if rv_joint is None else str(rv_joint),
            "reeval_func_test_status": rv.get("func_test_status") or "",
            "reeval_sec_test_status": rv.get("sec_test_status") or "",
            "reeval_attempts": rv.get("attempt", 0), "reeval_matches_published": matches,
            "control_golden_func": yn(cg.get("func_pass")), "control_golden_sec": yn(cg.get("sec_pass")),
            "control_vulnerable_func": yn(cv.get("func_pass")), "control_vulnerable_sec": yn(cv.get("sec_pass")),
            "env_valid_here": env_valid, "reeval_disagreement_cause": cause,
            "retry_status": "technical_retry" if rv.get("attempt", 1) > 1 else "none",
            "patch_identical_to_dec2025_record": str(dec.get(iid) == hashlib.sha256(t["model_patch"].encode()).hexdigest()),
            "git_history_commands_in_trajectory": len(sc.get("git_history_commands", [])),
            "needs_manual_review": str(review), "review_note": "; ".join(notes),
            "patch_artifact": f"leaderboard:{SUB}/trajectories/{SUB}.trials.json#{iid}",
            "patch_sha256": hashlib.sha256(t["model_patch"].encode()).hexdigest(),
            "trajectory_artifact": f"leaderboard:{SUB}/trajectories/{t['messages']}",
            "cost_usd": md.get("total_cost_usd"), "tokens_sent": md.get("tokens_sent"),
            "tokens_received": md.get("tokens_received"), "num_turns": md.get("num_turns"),
            "run_id": "susvibes_eval__claude-sonnet-4-20250514__t-0.00__p-1.00__c-0.00___susvibes.run_evaluation_generic_instances",
            "model_identifier": t["model_name_or_path"], "config_label": "SWE-agent default (generic security reminder)",
        })
    assert len(rows) == len({r["instance_id"] for r in rows}) == len(dataset)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
