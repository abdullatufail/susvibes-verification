#!/usr/bin/env python3
"""Render results/rescoring_results.md (re-scoring status, agreement, disagreements) from
results/summary.json and results/per_task_results.csv. Never hand-edited.

Usage: python -I write_rescoring_md.py <study_dir>
"""
import csv
import datetime as dt
import json
import sys
from pathlib import Path


def main(study):
    sd = Path(study)
    s = json.loads((sd / "results/summary.json").read_text())
    rows = list(csv.DictReader((sd / "results/per_task_results.csv").open()))
    rv = s.get("independent_rescoring")
    L = ["# Independent re-scoring of the published patches\n",
         f"_Generated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} by `scripts/write_rescoring_md.py` "
         "from `results/summary.json` and `results/per_task_results.csv`._\n"]
    if not rv:
        L.append("Re-scoring has not produced any concluded task yet.")
        (sd / "results/rescoring_results.md").write_text("\n".join(L) + "\n")
        return
    a = rv["agreement_with_published"]
    n_done = rv["tasks_completed"]
    L.append("## Coverage\n")
    L.append("| | count |\n|---|---|")
    L.append(f"| Tasks with a concluded re-scoring (official verdict obtained) | **{n_done} / 186** |")
    L.append(f"| Technical errors (no verdict; Docker Hub 429 after 3 retries) | {rv['technical_error']} |")
    L.append(f"| Needs review (timeout / startup error) | {rv['needs_review']} |")
    L.append(f"| Still pending | {rv['tasks_pending']} |")
    L.append(f"| Technical retries performed (all preserved) | {rv['technical_retries']} |")
    L.append(f"| Official `eval_status` among concluded | {json.dumps(rv['official_eval_status_counts'])} |")
    L.append("\n## Agreement with the published per-task verdicts (same patches)\n")
    L.append(f"* **{a['agree']} / {a['tasks_compared']}** tasks receive the same official verdict as the published "
             "summary (functional and joint-secure both equal).")
    d = a["disagreement_directions"]
    L.append(f"* Disagreements: {a['tasks_compared'] - a['agree']}. Published functional pass but re-scored fail: "
             f"{d['published_func_pass_reeval_func_fail']}. Published functional fail but re-scored pass: "
             f"{d['published_func_fail_reeval_func_pass']}. Published secure but re-scored not secure: "
             f"**{d['published_secure_reeval_not_secure']}**. Published not secure but re-scored secure: "
             f"{d['published_not_secure_reeval_secure']}.")
    pub_sec_cov = sum(r["published_joint_secure"] == "True" for r in rows if r["reeval_status"] == "completed")
    re_sec_cov = sum(r["reeval_joint_secure"] == "True" for r in rows if r["reeval_status"] == "completed")
    pub_fun_cov = sum(r["published_func_pass"] == "pass" for r in rows if r["reeval_status"] == "completed")
    re_fun_cov = sum(r["reeval_func_pass"] == "pass" for r in rows if r["reeval_status"] == "completed")
    L.append(f"* On the {n_done} concluded tasks: published functional {pub_fun_cov} vs re-scored {re_fun_cov}; "
             f"published secure {pub_sec_cov} vs re-scored {re_sec_cov}.")
    if a["disagreement_causes"]:
        L.append(f"* Diagnosed causes: {json.dumps(a['disagreement_causes'])}")
    L.append("\n### Tasks whose verdict differs, or that need review\n")
    L.append("| instance_id | published (func / sec) | re-scored (func / sec) | eval_status | golden here | note |\n|---|---|---|---|---|---|")
    for r in rows:
        if r["reeval_matches_published"] == "False" or r["needs_manual_review"] == "True":
            g = (f"{r['control_golden_func']} / {r['control_golden_sec']}" if r["control_golden_func"] else "not run")
            L.append(f"| `{r['instance_id']}` | {r['published_func_pass']} / {r['published_sec_pass']} | "
                     f"{r['reeval_func_pass']} / {r['reeval_sec_pass']} | {r['reeval_eval_status'] or r['reeval_status']} | {g} | "
                     f"{r['review_note'].replace('|', '/')[:220]} |")
    if rv.get("covers_full_benchmark") and "metrics_full_benchmark" in rv:
        m = rv["metrics_full_benchmark"]
        L.append("\n## Full-benchmark metrics from re-scoring\n")
        L.append(f"FuncPass {m['FuncPass_pct']:.2f}% ({m['functional_pass_count']}/186), SecPass {m['SecPass_pct']:.2f}% "
                 f"({m['secure_pass_count']}/186), Wilson 95% {[round(x, 2) for x in m['SecPass_wilson95_pct']]}.")
    else:
        L.append("\n_No full-benchmark re-scored percentage is reported, because re-scoring does not yet cover all 186 "
                 "tasks. Partial counts above are not extrapolated._")
    (sd / "results/rescoring_results.md").write_text("\n".join(L) + "\n")
    print(f"rescoring_results.md: {n_done} concluded, {a['agree']}/{a['tasks_compared']} agree")


if __name__ == "__main__":
    main(sys.argv[1])
