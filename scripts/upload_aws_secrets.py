"""Explicit deployment step: upload local tokens to SSM without console disclosure."""
import argparse
from pathlib import Path
import boto3
from botocore.exceptions import ClientError

parser = argparse.ArgumentParser()
parser.add_argument("--region", default="ap-southeast-1")
parser.add_argument("--overwrite", action="store_true", help="Intentionally rotate existing runtime parameters")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
values = dict(line.split("=", 1) for line in (root / ".env").read_text(encoding="utf-8").splitlines() if "=" in line and not line.startswith("#"))
client = boto3.client("ssm", region_name=args.region)
for key, name in {"ADMIN_TOKEN": "admin-token", "METRICS_TOKEN": "metrics-token"}.items():
    value = values.get(key, "")
    if len(value) < 24:
        raise SystemExit(f"Set a random {key} of at least 24 characters in .env")
    full_name = "/ticketpilot-aws/" + name
    try:
        existing = client.get_parameter(Name=full_name, WithDecryption=True)["Parameter"]["Value"]
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ParameterNotFound":
            raise
        existing = None
    if existing == value:
        continue
    if existing is not None and not args.overwrite:
        raise SystemExit("Existing remote token differs. Use your existing .env or explicitly rotate with --overwrite, then redeploy Lambda.")
    client.put_parameter(Name=full_name, Value=value, Type="SecureString", Tier="Standard", Overwrite=args.overwrite)
print("Runtime parameters uploaded. Values were not printed or passed through Terraform.")
