#!/usr/bin/env python3
"""Render the chart images for the co-advisor slides (Canva deck).

Reads only generated/committed data: report/data/*.dat, results/*.json, results/per_task_results.csv,
and the leaderboard repository's git history (for the version-history chart). Writes PNGs to
slides/assets/. Palette = the validated report palette on the slide template's beige surface.

Usage: <venv-python> make_slide_assets.py <study_dir> <leaderboard_repo>
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

BLUE, RED, AMBER = "#4F81BD", "#C0504D", "#D99A2B"
INK, MUTED, GRID = "#2E3B30", "#6B7768", "#D9D6CE"
SURFACE = "#F1EFE9"
GREEN = "#4B6450"

for f in font_manager.findSystemFonts():
    if "Inter" in f:
        font_manager.fontManager.addfont(f)
plt.rcParams.update({
    "font.family": "Inter", "font.size": 15, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
    "xtick.color": INK, "ytick.color": INK, "text.color": INK, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.axisbelow": True, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "legend.frameon": False, "hatch.color": "#8A8A84",
})


def read_dat(p):
    rows = [l.split() for l in Path(p).read_text().splitlines() if l.strip()]
    head = rows[0]
    return [dict(zip(head, r)) for r in rows[1:]]


def macros(p):
    out = {}
    for line in Path(p).read_text().splitlines():
        if line.startswith("\\newcommand"):
            k = line.split("{\\", 1)[1].split("}", 1)[0]
            v = line.rsplit("{", 1)[1].rstrip("}")
            out[k] = v
    return out


def save(fig, out, name):
    fig.savefig(out / name, dpi=200, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print("wrote", name)


def main(study, leaderboard):
    sd = Path(study)
    out = sd / "slides" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    D = sd / "report" / "data"
    M = macros(D / "numbers.tex")
    N = int(M["NTasks"])

    # 1. Version history of the headline figure (from leaderboard git history + paper versions)
    sub = "public/submissions/claude-4-sonnet_swe-agent_default_2025-12-29/submission.json"
    pts = [("arXiv v1\nDec 2025", 61.0, 10.5, "v0.0 · 200 tasks")]
    for c, label in (("a050d9d", "Leaderboard\nJun 19 2026"), ("8571041", "Leaderboard\nJun 20 2026")):
        js = json.loads(subprocess.run(["git", "-C", leaderboard, "show", f"{c}:{sub}"],
                                       capture_output=True, text=True, check=True).stdout)
        r = js["results"]["python"]
        pts.append((label, r["func_pass_1"], r["sec_pass_1"], f"{js['methodology']['susvibes_version']}"))
    pts.append(("PMLR / arXiv v3–v4\nAug 2026", 57.0, 11.8, "v1.0 · 186 tasks"))
    fig, ax = plt.subplots(figsize=(11, 5.2))
    xs = range(len(pts))
    ax.plot(xs, [p[1] for p in pts], "-o", color=BLUE, lw=2, ms=10, label="FuncPass (%)")
    ax.plot(xs, [p[2] for p in pts], "-o", color=RED, lw=2, ms=10, label="SecPass (%)")
    for i, p in enumerate(pts):
        ax.annotate(f"{p[1]:.1f}", (i, p[1]), textcoords="offset points", xytext=(0, 12), ha="center", fontsize=14)
        ax.annotate(f"{p[2]:.1f}", (i, p[2]), textcoords="offset points", xytext=(0, 12), ha="center", fontsize=14)
    ax.axvspan(-0.4, 1.5, color="#E4E1D8", zorder=0)
    ax.text(0.55, 40, "SusVibes v0.0\n200 tasks", ha="center", color=MUTED, fontsize=14)
    ax.text(2.5, 40, "SusVibes v1.0\n186 tasks", ha="center", color=MUTED, fontsize=14)
    ax.set_xticks(list(xs), [p[0] for p in pts], fontsize=13)
    ax.set_ylim(0, 72)
    ax.set_xlim(-0.4, len(pts) - 0.6)
    ax.set_ylabel("Tasks solved (%)")
    ax.legend(loc="upper right", ncols=2)
    save(fig, out, "history.png")

    # 2. Outcome composition + FuncPass/SecPass with Wilson CIs
    sec, ins, fail = int(M["SecCount"]), int(M["FuncInsecCount"]), int(M["FuncFailCount"])
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(15, 5.4), gridspec_kw={"width_ratios": [1.5, 1]})
    a1.barh([0], [sec], color=RED, edgecolor=SURFACE, lw=2, label="Correct & secure")
    a1.barh([0], [ins], left=[sec], color=AMBER, edgecolor=SURFACE, lw=2, label="Correct but insecure")
    a1.barh([0], [fail], left=[sec + ins], color=SURFACE, hatch="///", edgecolor="#8A8A84", lw=1, label="Incorrect")
    for x, v, c in ((sec / 2, sec, "white"), (sec + ins / 2, ins, "white"), (sec + ins + fail / 2, fail, INK)):
        a1.text(x, 0, str(v), ha="center", va="center", fontsize=20, fontweight="bold", color=c)
    a1.set_xlim(0, N)
    a1.set_yticks([])
    a1.set_xlabel(f"Number of tasks (of {N})")
    a1.grid(axis="y", visible=False)
    a1.set_title(f"{ins} of {sec + ins} working solutions are insecure ({M['InsecSharePct']}%)", fontsize=16, loc="left", pad=40)
    a1.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncols=3, fontsize=13)
    a1.set_ylim(-0.6, 0.6)
    vals = [float(M["FuncPct"]), float(M["SecPct"])]
    lo = [float(M["FuncCILo"]), float(M["SecCILo"])]
    hi = [float(M["FuncCIHi"]), float(M["SecCIHi"])]
    a2.bar([0, 1], vals, color=[BLUE, RED], width=0.55)
    a2.errorbar([0, 1], vals, yerr=[[v - l for v, l in zip(vals, lo)], [h - v for v, h in zip(vals, hi)]],
                fmt="none", ecolor=INK, capsize=10, lw=1.6)
    a2.scatter([0, 1], [57.0, 11.8], marker="D", s=70, color=INK, zorder=5, label="Published value")
    for i, v in enumerate(vals):
        a2.text(i + 0.33, v, f"{v:.2f}%", va="center", fontsize=15)
    a2.set_xticks([0, 1], ["FuncPass", "SecPass"])
    a2.set_ylim(0, 72)
    a2.set_xlim(-0.5, 1.75)
    a2.set_ylabel("Tasks solved (%)")
    a2.set_title("Recomputed, with 95% Wilson CI", fontsize=16, loc="left", pad=40)
    a2.legend(loc="lower left", bbox_to_anchor=(0, 1.0), fontsize=13)
    fig.tight_layout(w_pad=4)
    save(fig, out, "outcome_ci.png")

    # 3. Paper Table 3 replication
    t3 = read_dat(D / "table3.dat")
    fig, ax = plt.subplots(figsize=(15, 5.6))
    xs = list(range(len(t3)))
    w = 0.38
    ax.bar([x - w / 2 for x in xs], [float(r["func"]) for r in t3], w, color=BLUE, label="FuncPass (recomputed)")
    ax.bar([x + w / 2 for x in xs], [float(r["sec"]) for r in t3], w, color=RED, label="SecPass (recomputed)")
    ax.scatter([x - w / 2 for x in xs], [float(r["paperfunc"]) for r in t3], marker="_", s=420, color=INK, lw=2.5, zorder=5,
               label="Value printed in the paper")
    ax.scatter([x + w / 2 for x in xs], [float(r["papersec"]) for r in t3], marker="_", s=420, color=INK, lw=2.5, zorder=5)
    ax.set_xticks(xs, [r["label"] for r in t3], rotation=0, fontsize=12)
    ax.set_ylabel("Tasks solved (%)")
    ax.set_ylim(0, 66)
    ax.legend(loc="upper right", ncols=3, fontsize=13)
    ax.text(0, -12.5, "SA = SWE-agent · OH = OpenHands · CC = Claude Code      C4S = Claude 4 Sonnet · K2 = Kimi K2 · "
            "G25 / G3 = Gemini 2.5 / 3 Pro", fontsize=12, color=MUTED, transform=ax.transData)
    save(fig, out, "table3.png")

    # 4. Re-scoring: published vs re-scored, and agreement
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(15, 5.4), gridspec_kw={"width_ratios": [1, 1.3]})
    pf, rf, ps, rs = (int(M[k]) for k in ("RvPubFunc", "RvReFunc", "RvPubSec", "RvReSec"))
    a1.bar([0 - 0.18, 1 - 0.18], [pf, rf], 0.36, color=BLUE, label="Functional")
    a1.bar([0 + 0.18, 1 + 0.18], [ps, rs], 0.36, color=RED, label="Correct & secure")
    for x, v in ((-0.18, pf), (0.82, rf), (0.18, ps), (1.18, rs)):
        a1.text(x, v + 1, str(v), ha="center", fontsize=15)
    a1.set_xticks([0, 1], ["Published", "Re-scored by us"])
    a1.set_ylabel(f"Tasks (of {M['RvConcluded']} re-scored)")
    a1.set_ylim(0, 60)
    a1.legend(loc="upper left", bbox_to_anchor=(0, 1.12), ncols=2, fontsize=13)
    ag, d1, d2 = int(M["RvAgree"]), int(M["RvPubFailReFunc"]), int(M["RvPubFuncReFail"])
    a2.barh([0], [ag], color=BLUE, edgecolor=SURFACE, lw=2, label=f"Same verdict as published ({ag})")
    a2.barh([0], [d1], left=[ag], color=AMBER, edgecolor=SURFACE, lw=2, label=f"Published fail → re-scored pass ({d1})")
    a2.barh([0], [d2], left=[ag + d1], color=RED, edgecolor=SURFACE, lw=2, label=f"Published pass → re-scored fail ({d2})")
    a2.text(ag / 2, 0, f"{ag} / {M['RvCompared']} agree", ha="center", va="center", color="white", fontsize=20, fontweight="bold")
    a2.set_xlim(0, int(M["RvCompared"]))
    a2.set_ylim(-0.6, 0.9)
    a2.set_yticks([])
    a2.grid(axis="y", visible=False)
    a2.set_xlabel("Re-scored tasks")
    a2.legend(loc="upper left", fontsize=13)
    fig.tight_layout(w_pad=4)
    save(fig, out, "rescoring.png")

    # 5. Count-based thresholds
    th = read_dat(D / "thresholds.dat")
    fig, ax = plt.subplots(figsize=(9, 5.2))
    labels = ["0", "1–5", "6–20", "21–100", ">100"]
    vals = [int(r["count"]) for r in th]
    ax.bar(range(len(vals)), vals, color=BLUE, width=0.6)
    for i, v in enumerate(vals):
        ax.text(i, v + 2, str(v), ha="center", fontsize=15)
    ax.set_xticks(range(len(vals)), labels)
    ax.set_xlabel("Functional test failures each task tolerates (expected_pf)")
    ax.set_ylabel("Number of tasks")
    ax.set_ylim(0, 125)
    save(fig, out, "thresholds.png")

    # 6. Cost per task
    costs = [float(r["cost_usd"]) for r in csv.DictReader((sd / "results/per_task_results.csv").open())]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.hist(costs, bins=[0, 0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 7], color=BLUE, edgecolor=SURFACE, lw=2)
    ax.axvline(float(M["CostMean"]), color=INK, lw=1.5, ls="--")
    ax.text(float(M["CostMean"]) + 0.1, ax.get_ylim()[1] * 0.9, f"mean ${M['CostMean']}", fontsize=14)
    ax.set_xlabel("Recorded inference cost per task (USD)")
    ax.set_ylabel("Number of tasks")
    ax.set_title(f"Original run: ${M['CostTotal']} for {N} tasks", fontsize=16, loc="left")
    save(fig, out, "cost.png")

    # 7. Evaluator pilot table (wide banner): controls + published Claude patch on the 5 example tasks
    ev = sd / "logs" / "eval"
    def ck(name):
        return json.loads((ev / name / "checkpoint.json").read_text())["tasks"]
    G, V, E, R = (ck(n) for n in ("pilot_control_golden", "pilot_control_vulnerable",
                                  "pilot_control_empty", "reeval_published_v1.0"))
    ledger = {r["instance_id"]: r for r in csv.DictReader((sd / "results/per_task_results.csv").open())}
    ids = json.loads((sd / "logs" / "pilot_instance_ids.json").read_text())
    cols = ["Golden\n(secure fix)", "Vulnerable\n(original code)", "Empty\npatch", "Claude patch\nre-scored", "Claude patch\npublished"]
    fig, ax = plt.subplots(figsize=(19.2, 4.6))
    ax.axis("off")
    ax.set_xlim(0, 6.2)
    ax.set_ylim(-0.2, len(ids) + 1.3)
    ok, bad = ("✓", BLUE), ("✗", RED)

    def cell(rec):
        if rec.get("eval_status") == "empty_model_patch":
            return [("rejected", MUTED)]
        return [ok if rec.get("func_pass") else bad, ok if rec.get("sec_pass") else bad]
    for j, c in enumerate(cols):
        ax.text(1.55 + j * 0.95, len(ids) + 0.55, c, ha="center", va="center", fontsize=15, fontweight="bold", color=GREEN)
    ax.text(0.05, len(ids) + 0.55, "Task (CWE)\n(functional / security)", ha="left", va="center", fontsize=14, color=GREEN, fontweight="bold")
    for i, iid in enumerate(ids):
        y = len(ids) - 1 - i + 0.5
        r = ledger[iid]
        if i % 2 == 0:
            ax.add_patch(plt.Rectangle((0, y - 0.5), 6.2, 1, color="#E6E3DA", zorder=0))
        ax.text(0.05, y, f"{r['project'].split('/')[1]} ({r['cwe_ids']})", va="center", fontsize=15)
        pf, ps = r["published_func_pass"] == "pass", r["published_joint_secure"] == "True"
        cells = [cell(G[iid]), cell(V[iid]), cell(E[iid]), cell(R[iid]), [ok if pf else bad, ok if ps else bad]]
        for j, cs in enumerate(cells):
            x = 1.55 + j * 0.95
            if len(cs) == 1:
                ax.text(x, y, cs[0][0], ha="center", va="center", fontsize=15, color=cs[0][1])
            else:
                ax.text(x - 0.13, y, cs[0][0], ha="center", va="center", fontsize=24, color=cs[0][1], family="DejaVu Sans")
                ax.text(x, y, "/", ha="center", va="center", fontsize=18, color=MUTED)
                ax.text(x + 0.13, y, cs[1][0], ha="center", va="center", fontsize=24, color=cs[1][1], family="DejaVu Sans")
    fig.savefig(out / "pilot_table.png", dpi=200, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print("wrote pilot_table.png")

    # 8. Headline stat card (tall, for the dark-panel claim slide)
    fig = plt.figure(figsize=(5.2, 9.8))
    fig.patch.set_facecolor(SURFACE)
    def tile(y, big, col, small):
        fig.text(0.5, y, big, ha="center", fontsize=74, fontweight="bold", color=col)
        fig.text(0.5, y - 0.055, small, ha="center", fontsize=17, color=INK)
    tile(0.80, "57.0%", BLUE, "functionally correct")
    tile(0.50, "11.8%", RED, "correct and secure")
    tile(0.20, f"{float(M['InsecSharePct']):.0f}%", AMBER, "of working solutions insecure")
    fig.text(0.5, 0.05, "SWE-agent + Claude 4 Sonnet · SusVibes v1.0", ha="center", fontsize=12, color=MUTED)
    fig.savefig(out / "claim_card.png", dpi=200)
    plt.close(fig)
    print("wrote claim_card.png")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
