"""Validate only this run's synthetic tenant concerns in a deployed GCP service.

Reads the manager token locally, never prints credential values, and cleans only
known IDs whose exact synthetic titles/kind still match. No collection listing,
real tenant record updates, building notice writes, AWS calls or paid AI requests.
The --url and --project must identify the same deployment.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = "ticketpilot_apartment_tickets"


class ValidationError(Exception):
    """A fixed, safe validation message that contains no credentials or records."""


@dataclass
class ConcernReceipt:
    record_id: str
    title: str
    key: str = field(default="", repr=False)
    version: int = 1
    status: str = "received"


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def expect(response, status, message):
    require(response.status_code == status, message + " (HTTP " + str(response.status_code) + ")")
    return response


def tracking(client, concern):
    response = client.get("/api/apartments/concerns/" + concern.record_id, headers={"X-Ticket-Key": concern.key})
    expect(response, 200, "Private concern tracking failed")
    value = response.json()
    require(value.get("id") == concern.record_id and value.get("title") == concern.title, "Tracking returned an unexpected concern")
    require(value.get("version") == concern.version and value.get("status") == concern.status, "Concern version/status did not persist")
    require(not {"tracking_hash", "tracking_key", "internal_notes", "assigned_to"}.intersection(value), "Private manager/storage fields leaked into a tenant response")
    return value


def exercise_http(client, manager_token, created, title_prefix, expected_storage="firestore"):
    owner = {"X-Admin-Token": manager_token}
    health = expect(client.get("/health"), 200, "Service health failed").json()
    require(health.get("storage_mode") == expected_storage, "Service is not using the expected durable storage")
    for path in ("/tenant", "/manager"):
        expect(client.get(path), 200, "Apartment page unavailable")
    config = expect(client.get("/api/apartments/config"), 200, "Apartment configuration unavailable").json()
    require(config.get("intake_available") is True, "Apartment intake is disabled")
    units = config.get("units", [])
    require(bool(units), "No apartment units are configured")
    # Prove the selected local token matches before creating any records. This
    # random nonexistent ID neither lists a queue nor reads a private concern.
    manager_probe = client.get("/api/apartments/manage/concerns/apt_" + uuid4().hex, headers=owner)
    if manager_probe.status_code == 401:
        raise ValidationError("The selected local ADMIN_TOKEN does not match the service manager token; update the selected local environment file to match the configured cloud secret before rerunning")
    expect(manager_probe, 404, "Manager authorization preflight failed; no synthetic concerns were created")
    demo = expect(client.post("/api/analyze", json={"title": "Synthetic API validation", "text": "Production API is unreachable with HTTP 503 server errors. Synthetic validation only."}), 200, "Local CPU classifier/retrieval failed").json()
    require(demo.get("answer_mode") == "retrieval" and bool(demo.get("sources")), "Public inference did not remain retrieval-only")

    def create(category, unit, suffix):
        title = title_prefix + suffix
        response = expect(client.post("/api/apartments/concerns", json={"unit": unit, "category": category, "title": title,
            "description": "Synthetic deployment validation only. No real tenant issue, bill, payment or maintenance request.", "language": "fil"}), 201, "Synthetic concern creation failed")
        value = response.json()
        record = value.get("ticket", {})
        record_id = record.get("id", "")
        require(isinstance(record_id, str) and bool(re.fullmatch(r"apt_[0-9a-f]{32}", record_id)), "Creation did not return a valid concern ID")
        concern = ConcernReceipt(record_id, title)
        # Retain the known ID immediately so partial failures can still be cleaned.
        created.append(concern)
        require(record.get("title") == title, "Created concern title differs from its synthetic marker")
        key = value.get("tracking_key", "")
        require(isinstance(key, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{32,128}", key)), "Creation did not return a valid private tracking key")
        concern.key = key
        require(record.get("version") == 1 and record.get("status") == "received", "Initial concern state is invalid")
        return concern

    first = create("water", units[0], "water concern")
    second = create("billing", units[min(1, len(units) - 1)], "billing concern")
    require(first.record_id != second.record_id and first.key != second.key, "Concern IDs/keys are not distinct")
    expect(client.get("/api/apartments/manage/concerns"), 401, "Manager queue was accessible anonymously")
    expect(client.get("/api/apartments/concerns/" + first.record_id), 404, "Concern was accessible without its private key")
    expect(client.get("/api/apartments/concerns/" + first.record_id, headers={"X-Ticket-Key": second.key}), 404, "Another concern's key granted access")
    expect(client.post("/api/apartments/concerns/" + first.record_id + "/replies", headers={"X-Ticket-Key": second.key}, json={"version": 1, "message": "Synthetic cross-key denial check"}), 404, "Another concern's key could add a reply")
    tracking(client, first)

    endpoint = "/api/apartments/manage/concerns/" + first.record_id
    private_note = "Private synthetic validator note; must never appear in a tenant response."
    response = expect(client.patch(endpoint, headers=owner, json={"version": 1, "status": "in_progress", "priority": "high",
        "message": "Synthetic manager update saved.", "internal_note": private_note}), 200, "Manager update failed")
    first.version = response.json()["version"]
    first.status = "in_progress"
    public = tracking(client, first)
    require(private_note not in json.dumps(public), "A private manager note leaked to tenant tracking")

    expected_version = first.version
    race_messages = ["Synthetic concurrent update A.", "Synthetic concurrent update B."]
    def race(message):
        return client.patch(endpoint, headers=owner, json={"version": expected_version, "status": "resolved", "priority": "high", "message": message})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(race, race_messages))
    require(sorted(response.status_code for response in responses) == [200, 409], "Same-version concurrent updates did not produce exactly one success and one conflict")
    winner = next(response.json() for response in responses if response.status_code == 200)
    first.version = winner["version"]
    first.status = "resolved"
    public = tracking(client, first)
    stored_messages = [update["text"] for update in public.get("updates", [])]
    require(sum(message in stored_messages for message in race_messages) == 1, "Concurrent update messages were lost or duplicated")

    response = expect(client.post("/api/apartments/concerns/" + first.record_id + "/replies", headers={"X-Ticket-Key": first.key},
        json={"version": first.version, "message": "Synthetic tenant reply: reopen this validation concern.", "reopen": True}), 200, "Tenant reply/reopening failed")
    first.version = response.json()["version"]
    first.status = "received"
    tracking(client, first)
    manager_record = expect(client.get(endpoint, headers=owner), 200, "Manager could not read its synthetic concern").json()
    require(any(note.get("text") == private_note for note in manager_record.get("internal_notes", [])), "Private manager note did not persist")
    second_endpoint = "/api/apartments/manage/concerns/" + second.record_id
    response = expect(client.patch(second_endpoint, headers=owner, json={"version": 1, "status": "resolved", "priority": "normal", "message": "Synthetic validation concern closed."}), 200, "Second synthetic concern could not be resolved")
    second.version = response.json()["version"]
    second.status = "resolved"
    return {"health_and_pages": "passed", "cpu_classifier_and_retrieval": "passed; no paid generation requested",
            "synthetic_tenant_intake": "two concerns saved", "private_tracking_and_cross_key_denial": "passed",
            "manager_private_note_isolation": "passed", "concurrent_updates": "one success and one conflict",
            "tenant_reply_and_reopening": "passed", "existing_records_and_building_notices": "not listed or modified"}


def write_report(destination, report):
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


def failure_details(exc):
    value = {"error_type": type(exc).__name__}
    if isinstance(exc, ValidationError):
        value["failure"] = str(exc)
    elif isinstance(exc, httpx.HTTPStatusError):
        value["failure"] = "HTTP verification failed (status " + str(exc.response.status_code) + ")"
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--database", default=os.getenv("FIRESTORE_DATABASE", "(default)"))
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args(argv)
    parsed = urlparse(args.url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        parser.error("Provide only the HTTPS service base URL")
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", args.project):
        parser.error("Provide a valid Google Cloud project ID")
    if args.database != "(default)" and not re.fullmatch(r"[a-z][a-z0-9-]{2,61}[a-z0-9]", args.database):
        parser.error("Provide a valid Firestore database ID")
    report = {"scope": "Synthetic deployed apartment verification; only this run's exact IDs may be cleaned"}
    created = []
    marker = "Synthetic GCP check " + uuid4().hex[:12] + ": "
    database = None
    passed = False
    try:
        token = dotenv_values(args.env_file).get("ADMIN_TOKEN")
        require(bool(token), "ADMIN_TOKEN is missing from the selected local environment file")
        from google.cloud import firestore
        database = firestore.Client(project=args.project, database=args.database)
        # A random nonexistent ID checks ADC/database read access before HTTP writes;
        # it never lists a collection or reads another tenant's records.
        database.collection(COLLECTION).document("apt_" + uuid4().hex).get(timeout=10)
        with httpx.Client(base_url=args.url.rstrip("/"), timeout=30, follow_redirects=False, trust_env=False) as client:
            report.update(exercise_http(client, token, created, marker))
            for concern in created:
                snapshot = database.collection(COLLECTION).document(concern.record_id).get(timeout=10)
                value = snapshot.to_dict() if snapshot.exists else {}
                require(value.get("id") == concern.record_id and value.get("title") == concern.title and concern.title.startswith(marker), "Independent Firestore read did not match this validation run")
                require(value.get("kind") == "apartment_ticket" and value.get("queue") == "apartment_tickets", "Independent Firestore record kind is incorrect")
                require(value.get("version") == concern.version and value.get("status") == concern.status, "Independent Firestore state did not match the HTTP workflow")
                require(value.get("tracking_hash") == hashlib.sha256(concern.key.encode()).hexdigest(), "Firestore did not persist the tracking-key hash")
            report["independent_firestore_persistence"] = "verified through ADC by exact synthetic document IDs"
            passed = True
    except Exception as exc:
        report.update(failure_details(exc))
    finally:
        cleanup = {"created": len(created), "deleted": 0, "already_absent": 0, "skipped": 0}
        cleanup_errors = []
        if database is not None:
            for concern in created:
                try:
                    reference = database.collection(COLLECTION).document(concern.record_id)
                    snapshot = reference.get(field_paths=["id", "title", "kind", "queue"], timeout=10)
                    if not snapshot.exists:
                        cleanup["already_absent"] += 1
                        continue
                    value = snapshot.to_dict()
                    if value.get("id") != concern.record_id or value.get("title") != concern.title or not concern.title.startswith(marker) or value.get("kind") != "apartment_ticket" or value.get("queue") != "apartment_tickets":
                        cleanup["skipped"] += 1
                        continue
                    # Rechecking the update timestamp avoids deleting a changed
                    # document between ownership validation and deletion.
                    reference.delete(option=firestore.LastUpdateOption(snapshot.update_time), timeout=10)
                    require(not reference.get(timeout=10).exists, "Synthetic document cleanup was not confirmed")
                    cleanup["deleted"] += 1
                except Exception as exc:
                    cleanup_errors.append(type(exc).__name__)
        report["synthetic_document_cleanup"] = cleanup
        if cleanup_errors:
            report["cleanup_error_types"] = cleanup_errors
        if cleanup_errors or cleanup["skipped"] or cleanup["deleted"] + cleanup["already_absent"] != len(created):
            passed = False
        report["status"] = "passed" if passed else "failed"
        write_report(ROOT / ".tools/gcp-deployment-validation.json", report)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
