#!/usr/bin/env bash
# Rebuild ledger, metrics, paper cross-check and manifest from current evidence (safe to re-run any time).
set -eu
D=/home/user/susvibes-verification/susvibes_118_verification
SRC=/home/user/sources
SUB=$SRC/susvibes-leaderboard/public/submissions/claude-4-sonnet_swe-agent_default_2025-12-29
DS=$SRC/susvibes-v1.0/datasets/default/susvibes_dataset.jsonl
E=$D/logs/eval
# Sync live run output (written outside the repo) into the study directory.
LIVE=${LIVE:-/home/user/runs/eval}
if [ -d "$LIVE" ]; then cp -a "$LIVE"/. "$E"/; fi
[ -f /home/user/runs/full_reeval_driver.log ] && cp /home/user/runs/full_reeval_driver.log $D/logs/full_reeval_driver.log
python3 -I $D/scripts/screen_trajectories.py $SUB/trajectories $D/logs/artifact_audit/trajectory_screen.json > /dev/null
python3 -I $D/scripts/build_ledger.py --dataset $DS --submission $SUB \
  --dec2025_digest $D/logs/artifact_audit/v0.0_dec2025_record_digest.json \
  --screen $D/logs/artifact_audit/trajectory_screen.json \
  --reeval_ckpt $E/reeval_published_v1.0/checkpoint.json \
  --control golden=$E/pilot_control_golden/checkpoint.json --control golden=$E/disagree_control_golden/checkpoint.json \
  --control vulnerable=$E/pilot_control_vulnerable/checkpoint.json --control vulnerable=$E/disagree_control_vulnerable/checkpoint.json \
  --out $D/results/per_task_results.csv
python3 -I $D/scripts/recompute_metrics.py --ledger $D/results/per_task_results.csv --dataset $DS \
  --out $D/results/summary.json --published_summary $SUB/trajectories/claude-4-sonnet_swe-agent_default_2025-12-29.summary.json
python3 -I $D/scripts/crosscheck_paper_tables.py $SRC/susvibes-leaderboard/public/submissions $D/results/paper_table_crosscheck.json > /dev/null
python3 -I $D/scripts/make_manifest.py --study_dir $D --susvibes $SRC/susvibes --susvibes_v1 $SRC/susvibes-v1.0 \
  --leaderboard $SRC/susvibes-leaderboard --paper_dir $SRC/paper --hf_dir $SRC/hf \
  --proposal /root/.claude/uploads/3b4224f5-3300-532a-b006-35f4c8da931b/3ea48754-proposal.pdf
python3 -I $D/scripts/write_rescoring_md.py $D > /dev/null
python3 -I $D/scripts/write_checkpoint_md.py $D > /dev/null
python3 -I $D/scripts/make_report_data.py $D $DS > /dev/null
