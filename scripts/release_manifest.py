"""Create and verify immutable container release metadata without cloud credentials."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

_SCHEMA_KEYS = {"schema_version", "repository", "commit", "run_id", "app", "lambda"}
_IMAGE_KEYS = {"image", "digest"}
_REPOSITORY = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9]+(?:(?:[._]|__|-+)[A-Za-z0-9]+)*")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_RUN_ID = re.compile(r"[1-9][0-9]*")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_MAX_BYTES = 16_384


def _repository(value: str) -> str:
    if not isinstance(value, str) or not _REPOSITORY.fullmatch(value):
        raise ValueError("repository must be a GitHub owner/repository with a valid container image name")
    if len(value.split("/", 1)[1]) > 100:
        raise ValueError("repository name exceeds the supported GitHub name length")
    return value.lower()


def _matches(value: str, pattern: re.Pattern, message: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(message)
    return value


def _provenance(repository: str, commit: str, run_id: str) -> tuple[str, str, str]:
    return (
        _repository(repository),
        _matches(commit, _COMMIT, "commit must be a lowercase 40-character hexadecimal SHA"),
        _matches(run_id, _RUN_ID, "run_id must be a positive decimal string without leading zeros"),
    )


def build_manifest(repository: str, commit: str, run_id: str, app_digest: str, lambda_digest: str) -> dict:
    """Build schema 1 metadata; repository input is case-insensitive GitHub naming."""
    repository, commit, run_id = _provenance(repository, commit, run_id)
    manifest = {
        "schema_version": 1,
        "repository": repository,
        "commit": commit,
        "run_id": run_id,
        "app": {"image": "ghcr.io/" + repository, "digest": app_digest},
        "lambda": {"image": "ghcr.io/" + repository + "-lambda", "digest": lambda_digest},
    }
    return validate_manifest(manifest, repository, commit, run_id)


def validate_manifest(manifest: dict, repository: str, commit: str, run_id: str) -> dict:
    """Reject untrusted references or mismatched provenance; return a canonical copy."""
    repository, commit, run_id = _provenance(repository, commit, run_id)
    if not isinstance(manifest, dict) or set(manifest) != _SCHEMA_KEYS:
        raise ValueError("manifest must contain exactly the schema 1 fields")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("unsupported manifest schema_version")
    for field, expected in (("repository", repository), ("commit", commit), ("run_id", run_id)):
        if type(manifest[field]) is not str or manifest[field] != expected:
            raise ValueError("manifest " + field + " does not match the expected workflow provenance")
    result = {"schema_version": 1, "repository": repository, "commit": commit, "run_id": run_id}
    for field, expected_image in (("app", "ghcr.io/" + repository), ("lambda", "ghcr.io/" + repository + "-lambda")):
        image = manifest[field]
        if not isinstance(image, dict) or set(image) != _IMAGE_KEYS:
            raise ValueError(field + " must contain exactly image and digest")
        if type(image["image"]) is not str or image["image"] != expected_image:
            raise ValueError(field + " image must match the expected GHCR repository exactly")
        digest = _matches(image["digest"], _DIGEST, field + " digest must be an immutable lowercase sha256 digest")
        result[field] = {"image": expected_image, "digest": digest}
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest JSON keys are not allowed")
        result[key] = value
    return result


def _metadata(manifest: dict) -> dict:
    return {
        "commit": manifest["commit"],
        "app_ref": manifest["app"]["image"] + "@" + manifest["app"]["digest"],
        "lambda_ref": manifest["lambda"]["image"] + "@" + manifest["lambda"]["digest"],
        "run_id": manifest["run_id"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    write = commands.add_parser("write", help="Write validated release metadata")
    verify = commands.add_parser("verify", help="Verify image names and workflow provenance")
    for command in (write, verify):
        command.add_argument("--repository", required=True)
        command.add_argument("--commit", required=True)
        command.add_argument("--run-id", required=True)
    write.add_argument("--app-digest", required=True)
    write.add_argument("--lambda-digest", required=True)
    write.add_argument("--output", required=True, type=Path)
    verify.add_argument("--path", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "write":
            manifest = build_manifest(args.repository, args.commit, args.run_id, args.app_digest, args.lambda_digest)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        else:
            if args.path.stat().st_size > _MAX_BYTES:
                raise ValueError("manifest exceeds the allowed metadata size")
            document = json.loads(args.path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
            manifest = validate_manifest(document, args.repository, args.commit, args.run_id)
            output = os.getenv("GITHUB_OUTPUT")
            if output:
                with Path(output).open("a", encoding="utf-8") as stream:
                    for key, value in _metadata(manifest).items():
                        stream.write(key + "=" + value + "\n")
        print(json.dumps({"schema_version": 1, "repository": manifest["repository"], **_metadata(manifest)}, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print("Release manifest rejected: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
