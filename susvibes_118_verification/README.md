# SusVibes 11.8% verification study

**Research question.** Can we independently verify that SWE-agent with Claude 4 Sonnet reached a 11.8% secure pass rate (SecPass) on SusVibes?

**Context.** This is the baseline-establishment step for the SEECS/NUST FYP *Agentic Detect-Then-Patch Framework for Vulnerability Repair in AI-Generated Code*.

**Status and verdict.** See [`reproduction_report.md`](reproduction_report.md) for the full report and [`CHECKPOINT.md`](CHECKPOINT.md) for the live experiment state.

## Contents

| Path | What it is |
|---|---|
| `source_audit.md` | Provenance of the 11.8% figure: paper versions, dataset versions, model and agent configuration, prompt strategy, and evaluator semantics |
| `reproduction_report.md` | Research-style report with the verdict |
| `results/per_task_results.csv` | Authoritative 186-row ledger. Published verdicts, independent re-scoring verdicts, metadata and provenance |
| `results/summary.json` | Metrics recomputed from the ledger, with Wilson CIs and project/CWE subgroups |
| `results/paper_table_crosscheck.json` | Paper Tables 3 and 5 and Figure 5, recomputed from per-task leaderboard artifacts |
| `results/original_run_cost_profile.json` | Cost and token profile of the original run (basis for the fresh-run estimate) |
| `scripts/` | All analysis and orchestration code (below) |
| `predictions/` | The published Claude patches in official predictions format, plus evaluator controls |
| `logs/eval/<run>/` | Per-task evidence from the official evaluator: `report.json`, gzipped `run_instance.log`, functional/security test output, harness stdout/stderr, `checkpoint.json`, `batches.jsonl`, `run.log` |
| `logs/artifact_audit/` | Trajectory screen (prompt variant, git-history commands) and a digest of the Dec-2025 v0.0 record |
| `logs/environment_preflight.json` | Hardware/software, Docker state and credential *presence* (no secrets) |
| `manifest.json` | Source URLs, pinned commits, dataset hashes, configuration, batch records, file checksums |

## Scripts

| Script | Purpose |
|---|---|
| `scripts/screen_trajectories.py` | Flags prompt strategy (generic reminder / CWE hint) and git-history or network commands in each trajectory |
| `scripts/build_ledger.py` | Builds `per_task_results.csv` from the dataset, the leaderboard per-task lists, the trajectory screen and the re-scoring checkpoint |
| `scripts/recompute_metrics.py` | Validates the ledger and recomputes every metric from per-task rows. No hard-coded counts |
| `scripts/crosscheck_paper_tables.py` | Recomputes paper Table 3, Table 5 and Figure 5 from per-task lists |
| `scripts/build_predictions.py` | Writes the published patches and the golden / vulnerable (reversed `mask_patch`) / empty controls as prediction files |
| `scripts/run_eval_batches.py` | Checkpointed, sequential wrapper around the official `python -m susvibes.eval.core`. Logical batches of 5, one task image on disk at a time, resumable |
| `scripts/run_pilot.sh` | Stage-2 pilot: controls and published patches on the 5 shipped example tasks |
| `scripts/run_full_reeval.sh` | Stage-2b: re-score all 186 published patches (no model inference) |
| `scripts/make_manifest.py` | Writes `manifest.json` |

## Environment requirements

* x86_64 Linux, Docker, Python ≥ 3.11, network access to Docker Hub (`songwen6968/susvibes.x86_64.eval_*` images).
* Each eval image is about 1.8 GB. With one task processed at a time, peak extra disk use is about 4 GB.
* No model API is needed for anything in this directory. A fresh SWE-agent run would need one; see the report §8.

## Reproduction commands

```bash
# 0. Sources (pinned)
git clone https://github.com/LeiLiLab/susvibes.git && git -C susvibes worktree add ../susvibes-v1.0 v1.0
git clone https://github.com/LeiLiLab/susvibes-leaderboard.git        # main @ c74a6a2
uv venv -p 3.11 sv-venv && uv pip install -p sv-venv/bin/python -r susvibes-v1.0/requirements.txt -e susvibes-v1.0

SUB=susvibes-leaderboard/public/submissions/claude-4-sonnet_swe-agent_default_2025-12-29
DS=susvibes-v1.0/datasets/default/susvibes_dataset.jsonl

# 1. Artifact audit (no Docker, no API; seconds)
python -I scripts/screen_trajectories.py $SUB/trajectories logs/artifact_audit/trajectory_screen.json
python -I scripts/build_ledger.py --dataset $DS --submission $SUB \
   --dec2025_digest logs/artifact_audit/v0.0_dec2025_record_digest.json \
   --screen logs/artifact_audit/trajectory_screen.json \
   --reeval_ckpt logs/eval/reeval_published_v1.0/checkpoint.json --out results/per_task_results.csv
python -I scripts/recompute_metrics.py --ledger results/per_task_results.csv --dataset $DS \
   --out results/summary.json --published_summary $SUB/trajectories/claude-4-sonnet_swe-agent_default_2025-12-29.summary.json
python -I scripts/crosscheck_paper_tables.py susvibes-leaderboard/public/submissions results/paper_table_crosscheck.json

# 2. Independent re-scoring with the official evaluator (Docker; resumable)
python -I scripts/build_predictions.py --dataset $DS --trials $SUB/trajectories/*.trials.json \
   --out_dir predictions --control_ids $(python3 -c "import json;print(' '.join(json.load(open('logs/pilot_instance_ids.json'))))")
scripts/run_pilot.sh
scripts/run_full_reeval.sh          # re-run the same command to resume after interruption
```

The scripts contain absolute paths from the study machine (`/home/user/sources/...`, `/home/user/susvibes-verification/...`). Adjust these if you clone elsewhere.
