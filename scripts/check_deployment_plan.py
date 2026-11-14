"""Limit automated CD to updating an existing Lambda image, without infra deletion or reconfiguration."""
import argparse
import json
from pathlib import Path
import re


def validate_plan(plan, image_uri):
    if not re.fullmatch(r"[0-9]{12}\.dkr\.ecr\.ap-southeast-1\.amazonaws\.com/ticketpilot-aws@sha256:[0-9a-f]{64}", image_uri):
        raise ValueError("Expected an immutable TicketPilot ECR image in Singapore")
    if plan.get("errored") or plan.get("complete") is False:
        raise ValueError("Terraform did not produce a complete successful plan")
    changed = 0
    for resource in plan.get("resource_changes", []):
        change = resource["change"]
        actions = change["actions"]
        if actions == ["no-op"] or (resource.get("mode") == "data" and actions == ["read"]):
            continue
        if resource.get("address") != "aws_lambda_function.app" or actions != ["update"]:
            raise ValueError("CD permits only an existing Lambda image update; review infrastructure changes separately")
        before, after, unknown = change.get("before") or {}, change.get("after") or {}, change.get("after_unknown") or {}
        computed = {"last_modified", "qualified_arn", "qualified_invoke_arn", "version", "signing_job_arn", "signing_profile_version_arn", "invoke_arn", "arn", "id", "code_sha256"}
        def is_unknown(value):
            if isinstance(value, dict):
                return any(is_unknown(v) for v in value.values())
            if isinstance(value, list):
                return any(is_unknown(v) for v in value)
            return value is True
        differences = {key for key in set(before) | set(after) if before.get(key) != after.get(key) and not (key in computed and is_unknown(unknown.get(key)))}
        if differences - {"image_uri"} or after.get("image_uri") != image_uri:
            raise ValueError("Lambda changes include configuration beyond the selected image")
        if any(is_unknown(value) for key, value in unknown.items() if key not in computed):
            raise ValueError("Lambda configuration must remain known and unchanged")
        changed += 1
    if changed > 1:
        raise ValueError("Unexpected duplicate Lambda changes")
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan")
    parser.add_argument("--image-uri", required=True)
    args = parser.parse_args(argv)
    try:
        changed = validate_plan(json.loads(Path(args.plan).read_text(encoding="utf-8")), args.image_uri)
    except (ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(f"Deployment plan accepted: {changed} Lambda image update(s); no other managed-resource changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
