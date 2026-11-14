"""Select a successful, trusted release run before requesting AWS credentials."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess


def validate_run(run, repository, default_branch, run_id):
    if not re.fullmatch(r"[1-9][0-9]*", str(run_id)):
        raise ValueError("Release run ID must be a positive integer")
    if (str(run.get("id")) != str(run_id)
        or run.get("repository", {}).get("full_name", "").lower() != repository.lower()
        or run.get("head_repository", {}).get("full_name", "").lower() != repository.lower()
        or run.get("head_branch") != default_branch
        or run.get("path", "").split("@", 1)[0] != ".github/workflows/release.yml"
        or run.get("event") not in {"push", "workflow_dispatch"}
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or not re.fullmatch(r"[0-9a-f]{40}", run.get("head_sha", ""))):
        raise ValueError("Choose a successful release.yml run from this repository's default branch")
    return run["head_sha"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--default-branch", required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository) or not re.fullmatch(r"[1-9][0-9]*", args.run_id):
        parser.error("Invalid repository or run ID")
    result = subprocess.run(["gh", "api", f"repos/{args.repository}/actions/runs/{args.run_id}"], check=True, capture_output=True, text=True)
    run = json.loads(result.stdout)
    try:
        commit = validate_run(run, args.repository, args.default_branch, args.run_id)
    except ValueError as exc:
        parser.error(str(exc))
    target = Path(".tools/selected-release.json")
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps({"repository": args.repository.lower(), "commit": commit, "run_id": args.run_id}), encoding="utf-8")
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(f"commit={commit}\nrun_id={args.run_id}\n")
    print(f"Verified successful release run {args.run_id}, commit {commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
