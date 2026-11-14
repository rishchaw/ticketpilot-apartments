"""Read-only deployment preflight; fail closed when a required service is unavailable."""
import argparse
import json
import os
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--profile", default=os.getenv("AWS_PROFILE", "ticketpilot"))
    args = parser.parse_args(argv)
    try:
        session = boto3.Session(profile_name=args.profile, region_name=args.region)
        identity = session.client("sts").get_caller_identity()
        lambda_client = session.client("lambda")
        dynamodb = session.client("dynamodb")
        ecr = session.client("ecr")
        ssm = session.client("ssm")
    except (BotoCoreError, ClientError) as exc:
        print(f"AWS sign-in unavailable: {type(exc).__name__}. Check the selected local profile; never paste credentials into chat.", file=sys.stderr)
        return 1
    print(json.dumps({"account": identity["Account"], "principal": identity["Arn"], "profile": args.profile, "region": args.region}, indent=2))
    checks = {
        "Lambda": lambda_client.get_account_settings,
        "DynamoDB": lambda: dynamodb.list_tables(Limit=1),
        "ECR": lambda: ecr.describe_repositories(maxResults=1),
        "SSM": lambda: ssm.describe_parameters(MaxResults=1),
    }
    unavailable = False
    for name, check in checks.items():
        try:
            response = check()
            detail = ""
            if name == "Lambda":
                detail = " (regional concurrency: " + str(response.get("AccountLimit", {}).get("ConcurrentExecutions", "unknown")) + ")"
            print(f"{name}: read access available{detail}")
        except (BotoCoreError, ClientError) as exc:
            unavailable = True
            error = exc.response["Error"] if isinstance(exc, ClientError) else {"Code": type(exc).__name__}
            print(f"{name}: {json.dumps(error)}; check permissions/account service access", file=sys.stderr)
    print("Read access does not prove create permissions or Free plan eligibility. Verify credits and expiry in AWS Billing.")
    if unavailable:
        print("Deployment preflight failed. Resolve account activation or service access before creating cloud resources.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())