#!/usr/bin/env python3
"""Generate the data files and number macros used by report/verification_report.tex.

Every number in the PDF report comes from these generated files, which are derived from
results/summary.json, results/per_task_results.csv, results/paper_table_crosscheck.json,
results/original_run_cost_profile.json, the evaluation checkpoints and the pinned dataset.
Nothing is typed by hand.

Usage: python -I make_report_data.py <study_dir> <susvibes_dataset.jsonl>
"""
import csv
import json
import statistics
import sys
from pathlib import Path


def fmt(x, nd=1):
    return f"{x:.{nd}f}"


def main(study, dataset_path):
    sd = Path(study)
    out = sd / "report" / "data"
    out.mkdir(parents=True, exist_ok=True)
    s = json.loads((sd / "results/summary.json").read_text())
    rows = list(csv.DictReader((sd / "results/per_task_results.csv").open()))
    cross = json.loads((sd / "results/paper_table_crosscheck.json").read_text())
    cost = json.loads((sd / "results/original_run_cost_profile.json").read_text())
    ds = [json.loads(l) for l in open(dataset_path)]
    p = s["published_artifacts"]
    rv = s["independent_rescoring"]
    a = rv["agreement_with_published"]

    M = {}  # macro name -> value (LaTeX-safe text)
    M["NTasks"] = p["total_tasks"]
    M["FuncCount"] = p["functional_pass_count"]
    M["SecCount"] = p["secure_pass_count"]
    M["FuncInsecCount"] = p["functional_but_insecure_count"]
    M["FuncFailCount"] = p["functional_fail_count"]
    M["FuncPct"] = fmt(p["FuncPass_pct"], 2)
    M["SecPct"] = fmt(p["SecPass_pct"], 2)
    M["FuncPctExact"] = fmt(p["FuncPass_pct"], 4)
    M["SecPctExact"] = fmt(p["SecPass_pct"], 4)
    M["CondPct"] = fmt(p["conditional_secure_given_functional_pct"], 2)
    M["InsecSharePct"] = fmt(p["insecure_share_of_functional_pct"], 2)
    M["FuncOnlyInsecPct"] = fmt(p["functional_only_insecure_pct"], 2)
    M["GapPP"] = fmt(p["gap_pp"], 2)
    M["FuncCILo"], M["FuncCIHi"] = (fmt(x) for x in p["FuncPass_wilson95_pct"])
    M["SecCILo"], M["SecCIHi"] = (fmt(x) for x in p["SecPass_wilson95_pct"])
    M["CondCILo"], M["CondCIHi"] = (fmt(x) for x in p["conditional_secure_wilson95_pct"])
    for name, ci in (("Func", p["FuncPass_wilson95_pct"]), ("Sec", p["SecPass_wilson95_pct"])):
        M[f"{name}CIMid"] = fmt((ci[0] + ci[1]) / 2, 3)
        M[f"{name}CIHalf"] = fmt((ci[1] - ci[0]) / 2, 3)
    M["FuncCIPlus"] = fmt(p["FuncPass_wilson95_pct"][1] - p["FuncPass_pct"], 3)
    M["FuncCIMinus"] = fmt(p["FuncPass_pct"] - p["FuncPass_wilson95_pct"][0], 3)
    M["SecCIPlus"] = fmt(p["SecPass_wilson95_pct"][1] - p["SecPass_pct"], 3)
    M["SecCIMinus"] = fmt(p["SecPass_pct"] - p["SecPass_wilson95_pct"][0], 3)
    cmp_ = s["comparison_with_official_summary_json"]
    M["OfficialFuncFrac"] = repr(cmp_["official_func_pass_fraction"])
    M["OfficialSecFrac"] = repr(cmp_["official_sec_pass_fraction"])
    M["IdsIdentical"] = "yes" if (cmp_["func_ids_identical"] and cmp_["sec_ids_identical"]) else "no"
    M["LedgerSha"] = s["ledger_sha256"][:16]

    # Prompt screen and provenance
    M["GenericCount"] = sum(r["prompt_strategy_observed"].startswith("generic") for r in rows)
    M["GitCmdTasks"] = sum(int(r["git_history_commands_in_trajectory"]) > 0 for r in rows)
    M["SamePatchCount"] = sum(r["patch_identical_to_dec2025_record"] == "True" for r in rows)
    M["DiffPatchCount"] = len(rows) - M["SamePatchCount"]
    M["ExitSubmitted"] = sum(r["agent_exit_status"] == "submitted" for r in rows)
    M["ExitError"] = sum(r["agent_exit_status"] == "submitted (exit_error)" for r in rows)
    M["NProjects"] = len({r["project"] for r in rows})
    M["NCwes"] = len({c for r in rows for c in r["cwe_ids"].split(";") if c})

    # Paper cross-check
    t3 = cross["table3"]
    M["TThreeMatch"] = sum(all(v["match_1dp"]) for v in t3.values())
    M["TFiveMatch"] = sum(all(v["match_1dp"]) for v in cross["table5"].values())
    M["FFiveMatch"] = cross["figure5"]["cells_matching_1dp"]
    with (out / "table3.dat").open("w") as f:
        f.write("label func sec paperfunc papersec\n")
        names = {"swe-agent": "SA", "openhands": "OH", "claude-cli": "CC"}
        models = {"claude-4-sonnet": "C4S", "kimi-k2": "K2", "gemini-2.5-pro": "G25", "gemini-3-pro": "G3"}
        for k, v in t3.items():
            mdl, fw = k.split("_")[0], k.split("_")[1]
            f.write(f"{names[fw]}-{models[mdl]} {fmt(v['FuncPass'], 2)} {fmt(v['SecPass'], 2)} {v['paper'][0]} {v['paper'][1]}\n")
    with (out / "table3_rows.tex").open("w") as f:
        for k, v in t3.items():
            mdl, fw = k.split("_")[0], k.split("_")[1]
            ok = r"\checkmark" if all(v["match_1dp"]) else r"$\times$"
            f.write(f"{fw.replace('-', '{-}')} & {mdl} & {v['func']}/{v['n']} & {v['sec']}/{v['n']} & "
                    f"{fmt(v['FuncPass'], 2)} / {fmt(v['SecPass'], 2)} & {v['paper'][0]} / {v['paper'][1]} & {ok} \\\\\n")
    with (out / "table5_rows.tex").open("w") as f:
        for k, v in cross["table5"].items():
            ok = r"\checkmark" if all(v["match_1dp"]) else r"$\times$"
            f.write(f"{k.capitalize()} & {v['func']}/{v['n']} & {v['sec']}/{v['n']} & {fmt(v['FuncPass'], 2)} / "
                    f"{fmt(v['SecPass'], 2)} & {v['paper'][0]} / {v['paper'][1]} & {ok} \\\\\n")
    fc = cross["figure5"]["counts"]
    fp = cross["figure5"]["pct"]
    pp = cross["figure5"]["paper_pct"]
    lab = ["Incorrect", "Correct, insecure", "Correct, secure"]
    with (out / "fig5_rows.tex").open("w") as f:
        for i in range(3):
            cells = " & ".join(f"{fc[i][j]} ({fmt(fp[i][j])}\\%; paper {pp[i][j]})" for j in range(3))
            f.write(f"{lab[i]} & {cells} \\\\\n")

    # Outcome composition
    with (out / "outcome.dat").open("w") as f:
        f.write("cat count\n")
        f.write(f"secure {p['secure_pass_count']}\nfuncinsecure {p['functional_but_insecure_count']}\nfuncfail {p['functional_fail_count']}\n")

    # Re-scoring
    M["RvConcluded"] = rv["tasks_completed"]
    M["RvAttempted"] = rv["tasks_attempted"]
    M["RvTechErr"] = rv["technical_error"]
    M["RvPending"] = rv["tasks_pending"]
    M["RvRetries"] = rv["technical_retries"]
    M["RvAgree"] = a["agree"]
    M["RvCompared"] = a["tasks_compared"]
    M["RvDisagree"] = a["tasks_compared"] - a["agree"]
    M["RvAgreePct"] = fmt(100 * a["agree"] / a["tasks_compared"], 1)
    d = a["disagreement_directions"]
    M["RvPubFuncReFail"] = d["published_func_pass_reeval_func_fail"]
    M["RvPubFailReFunc"] = d["published_func_fail_reeval_func_pass"]
    M["RvPubSecReNot"] = d["published_secure_reeval_not_secure"]
    M["RvPubNotReSec"] = d["published_not_secure_reeval_secure"]
    done = [r for r in rows if r["reeval_status"] == "completed"]
    M["RvPubFunc"] = sum(r["published_func_pass"] == "pass" for r in done)
    M["RvReFunc"] = sum(r["reeval_func_pass"] == "pass" for r in done)
    M["RvPubSec"] = sum(r["published_joint_secure"] == "True" for r in done)
    M["RvReSec"] = sum(r["reeval_joint_secure"] == "True" for r in done)
    M["RvEvalCompleted"] = rv["official_eval_status_counts"].get("completed", 0)
    M["RvEvalPatchErr"] = rv["official_eval_status_counts"].get("model_patch_error", 0)
    M["RvGoldenTasks"] = rv["golden_control_tasks"]
    with (out / "rescoring.dat").open("w") as f:
        f.write("label published rescored\n")
        f.write(f"Functional {M['RvPubFunc']} {M['RvReFunc']}\nSecure {M['RvPubSec']} {M['RvReSec']}\n")
    with (out / "disagree_rows.tex").open("w") as f:
        for r in rows:
            if r["reeval_matches_published"] == "False" or r["needs_manual_review"] == "True":
                iid = r["instance_id"]
                short = iid.split("_")[0] + "\\_\\_" + iid.split("__")[1].split("_")[0] + "\\_" + iid.split("_")[-1][:7]
                short = iid.split("__")[0].replace("_", "\\_") + "/" + iid.split("__")[1].rsplit("_", 1)[0].replace("_", "\\_") + " " + iid.rsplit("_", 1)[1][:7]
                g = f"{r['control_golden_func']} / {r['control_golden_sec']}" if r["control_golden_func"] else "--"
                ev = (r["reeval_eval_status"] or r["reeval_status"]).replace("_", "\\_")
                f.write(f"\\texttt{{{short}}} & {r['published_func_pass']} / {r['published_sec_pass'].replace('_', ' ')} & "
                        f"{(r['reeval_func_pass'] or '--')} / {(r['reeval_sec_pass'] or '--').replace('_', ' ')} & {ev} & {g} \\\\\n")

    # Pilot controls
    eval_root = sd / "logs/eval"
    pilot_ids = json.loads((sd / "logs/pilot_instance_ids.json").read_text())

    def ck(name):
        pth = eval_root / name / "checkpoint.json"
        return json.loads(pth.read_text())["tasks"] if pth.exists() else {}
    G, V, E, R = ck("pilot_control_golden"), ck("pilot_control_vulnerable"), ck("pilot_control_empty"), ck("reeval_published_v1.0")
    pub = {r["instance_id"]: r for r in rows}

    def mark(x):
        return {True: r"\cmark", False: r"\xmark", None: "--"}[x]

    def vv(rec):
        if not rec:
            return "--"
        if rec.get("eval_status") == "empty_model_patch":
            return r"\textit{empty}"
        return f"{mark(rec.get('func_pass'))}\\,/\\,{mark(rec.get('sec_pass'))}"
    with (out / "pilot_rows.tex").open("w") as f:
        for iid in pilot_ids:
            r = pub[iid]
            proj = r["project"].split("/")[1]
            pf = r["published_func_pass"] == "pass"
            ps = r["published_joint_secure"] == "True"
            f.write(f"{proj} ({r['cwe_ids']}) & {vv(G.get(iid))} & {vv(V.get(iid))} & {vv(E.get(iid))} & {vv(R.get(iid))} & "
                    f"{mark(pf)}\\,/\\,{mark(ps if pf else False)} \\\\\n")
    M["PilotGoldenOK"] = sum(bool(G.get(i, {}).get("func_pass")) and bool(G.get(i, {}).get("sec_pass")) for i in pilot_ids)
    M["PilotVulnOK"] = sum(bool(V.get(i, {}).get("func_pass")) and V.get(i, {}).get("sec_pass") is False for i in pilot_ids)
    M["PilotEmptyOK"] = sum(E.get(i, {}).get("eval_status") == "empty_model_patch" for i in pilot_ids)

    # Count-based thresholds
    exp = [r["expected_pf"]["func"] for r in ds]
    assert all(isinstance(x, int) for x in exp)
    bins = [("0", lambda x: x == 0), ("1--5", lambda x: 1 <= x <= 5), ("6--20", lambda x: 6 <= x <= 20),
            ("21--100", lambda x: 21 <= x <= 100), ("$>$100", lambda x: x > 100)]
    with (out / "thresholds.dat").open("w") as f:
        f.write("bin count\n")
        for i, (b, fn) in enumerate(bins):
            f.write(f"{i} {sum(fn(x) for x in exp)}\n")
    M["ThreshZero"] = sum(x == 0 for x in exp)
    M["ThreshPos"] = sum(x > 0 for x in exp)
    M["ThreshMax"] = max(exp)

    # Cost profile
    costs = [float(r["cost_usd"]) for r in rows]
    M["CostTotal"] = fmt(cost["total_cost_usd"], 2)
    M["CostMean"] = fmt(cost["mean"], 2)
    M["CostMedian"] = fmt(cost["median"], 2)
    M["CostPNinety"] = fmt(cost["p90"], 2)
    M["CostMax"] = fmt(cost["max"], 2)
    M["CostPilot"] = fmt(cost["pilot5_cost_usd"], 2)
    M["TokIn"] = fmt(cost["tokens_sent_total"] / 1e6, 1)
    M["TokOut"] = fmt(cost["tokens_received_total"] / 1e6, 2)
    uncached = cost["tokens_sent_total"] * 3e-6 + cost["tokens_received_total"] * 15e-6
    M["CostUncached"] = f"{uncached:,.0f}".replace(",", "{,}")
    M["CostRatio"] = fmt(100 * cost["total_cost_usd"] / uncached, 1)
    M["TurnsMean"] = fmt(cost["turns_mean"], 1)
    edges = [0, 0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 7]
    with (out / "cost_hist.dat").open("w") as f:
        f.write("lo count\n")
        for lo, hi in zip(edges[:-1], edges[1:]):
            f.write(f"{lo} {sum(lo <= c < hi for c in costs)}\n")
        f.write(f"{edges[-1]} 0\n")  # closing point for pgfplots `ybar interval`
    assert sum(c >= edges[-1] for c in costs) == 0
    M["CostStdev"] = fmt(statistics.pstdev(costs), 2)

    # CWE subgroups (n >= 5)
    cw = s["subgroups_published"]["by_cwe"]
    with (out / "cwe.dat").open("w") as f:
        f.write("cwe n func sec insec fail\n")
        for k, v in cw.items():
            if v["n"] >= 5:
                f.write(f"{k} {v['n']} {v['func_pass']} {v['secure_pass']} {v['functional_but_insecure']} {v['n'] - v['func_pass']}\n")
    pr = s["subgroups_published"]["by_project"]
    with (out / "project_rows.tex").open("w") as f:
        for k, v in pr.items():
            if v["n"] >= 7:
                f.write(f"\\texttt{{{k}}} & {v['n']} & {v['func_pass']} & {v['secure_pass']} & {v['functional_but_insecure']} \\\\\n")

    with (out / "numbers.tex").open("w") as f:
        f.write("% Generated by scripts/make_report_data.py -- do not edit.\n")
        for k, v in M.items():
            assert k.isalpha(), k
            f.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")
    print(f"wrote {len(M)} macros and data files to {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
