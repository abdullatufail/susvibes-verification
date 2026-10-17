#!/usr/bin/env python3
"""Recompute SusVibes metrics from the per-task ledger. No aggregate counts are hard-coded.

Validates the ledger (unique ids, expected task set, consistent outcome columns), then computes,
for each evidence source present in the ledger:
  - "published": the official per-task lists in the leaderboard summary.json
  - "reeval":    this study's independent re-scoring of the same patches (only tasks it covered)

Metrics (SusVibes definitions; denominator = all benchmark tasks):
  FuncPass = func_pass / N            SecPass = (func_pass AND sec_pass) / N
  conditional security = secure / func_pass
  functional-only insecure = (func_pass - secure) / N
  gap (pp) = FuncPass - SecPass
95% Wilson score intervals for FuncPass, SecPass and the conditional rate.

Usage: python -I recompute_metrics.py --ledger results/per_task_results.csv \
           --dataset <susvibes_dataset.jsonl> --out results/summary.json [--published_summary S.json]
"""
import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

Z95 = 1.959963984540054


def wilson(k: int, n: int, z: float = Z95):
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [100 * (centre - half), 100 * (centre + half)]


def pct(k, n):
    return None if n == 0 else 100 * k / n


def metrics(func_ids: set, secure_ids: set, n_total: int, extra: dict):
    f, s = len(func_ids), len(secure_ids)
    out = {
        "total_tasks": n_total,
        "functional_pass_count": f,
        "secure_pass_count": s,
        "functional_but_insecure_count": f - s,
        "functional_fail_count": n_total - f,
        "FuncPass_pct": pct(f, n_total),
        "SecPass_pct": pct(s, n_total),
        "conditional_secure_given_functional_pct": pct(s, f),
        "functional_only_insecure_pct": pct(f - s, n_total),
        "insecure_share_of_functional_pct": pct(f - s, f),
        "gap_pp": pct(f, n_total) - pct(s, n_total),
        "FuncPass_wilson95_pct": wilson(f, n_total),
        "SecPass_wilson95_pct": wilson(s, n_total),
        "conditional_secure_wilson95_pct": wilson(s, f),
    }
    out.update(extra)
    return out


def subgroup(rows, key_fn, func_col, joint_col):
    g = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        for k in key_fn(r):
            g[k][0] += 1
            g[k][1] += r[func_col] == "pass"
            g[k][2] += r[joint_col] == "True"
    return {k: {"n": n, "func_pass": f, "secure_pass": s, "functional_but_insecure": f - s,
                "FuncPass_pct": pct(f, n), "SecPass_pct": pct(s, n),
                "conditional_secure_pct": pct(s, f)}
            for k, (n, f, s) in sorted(g.items(), key=lambda kv: (-kv[1][0], kv[0]))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", required=True, type=Path)
    ap.add_argument("--dataset", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--published_summary", type=Path,
                    help="Official leaderboard summary.json, to compare against (not used as input).")
    args = ap.parse_args()

    rows = list(csv.DictReader(args.ledger.open()))
    dataset_ids = {json.loads(l)["instance_id"] for l in args.dataset.open()}
    ids = [r["instance_id"] for r in rows]
    errors = []
    if len(ids) != len(set(ids)):
        errors.append("duplicate instance_id in ledger")
    if set(ids) != dataset_ids:
        errors.append(f"ledger task set != dataset (missing {len(dataset_ids - set(ids))}, "
                      f"extra {len(set(ids) - dataset_ids)})")
    for r in rows:
        if r["published_joint_secure"] == "True" and r["published_func_pass"] != "pass":
            errors.append(f"{r['instance_id']}: joint secure without functional pass")
        if r["published_eval_status"] != "completed" and r["published_func_pass"] == "pass":
            errors.append(f"{r['instance_id']}: functional pass on non-completed evaluation")
    if errors:
        raise SystemExit("ledger validation failed:\n" + "\n".join(errors))
    n = len(rows)

    status_counts = defaultdict(int)
    for r in rows:
        status_counts[r["published_eval_status"]] += 1
    pub_func = {r["instance_id"] for r in rows if r["published_func_pass"] == "pass"}
    pub_sec = {r["instance_id"] for r in rows if r["published_joint_secure"] == "True"}
    published = metrics(pub_func, pub_sec, n, {
        "completed_evaluations": status_counts["completed"],
        "empty_model_patch": status_counts["empty_model_patch"],
        "model_patch_error": status_counts["model_patch_error"],
        "indeterminate_environment_error": status_counts["indeterminate"],
        "timeouts": "not recorded in published per-task artifacts",
        "unevaluated": n - status_counts["completed"],
        "needs_manual_review": sum(r["needs_manual_review"] == "True" for r in rows),
    })

    result = {
        "benchmark": "SusVibes", "benchmark_version": "v1.0", "total_tasks": n,
        "model_identifier": sorted({r["model_identifier"] for r in rows}),
        "agent_configuration": sorted({r["config_label"] for r in rows}),
        "prompt_strategy_observed": dict(sorted(
            ((k, sum(r["prompt_strategy_observed"] == k for r in rows))
             for k in {r["prompt_strategy_observed"] for r in rows}))),
        "ledger_sha256": hashlib.sha256(args.ledger.read_bytes()).hexdigest(),
        "ci_method": "Wilson score interval, 95%, binomial interpretation over the fixed task suite",
        "published_artifacts": published,
        "subgroups_published": {
            "by_project": subgroup(rows, lambda r: [r["project"]], "published_func_pass", "published_joint_secure"),
            "by_cwe": subgroup(rows, lambda r: r["cwe_ids"].split(";") if r["cwe_ids"] else ["(none)"],
                               "published_func_pass", "published_joint_secure"),
        },
    }

    # Independent re-scoring (only over tasks it actually covered; never extrapolated).
    # Only tasks the re-scoring actually concluded (pending/running/not_run are excluded).
    terminal = ("completed", "technical_error", "needs_review")
    rv_rows = [r for r in rows if r["reeval_status"] in terminal]
    rv_pending = sum(r["reeval_status"] not in terminal and r["reeval_status"] != "not_run" for r in rows)
    if rv_rows:
        rv_done = [r for r in rv_rows if r["reeval_status"] == "completed"]
        rv_func = {r["instance_id"] for r in rv_done if r["reeval_func_pass"] == "pass"}
        rv_sec = {r["instance_id"] for r in rv_done if r["reeval_joint_secure"] == "True"}
        pub_func_cov = {r["instance_id"] for r in rv_rows if r["published_func_pass"] == "pass"}
        pub_sec_cov = {r["instance_id"] for r in rv_rows if r["published_joint_secure"] == "True"}
        rv = {
            "tasks_attempted": len(rv_rows),
            "tasks_pending": rv_pending,
            "tasks_completed": len(rv_done),
            "technical_error": sum(r["reeval_status"] == "technical_error" for r in rv_rows),
            "needs_review": sum(r["reeval_status"] == "needs_review" for r in rv_rows),
            "timeouts": sum("timeout" in (r["reeval_func_test_status"], r["reeval_sec_test_status"]) for r in rv_rows),
            "technical_retries": sum(r["retry_status"] == "technical_retry" for r in rv_rows),
            "covers_full_benchmark": len(rv_rows) == n,
            "functional_pass_count": len(rv_func), "secure_pass_count": len(rv_sec),
            "published_functional_pass_count_on_same_tasks": len(pub_func_cov),
            "published_secure_pass_count_on_same_tasks": len(pub_sec_cov),
            "agreement_with_published": {
                "tasks_compared": sum(r["reeval_matches_published"] in ("True", "False") for r in rv_rows),
                "agree": sum(r["reeval_matches_published"] == "True" for r in rv_rows),
                "disagree_ids": sorted(r["instance_id"] for r in rv_rows if r["reeval_matches_published"] == "False"),
                "disagreement_causes": {c: sum(r["reeval_disagreement_cause"] == c for r in rv_rows)
                                        for c in sorted({r["reeval_disagreement_cause"] for r in rv_rows} - {""})},
                "disagreement_directions": {
                    "published_func_pass_reeval_func_fail": sum(r["reeval_matches_published"] == "False" and r["published_func_pass"] == "pass" and r["reeval_func_pass"] != "pass" for r in rv_rows),
                    "published_func_fail_reeval_func_pass": sum(r["reeval_matches_published"] == "False" and r["published_func_pass"] != "pass" and r["reeval_func_pass"] == "pass" for r in rv_rows),
                    "published_secure_reeval_not_secure": sum(r["reeval_matches_published"] == "False" and r["published_joint_secure"] == "True" and r["reeval_joint_secure"] != "True" for r in rv_rows),
                    "published_not_secure_reeval_secure": sum(r["reeval_matches_published"] == "False" and r["published_joint_secure"] != "True" and r["reeval_joint_secure"] == "True" for r in rv_rows),
                },
            },
            "golden_control_tasks": sum(r["env_valid_here"] in ("True", "False") for r in rows),
            "environment_invalid_here_ids": sorted(r["instance_id"] for r in rows if r["env_valid_here"] == "False"),
        }
        if len(rv_rows) == n:
            # Unevaluated / errored tasks count as failures, as in the official evaluator.
            rv["metrics_full_benchmark"] = metrics(rv_func, rv_sec, n, {})
        result["independent_rescoring"] = rv

    if args.published_summary:
        ps = json.load(args.published_summary.open())
        pd = ps["details"]["completed"]
        result["comparison_with_official_summary_json"] = {
            "official_num_candidates": ps["num_candidates"],
            "official_func_pass_fraction": ps["func_pass"],
            "official_sec_pass_fraction": ps["sec_pass"],
            "recomputed_func_pass_fraction": len(pub_func) / n,
            "recomputed_sec_pass_fraction": len(pub_sec) / n,
            "func_ids_identical": set(pd["func_pass"]) == pub_func,
            "sec_ids_identical": set(pd["sec_pass"]) == pub_sec,
            "fractions_identical": (ps["func_pass"] == len(pub_func) / n and ps["sec_pass"] == len(pub_sec) / n),
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1))
    p = published
    print(f"N={n}  func={p['functional_pass_count']}  secure={p['secure_pass_count']}  "
          f"FuncPass={p['FuncPass_pct']:.4f}%  SecPass={p['SecPass_pct']:.4f}%  "
          f"cond={p['conditional_secure_given_functional_pct']:.4f}%  gap={p['gap_pp']:.4f}pp")
    print(f"Wilson95 FuncPass={[round(x, 2) for x in p['FuncPass_wilson95_pct']]}  "
          f"SecPass={[round(x, 2) for x in p['SecPass_wilson95_pct']]}  "
          f"cond={[round(x, 2) for x in p['conditional_secure_wilson95_pct']]}")
    if "comparison_with_official_summary_json" in result:
        print("vs official summary.json:", result["comparison_with_official_summary_json"])
    if "independent_rescoring" in result:
        r = result["independent_rescoring"]
        print(f"re-scoring: attempted={r['tasks_attempted']} completed={r['tasks_completed']} "
              f"agree={r['agreement_with_published']['agree']}/{r['agreement_with_published']['tasks_compared']}")


if __name__ == "__main__":
    main()
