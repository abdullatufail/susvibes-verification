#!/usr/bin/env bash
# Stage-2 pilot: evaluator controls + published Claude patches on the 5 shipped example tasks.
# One task image at a time; controls reuse the cached image; the final (Claude) pass removes it.
set -u
D=/home/user/susvibes-verification/susvibes_118_verification
H=/home/user/sources/susvibes-v1.0
PY=/home/user/sources/sv-venv/bin/python
IDS=$D/logs/pilot_instance_ids.json
for iid in $(python3 -c "import json;print(' '.join(json.load(open('$IDS'))))"); do
  echo "$iid" > /dev/null
  python3 -c "import json;json.dump(['$iid'],open('$D/logs/_one.json','w'))"
  for c in golden vulnerable empty; do
    python3 -I $D/scripts/run_eval_batches.py --predictions $D/predictions/control_$c.jsonl \
      --run_id pilot_control_$c --strategy generic --harness_root $H --harness_python $PY \
      --out_dir $D/logs/eval/pilot_control_$c --instance_ids_file $D/logs/_one.json --keep_images
  done
  python3 -I $D/scripts/run_eval_batches.py --predictions $D/predictions/claude-sonnet-4-20250514_published.jsonl \
    --run_id reeval_published_v1.0 --strategy generic --harness_root $H --harness_python $PY \
    --out_dir $D/logs/eval/reeval_published_v1.0 --instance_ids_file $D/logs/_one.json
done
rm -f $D/logs/_one.json
echo PILOT_DONE
