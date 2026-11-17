"""Accept this AWS deployment using fictional records and guarded exact-ID cleanup.

Binds the HTTPS URL and DynamoDB table to the selected Lambda before any writes.
Reads only known synthetic record IDs; never lists private concerns or updates
notices. Manager values stay in-process. No paid model calls are requested.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import re
import sys
from urllib.parse import urlparse
from uuid import uuid4

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.config import Config
from dotenv import dotenv_values
import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.validate_gcp_deployment import exercise_http, failure_details, require, write_report


def verify_binding(lambda_client, function_name, table_name, url):
    configuration = lambda_client.get_function_configuration(FunctionName=function_name)
    public = lambda_client.get_function_url_config(FunctionName=function_name)
    require(public.get("FunctionUrl", "").rstrip("/") == url.rstrip("/"), "Selected HTTPS URL does not belong to the selected Lambda")
    require(public.get("AuthType") == "NONE", "The selected URL is not the public apartment endpoint")
    environment = configuration.get("Environment", {}).get("Variables", {})
    require(environment.get("STORAGE_MODE") == "dynamodb" and environment.get("DYNAMODB_TABLE") == table_name, "Selected table does not match the Lambda persistence configuration")
    require(environment.get("LLM_PROVIDER", "none") == "none", "Disable hosted generation for this low-cost acceptance run")
    require(configuration.get("State") == "Active" and configuration.get("LastUpdateStatus") == "Successful", "The selected Lambda deployment is not ready")


def read_exact(table, receipt, marker):
    item = table.get_item(Key={"id": receipt.record_id}, ConsistentRead=True).get("Item", {})
    require(item.get("id") == receipt.record_id and item.get("title") == receipt.title and receipt.title.startswith(marker), "Independent DynamoDB read did not match this synthetic run")
    require(item.get("kind") == "apartment_ticket" and item.get("queue") == "apartment_tickets", "Independent DynamoDB record kind/queue differs")
    require(item.get("version") == receipt.version and item.get("status") == receipt.status, "Independent DynamoDB state differs from the HTTP workflow")
    require(item.get("tracking_hash") == hashlib.sha256(receipt.key.encode()).hexdigest(), "DynamoDB tracking-key hash did not match")
    return item


def cleanup_owned(table, created, marker):
    result = {"created": len(created), "deleted": 0, "already_absent": 0, "skipped": 0, "error_types": []}
    for receipt in created:
        try:
            item = table.get_item(Key={"id": receipt.record_id}, ConsistentRead=True).get("Item")
            if not item:
                result["already_absent"] += 1
                continue
            owned = item.get("id") == receipt.record_id and item.get("title") == receipt.title and receipt.title.startswith(marker) and item.get("kind") == "apartment_ticket" and item.get("queue") == "apartment_tickets"
            if receipt.key:
                owned = owned and item.get("tracking_hash") == hashlib.sha256(receipt.key.encode()).hexdigest()
            if not owned or "version" not in item or "updated_at" not in item:
                result["skipped"] += 1
                continue
            # Version/timestamp predicates refuse a changed record between read
            # and delete. Exact title, queue, kind and key hash retain ownership.
            condition = Attr("title").eq(receipt.title) & Attr("queue").eq("apartment_tickets") & Attr("kind").eq("apartment_ticket") & Attr("version").eq(item["version"]) & Attr("updated_at").eq(item["updated_at"]) & Attr("tracking_hash").eq(item["tracking_hash"])
            try:
                table.delete_item(Key={"id": receipt.record_id}, ConditionExpression=condition)
            except table.meta.client.exceptions.ConditionalCheckFailedException:
                result["skipped"] += 1
                continue
            require(not table.get_item(Key={"id": receipt.record_id}, ConsistentRead=True).get("Item"), "Synthetic cleanup could not be independently confirmed")
            result["deleted"] += 1
        except Exception as error:
            # SDK errors can contain account IDs/request details; report types only.
            result["error_types"].append(type(error).__name__)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--function", default="ticketpilot-aws")
    parser.add_argument("--profile", default="ticketpilot")
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args(argv)
    parsed = urlparse(args.url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.port not in (None, 443):
        parser.error("Provide only the HTTPS Lambda service base URL")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,255}", args.table) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", args.function):
        parser.error("Provide the explicit deployed table and function names")
    if args.region != "ap-southeast-1":
        parser.error("This acceptance run is scoped to Singapore ap-southeast-1")
    marker = "Synthetic AWS check " + uuid4().hex[:12] + ": "
    created, table = [], None
    passed = False
    report = {"scope": "Synthetic AWS apartment acceptance; exact owned IDs only", "stage": "preflight"}
    try:
        token = dotenv_values(args.env_file).get("ADMIN_TOKEN")
        require(bool(token), "ADMIN_TOKEN is missing from the selected local environment file")
        session = boto3.Session(profile_name=args.profile, region_name=args.region)
        config = Config(connect_timeout=5, read_timeout=10, retries={"total_max_attempts": 3, "mode": "standard"}, ignore_configured_endpoint_urls=True)
        verify_binding(session.client("lambda", config=config), args.function, args.table, args.url)
        table = session.resource("dynamodb", config=config).Table(args.table)
        # No collection or private queue listing; prove read permission with one
        # random nonexistent ID before public writes are attempted.
        table.get_item(Key={"id": "apt_" + uuid4().hex}, ConsistentRead=True)
        report["deployment_binding"] = "HTTPS URL and DynamoDB table matched the selected active Lambda"
        report["stage"] = "http_acceptance"
        with httpx.Client(base_url=args.url.rstrip("/"), timeout=35, trust_env=False, follow_redirects=False) as client:
            report.update(exercise_http(client, token, created, marker, expected_storage="dynamodb"))
        report["stage"] = "independent_persistence"
        for receipt in created:
            read_exact(table, receipt, marker)
        report["independent_dynamodb_persistence"] = "strong reads verified both exact synthetic records and final states"
        passed = True
    except Exception as error:
        report.update(failure_details(error))
    finally:
        cleanup = cleanup_owned(table, created, marker) if table is not None else {"created": 0, "deleted": 0, "already_absent": 0, "skipped": 0, "error_types": []}
        report["synthetic_record_cleanup"] = cleanup
        if cleanup["skipped"] or cleanup["error_types"] or cleanup["deleted"] + cleanup["already_absent"] != len(created):
            passed = False
        report["status"] = "passed" if passed else "failed"
        write_report(ROOT / ".tools/aws-deployment-validation.json", report)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
