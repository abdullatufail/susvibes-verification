#!/usr/bin/env python3
"""Build SusVibes prediction files for re-evaluation.

1. The published SWE-agent + Claude 4 Sonnet patches (leaderboard trials.json), unchanged,
   in the official predictions format {instance_id, model_name_or_path, model_patch}.
2. Evaluator controls for a chosen set of tasks (never shown to any agent):
   - golden:      the dataset's golden_patch (secure reference) -> expect func pass, sec pass
   - vulnerable:  mask_patch reversed, i.e. the original vulnerable human implementation
                  -> expect func pass, sec fail
   - empty:       empty patch -> expect eval_status empty_patch (counted as failure)

Usage:
  python -I build_predictions.py --dataset <susvibes_dataset.jsonl> --trials <trials.json> \
      --out_dir <dir> [--control_ids <id> ...]
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

HUNK = re.compile(r"^@@ -(\d+(?:,\d+)?) \+(\d+(?:,\d+)?) @@(.*)$")


def reverse_unified_diff(patch: str) -> str:
    """Reverse a git-style unified diff (swap old/new sides). Handles text hunks only."""
    out = []
    lines = patch.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("diff --git "):
            m = re.match(r"^diff --git a/(\S+) b/(\S+)$", line)
            out.append(f"diff --git a/{m.group(2)} b/{m.group(1)}" if m else line)
        elif line.startswith("index "):
            m = re.match(r"^index ([0-9a-f]+)\.\.([0-9a-f]+)(.*)$", line)
            out.append(f"index {m.group(2)}..{m.group(1)}{m.group(3)}" if m else line)
        elif line.startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
            old, new = line[4:], lines[i + 1][4:]
            old = "a/" + new[2:] if new.startswith("b/") else new
            new = "b/" + line[4:][2:] if line[4:].startswith("a/") else line[4:]
            out.append("--- " + old)
            out.append("+++ " + new)
            i += 1
        elif line.startswith("new file mode"):
            out.append(line.replace("new file mode", "deleted file mode"))
        elif line.startswith("deleted file mode"):
            out.append(line.replace("deleted file mode", "new file mode"))
        elif HUNK.match(line):
            m = HUNK.match(line)
            out.append(f"@@ -{m.group(2)} +{m.group(1)} @@{m.group(3)}")
        elif line.startswith("+") and not line.startswith("+++ "):
            out.append("-" + line[1:])
        elif line.startswith("-") and not line.startswith("--- "):
            out.append("+" + line[1:])
        else:
            out.append(line)
        i += 1
    return "\n".join(out)


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, type=Path)
    ap.add_argument("--trials", required=True, type=Path)
    ap.add_argument("--out_dir", required=True, type=Path)
    ap.add_argument("--control_ids", nargs="*", default=[])
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    dataset = {json.loads(l)["instance_id"]: json.loads(l) for l in args.dataset.open()}
    trials = json.load(args.trials.open())
    ids = [t["instance_id"] for t in trials]
    assert len(ids) == len(set(ids)), "duplicate instance_id in trials"
    assert set(ids) == set(dataset), "trials do not cover exactly the dataset task set"

    preds = [{"instance_id": t["instance_id"],
              "model_name_or_path": t["model_name_or_path"],
              "model_patch": t["model_patch"]} for t in sorted(trials, key=lambda t: t["instance_id"])]
    p = args.out_dir / "claude-sonnet-4-20250514_published.jsonl"
    p.write_text("".join(json.dumps(x) + "\n" for x in preds))
    print(f"{p}: {len(preds)} predictions")
    patch_hashes = {x["instance_id"]: sha(x["model_patch"]) for x in preds}
    (args.out_dir / "published_patch_sha256.json").write_text(json.dumps(patch_hashes, indent=1, sort_keys=True))

    for control in ("golden", "vulnerable", "empty"):
        rows = []
        for iid in args.control_ids:
            rec = dataset[iid]
            patch = {"golden": rec["golden_patch"],
                     "vulnerable": reverse_unified_diff(rec["mask_patch"]),
                     "empty": ""}[control]
            rows.append({"instance_id": iid, "model_name_or_path": f"control-{control}", "model_patch": patch})
        if rows:
            p = args.out_dir / f"control_{control}.jsonl"
            p.write_text("".join(json.dumps(x) + "\n" for x in rows))
            print(f"{p}: {len(rows)} predictions")


if __name__ == "__main__":
    main()
