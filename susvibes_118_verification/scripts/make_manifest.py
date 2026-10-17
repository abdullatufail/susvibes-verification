#!/usr/bin/env python3
"""Write manifest.json: source URLs, pinned commits, dataset hashes, model/config identifiers,
batch records and checksums of the important study files. Paths are given on the command line.

Usage: python -I make_manifest.py --study_dir DIR --susvibes DIR --susvibes_v1 DIR \
           --leaderboard DIR --paper_dir DIR --hf_dir DIR --proposal FILE
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

SUB = "claude-4-sonnet_swe-agent_default_2025-12-29"


def sha(p: Path):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def git(d, *a):
    return subprocess.run(["git", "-C", str(d), *a], capture_output=True, text=True).stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    for k in ("study_dir", "susvibes", "susvibes_v1", "leaderboard", "paper_dir", "hf_dir", "proposal"):
        ap.add_argument(f"--{k}", required=True, type=Path)
    a = ap.parse_args()
    sd = a.study_dir
    tdir = a.leaderboard / "public/submissions" / SUB / "trajectories"
    msgs = sorted((tdir / "messages").glob("*.json"))
    msg_digest = hashlib.sha256("".join(f"{p.name}:{sha(p)}\n" for p in msgs).encode()).hexdigest()

    batches = []
    for bj in sorted((sd / "logs/eval").glob("*/batches.jsonl")):
        for line in bj.read_text().splitlines():
            b = json.loads(line)
            batches.append({"run": bj.parent.name, "batch": b["batch"], "instance_ids": b["instance_ids"],
                            "completed": b["completed"], "technical_error": b["technical_error"],
                            "needs_review": b["needs_review"], "func_pass": b["func_pass"],
                            "sec_pass_joint": b["sec_pass_joint"], "checkpoint_sha256": b.get("checkpoint_sha256"),
                            "started_at": b["started_at"], "finished_at": b["finished_at"]})

    important = [p for p in sorted(sd.rglob("*")) if p.is_file() and p.suffix in (".csv", ".json", ".md", ".py", ".sh", ".jsonl")
                 and "logs/eval" not in str(p.relative_to(sd)) and p.name != "manifest.json"]
    important += [p for p in sorted((sd / "logs/eval").glob("*/checkpoint.json"))]
    important += [p for p in sorted((sd / "logs/eval").glob("*/batches.jsonl"))]

    manifest = {
        "study": "Independent verification of SusVibes SecPass 11.8% (SWE-agent + Claude 4 Sonnet)",
        "sources": {
            "paper_pmlr": {"url": "https://proceedings.mlr.press/v306/zhao26ax.html",
                           "pdf_url": "https://raw.githubusercontent.com/mlresearch/v306/main/assets/zhao26ax/zhao26ax.pdf",
                           "sha256": sha(a.paper_dir / "pmlr_zhao26ax.pdf")},
            "paper_arxiv": {f"v{v}": {"url": f"https://arxiv.org/abs/2512.03262v{v}",
                                      "sha256": sha(a.paper_dir / f"arxiv_v{v}.pdf")} for v in (1, 2, 3, 4)},
            "susvibes_repo": {"url": "https://github.com/LeiLiLab/susvibes",
                              "main_commit": git(a.susvibes, "rev-parse", "HEAD"),
                              "tag_v1.0_commit": git(a.susvibes, "rev-list", "-n1", "v1.0"),
                              "tag_v0.0_commit": git(a.susvibes, "rev-list", "-n1", "v0.0"),
                              "evaluator_used_for_rescoring": git(a.susvibes_v1, "rev-parse", "HEAD")},
            "leaderboard_repo": {"url": "https://github.com/LeiLiLab/susvibes-leaderboard",
                                 "main_commit": git(a.leaderboard, "rev-parse", "HEAD"),
                                 "submission_dir": f"public/submissions/{SUB}",
                                 "v1_migration_commit": "857104185009d3a49f91cd064f1315bdd99e33d4",
                                 "dec2025_trials_commit": git(a.leaderboard, "rev-parse", "4db597e"),
                                 "submission_guide_url": "https://github.com/LeiLiLab/susvibes-leaderboard/blob/main/docs/SUBMISSION_GUIDE.md"},
            "leaderboard_site": "https://leililab.github.io/susvibes-leaderboard/",
            "hf_dataset": {"url": "https://huggingface.co/datasets/dqwang122/susvibes",
                           "revision": json.loads((a.hf_dir / "api.json").read_text())["sha"],
                           "jsonl_sha256": sha(a.hf_dir / "susvibes_dataset.jsonl")},
            "fyp_proposal_sha256": sha(a.proposal),
        },
        "dataset": {
            "version": "v1.0", "tasks": 186,
            "jsonl_sha256_tag_v1.0": sha(a.susvibes_v1 / "datasets/default/susvibes_dataset.jsonl"),
            "leaderboard_v1.0_jsonl_sha256": sha(a.leaderboard / "public/datasets/susvibes_dataset_v1.0.jsonl"),
            "v0.0_jsonl_sha256": sha(a.leaderboard / "public/datasets/susvibes_dataset_v0.0.jsonl"),
        },
        "evaluated_configuration": {
            "model_identifier": "claude-sonnet-4-20250514",
            "agent": "SWE-agent (~1.1.0; exact commit and susvibes_eval/no_cache config YAML unpublished)",
            "prompt_strategy": "generic security reminder (## Safety Requirements), 186/186 trajectories",
            "sampling": "temperature 0.00, top_p 1.00 (from original run-directory name)",
            "limits": "per_instance_call_limit 200, per_instance_cost_limit 0 (unlimited)",
            "attempts": "pass@1",
            "original_run_dir": "susvibes_eval__claude-sonnet-4-20250514__t-0.00__p-1.00__c-0.00___susvibes.run_evaluation_generic_instances",
        },
        "published_artifacts_sha256": {
            "submission.json": sha(tdir.parent / "submission.json"),
            "summary.json": sha(tdir / f"{SUB}.summary.json"),
            "trials.json": sha(tdir / f"{SUB}.trials.json"),
            "messages_dir_digest": msg_digest, "messages_count": len(msgs),
        },
        "batch_records": batches,
        "study_file_sha256": {str(p.relative_to(sd)): sha(p) for p in important},
    }
    (sd / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"manifest: {len(manifest['study_file_sha256'])} files, {len(batches)} batch records")


if __name__ == "__main__":
    main()
