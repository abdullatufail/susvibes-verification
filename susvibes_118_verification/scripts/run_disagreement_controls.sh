#!/usr/bin/env bash
# Stage-2c: for every task whose re-scored verdict disagrees with the published one, evaluate the
# golden (secure reference) and vulnerable (reversed mask_patch) controls on this machine. If the
# golden patch also fails here, the disagreement is attributable to this environment.
set -u
D=/home/user/susvibes-verification/susvibes_118_verification
H=/home/user/sources/susvibes-v1.0
PY=/home/user/sources/sv-venv/bin/python
IDS=$D/logs/disagreement_instance_ids.json
python3 -I - "$D" <<'PY'
import csv, json, sys
d = sys.argv[1]
ids = [r["instance_id"] for r in csv.DictReader(open(f"{d}/results/per_task_results.csv"))
       if r["reeval_matches_published"] == "False" or r["reeval_status"] in ("technical_error", "needs_review")]
json.dump(ids, open(f"{d}/logs/disagreement_instance_ids.json", "w"), indent=1)
print(f"{len(ids)} tasks need controls")
PY
for c in golden vulnerable; do
  keep=--keep_images; [ "$c" = vulnerable ] && keep=
  for iid in $(python3 -c "import json;print(' '.join(json.load(open('$IDS'))))"); do
    python3 -c "import json;json.dump(['$iid'],open('$D/logs/_one.json','w'))"
    python3 -I $D/scripts/run_eval_batches.py --predictions $D/predictions/control_${c}_all186.jsonl \
      --run_id disagree_control_$c --strategy generic --harness_root $H --harness_python $PY \
      --out_dir $D/logs/eval/disagree_control_$c --instance_ids_file $D/logs/_one.json $keep
  done
done
rm -f $D/logs/_one.json
echo CONTROLS_DONE
