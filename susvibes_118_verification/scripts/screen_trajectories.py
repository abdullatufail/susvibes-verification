#!/usr/bin/env python3
"""Screen SWE-agent trajectories (leaderboard messages format) for prompt variant,
git-history access and network access to upstream sources.

Read-only, descriptive heuristics; flags are for manual review, not verdicts.
Usage: python -I screen_trajectories.py <submission_trajectories_dir> <out_json>
"""
import json
import os
import re
import sys

GIT_HISTORY = re.compile(r"\bgit\s+(log|show|reflog|checkout\s+[0-9a-f]{7,}|diff\s+[0-9a-f]{7,}|cat-file|rev-list|fsck|stash\s+show)\b")
NETWORK = re.compile(r"\b(git\s+clone|curl\s|wget\s|pip\s+download|pip\s+install\s+[^\n]*==)")


def commands(msgs):
    for m in msgs:
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"raw": fn.get("arguments")}
            if fn.get("name") == "bash":
                yield args.get("command") or args.get("raw") or ""


def main(traj_dir, out_path):
    trials_path = [f for f in os.listdir(traj_dir) if f.endswith(".trials.json")][0]
    trials = json.load(open(os.path.join(traj_dir, trials_path)))
    out = {}
    for t in trials:
        msgs = json.load(open(os.path.join(traj_dir, t["messages"])))
        first_user = next((m["content"] for m in msgs if m["role"] == "user"), "")
        if not isinstance(first_user, str):
            first_user = json.dumps(first_user)
        cmds = list(commands(msgs))
        out[t["instance_id"]] = {
            "n_messages": len(msgs),
            "n_bash_commands": len(cmds),
            "prompt_has_generic_safety_reminder": "## Safety Requirements" in first_user,
            "prompt_has_cwe_hint": "CWE-" in first_user,
            "git_history_commands": [c[:200] for c in cmds if GIT_HISTORY.search(c)],
            "network_commands": [c[:200] for c in cmds if NETWORK.search(c)],
        }
    json.dump(out, open(out_path, "w"), indent=1, sort_keys=True)
    n = len(out)
    print(f"trajectories: {n}")
    print("generic safety reminder:", sum(v["prompt_has_generic_safety_reminder"] for v in out.values()))
    print("CWE hint in prompt:", sum(v["prompt_has_cwe_hint"] for v in out.values()))
    print("with git-history commands:", sum(bool(v["git_history_commands"]) for v in out.values()))
    print("with network commands:", sum(bool(v["network_commands"]) for v in out.values()))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
