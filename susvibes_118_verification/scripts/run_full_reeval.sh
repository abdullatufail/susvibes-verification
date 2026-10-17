#!/usr/bin/env bash
# Stage-2b: re-score all 186 published SWE-agent + Claude 4 Sonnet patches with the pinned
# official v1.0 evaluator. Zero model inference. Resumable: completed tasks with valid saved
# evidence are skipped by run_eval_batches.py; batches of 5, one task/image at a time.
# Environment-validity controls (golden patch) are run afterwards by run_disagreement_controls.sh,
# only on tasks whose re-scored verdict differs from the published one.
set -u
D=/home/user/susvibes-verification/susvibes_118_verification
# Live output is written outside the git repo and synced into $D/logs/eval by rebuild_results.sh.
LIVE=${LIVE:-/home/user/runs/eval}
python3 -I $D/scripts/run_eval_batches.py \
  --predictions $D/predictions/claude-sonnet-4-20250514_published.jsonl \
  --run_id reeval_published_v1.0 --strategy generic \
  --harness_root /home/user/sources/susvibes-v1.0 --harness_python /home/user/sources/sv-venv/bin/python \
  --out_dir $LIVE/reeval_published_v1.0 --batch_size 5 "$@"
echo FULL_REEVAL_EXIT=$?
