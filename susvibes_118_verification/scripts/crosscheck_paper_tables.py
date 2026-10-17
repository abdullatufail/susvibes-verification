#!/usr/bin/env python3
"""Cross-check published paper tables against leaderboard per-task artifacts.

- Table 3 (FuncPass/SecPass per framework x model) vs each submission's summary.json
- Table 5 (generic / self-selection / oracle on SWE-agent + Claude 4 Sonnet)
- Figure 5 (generic -> self-selection outcome transition matrix, % of all tasks)
All numbers are derived from per-task id lists, then rounded to 1 dp only for comparison.

Usage: python -I crosscheck_paper_tables.py <leaderboard_submissions_dir> <out_json>
"""
import json
import sys
from pathlib import Path

PAPER_TABLE3 = {  # PMLR v306 zhao26ax, Table 3 (FuncPass, SecPass)
    "claude-4-sonnet_swe-agent_default_2025-12-29": (57.0, 11.8),
    "kimi-k2_swe-agent_default_2025-12-29": (21.5, 5.4),
    "gemini-2.5-pro_swe-agent_default_2025-12-29": (18.3, 6.5),
    "gemini-3-pro_swe-agent_default_2025-12-29": (37.1, 12.9),
    "claude-4-sonnet_openhands_default_2025-12-29": (53.2, 11.8),
    "kimi-k2_openhands_default_2025-12-29": (36.0, 9.1),
    "gemini-2.5-pro_openhands_default_2025-12-29": (19.9, 8.1),
    "gemini-3-pro_openhands_default_2025-12-29": (50.5, 10.8),
    "claude-4-sonnet_claude-cli_default_2025-12-29": (41.4, 5.9),
    "kimi-k2_claude-cli_default_2025-12-29": (40.3, 8.6),
    "gemini-2.5-pro_claude-cli_default_2025-12-29": (12.9, 3.8),
    "gemini-3-pro_claude-cli_default_2025-12-29": (34.9, 6.5),
}
PAPER_TABLE5 = {"generic": (57.0, 11.8), "self-selection": (50.0, 14.5), "oracle": (55.4, 15.1)}
PAPER_FIG5 = [[38.7, 2.7, 1.6], [8.1, 32.3, 4.8], [3.2, 0.5, 8.1]]  # rows generic, cols self-sel
OUTCOMES = ["Incorrect", "Correct-Insecure", "Correct-Secure"]
STRAT_SUBS = {
    "generic": "claude-4-sonnet_swe-agent_default_2025-12-29",
    "self-selection": "claude-4-sonnet_swe-agent_custom-self-selection-prompt_2025-12-29",
    "oracle": "claude-4-sonnet_swe-agent_custom-oracle-prompt_2025-12-29",
}


def load_summary(subs: Path, name: str):
    p = subs / name / "trajectories" / f"{name}.summary.json"
    s = json.load(p.open())
    n = s["num_candidates"]
    f = set(s["details"]["completed"]["func_pass"])
    sec = set(s["details"]["completed"]["sec_pass"])
    assert sec <= f, f"{name}: sec_pass not subset of func_pass"
    return n, f, sec


def r1(x):
    return round(x + 1e-12, 1)


def main(subs_dir, out_path):
    subs = Path(subs_dir)
    out = {"table3": {}, "table5": {}, "figure5": {}}
    for name, (pf, ps) in PAPER_TABLE3.items():
        n, f, s = load_summary(subs, name)
        rf, rs = 100 * len(f) / n, 100 * len(s) / n
        out["table3"][name] = {"n": n, "func": len(f), "sec": len(s), "FuncPass": rf, "SecPass": rs,
                               "paper": [pf, ps], "match_1dp": [r1(rf) == pf, r1(rs) == ps]}
    outcome = {}
    for strat, name in STRAT_SUBS.items():
        n, f, s = load_summary(subs, name)
        rf, rs = 100 * len(f) / n, 100 * len(s) / n
        out["table5"][strat] = {"n": n, "func": len(f), "sec": len(s), "FuncPass": rf, "SecPass": rs,
                                "paper": list(PAPER_TABLE5[strat]),
                                "match_1dp": [r1(rf) == PAPER_TABLE5[strat][0], r1(rs) == PAPER_TABLE5[strat][1]]}
        trials = json.load((subs / name / "trajectories" / f"{name}.trials.json").open())
        ids = {t["instance_id"] for t in trials}
        outcome[strat] = {i: (2 if i in s else 1 if i in f else 0) for i in ids}
    g, ss = outcome["generic"], outcome["self-selection"]
    assert set(g) == set(ss)
    n = len(g)
    counts = [[0] * 3 for _ in range(3)]
    for i in g:
        counts[g[i]][ss[i]] += 1
    mat = [[100 * c / n for c in row] for row in counts]
    out["figure5"] = {"rows_generic_cols_selfselection": OUTCOMES, "counts": counts, "pct": mat,
                      "paper_pct": PAPER_FIG5,
                      "cells_matching_1dp": sum(r1(mat[a][b]) == PAPER_FIG5[a][b] for a in range(3) for b in range(3))}
    Path(out_path).write_text(json.dumps(out, indent=1))
    for k, v in out["table3"].items():
        print(f"T3 {k:52s} {v['func']:3d}/{v['n']} {v['sec']:3d}/{v['n']}  {v['FuncPass']:.2f} {v['SecPass']:.2f}  paper {v['paper']}  match {v['match_1dp']}")
    for k, v in out["table5"].items():
        print(f"T5 {k:15s} {v['func']}/{v['n']} {v['sec']}/{v['n']} {v['FuncPass']:.2f} {v['SecPass']:.2f} paper {v['paper']} match {v['match_1dp']}")
    print("F5 counts", counts)
    print("F5 pct   ", [[round(x, 1) for x in row] for row in mat], "paper", PAPER_FIG5,
          "cells match:", out["figure5"]["cells_matching_1dp"], "/ 9")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
