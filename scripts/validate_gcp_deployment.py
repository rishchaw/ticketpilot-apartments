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
import secrets
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
    tenant_id: str = field(default="", repr=False)
    username: str = field(default="", repr=False)


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def expect(response, status, message):
    require(response.status_code == status, message + " (HTTP " + str(response.status_code) + ")")
    return response


def validate_inventory(value):
    """Validate in-process only. Never include inventory values in diagnostics."""
    require(isinstance(value, dict) and value.get("schema_version") == 1, "Unexpected private tenant inventory schema")
    accounts = value.get("accounts")
    require(isinstance(accounts, list) and len(accounts) == 8, "Acceptance requires the existing eight-account inventory")
    for account in accounts:
        require(isinstance(account, dict), "Invalid private tenant account")
        require(isinstance(account.get("tenant_id"), str) and bool(re.fullmatch(r"[0-9a-f]{32}", account["tenant_id"])), "Invalid private tenant identity")
        require(isinstance(account.get("username"), str) and bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,63}", account["username"])), "Invalid private tenant username")
        require(isinstance(account.get("unit"), str) and 1 <= len(account["unit"]) <= 40 and account["unit"] == account["unit"].strip(), "Invalid private tenant unit")
        require(isinstance(account.get("password"), str) and 15 <= len(account["password"]) <= 128, "Restore the private initial credentials or provide a current authorized inventory; validation never resets passwords")
    require(len({a["tenant_id"] for a in accounts}) == 8 and len({a["username"] for a in accounts}) == 8, "Private tenant identities/usernames must be distinct")
    return value


def load_tenant_inventory(path):
    try:
        require(not path.is_symlink() and path.is_file() and path.stat().st_size <= 65536, "Restore the private tenant credential inventory before live acceptance")
        return validate_inventory(json.loads(path.read_text(encoding="utf-8-sig")))
    except (OSError, UnicodeError, ValueError) as error:
        raise ValidationError("Private tenant inventory is unreadable; no accounts were reset or created") from error


def synthetic_inventory():
    """Eight isolated fictional identities, never real tenant credentials."""
    return {"schema_version": 1, "accounts": [
        {"tenant_id": uuid4().hex, "username": "unit-" + str(i), "unit": str(i), "password": secrets.token_urlsafe(24)}
        for i in range(1, 9)]}


class TenantHTTP:
    """Separate cookie/CSRF state over one transport; never store passwords."""
    def __init__(self, client, principal, cookies, csrf_token):
        self.client, self.principal = client, principal
        self.cookies, self.csrf_token = dict(cookies), csrf_token

    def request(self, method, path, *, headers=None, csrf=True, **kwargs):
        selected = {"Cookie": "; ".join(name + "=" + value for name, value in sorted(self.cookies.items()))}
        if csrf and method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            selected["X-CSRF-Token"] = self.csrf_token
        selected.update(headers or {})
        return self.client.request(method, path, headers=selected, **kwargs)

    def get(self, path, **kwargs): return self.request("GET", path, **kwargs)
    def post(self, path, **kwargs): return self.request("POST", path, **kwargs)


def tenant_login(client, account, *, register=True):
    response = expect(client.post("/api/tenant/login", headers={"Cookie": "", "X-TicketPilot-Login": "1"},
        json={"username": account["username"], "password": account["password"]}), 200, "Tenant sign-in failed; provide current credentials without rotating an account for validation")
    value = response.json()
    principal, csrf = value.get("tenant", {}), value.get("csrf_token", "")
    require(principal.get("id") == account["tenant_id"] and principal.get("username") == account["username"] and principal.get("unit") == account["unit"], "Tenant session identity differs from its private inventory")
    require(isinstance(csrf, str) and 24 <= len(csrf) <= 128 and bool(response.cookies), "Tenant sign-in did not create a protected session")
    cookies = response.headers.get_list("set-cookie")
    require(bool(cookies) and all("httponly" in entry.lower() and "samesite=strict" in entry.lower() and "path=/" in entry.lower() for entry in cookies), "Tenant session cookie protections are missing")
    if str(client.base_url).startswith("https://"):
        require(all("; secure" in entry.lower() for entry in cookies), "HTTPS tenant cookies must be Secure")
    require(not {"password", "password_hash", "credential_version", "session_token"}.intersection(value), "Tenant sign-in exposed credential fields")
    session = TenantHTTP(client, principal, dict(response.cookies.items()), csrf)
    if register:
        sessions = getattr(client, "_ticketpilot_tenant_sessions", {})
        sessions[account["username"]] = session
        client._ticketpilot_tenant_sessions = sessions
    return session


def capture_sessions(client):
    return dict(getattr(client, "_ticketpilot_tenant_sessions", {}))


def restore_sessions(client, sessions):
    """Rebind opaque sessions after restart; do not silently reauthenticate."""
    restored = {}
    for username, prior in sessions.items():
        session = TenantHTTP(client, prior.principal, prior.cookies, prior.csrf_token)
        value = expect(session.get("/api/tenant/session"), 200, "Tenant session did not persist after application restart").json()
        require(value.get("tenant") == prior.principal, "Persisted tenant identity changed")
        session.csrf_token = value["csrf_token"]
        restored[username] = session
    client._ticketpilot_tenant_sessions = restored
    return restored


def logout_sessions(client):
    errors = []
    for session in capture_sessions(client).values():
        try:
            expect(session.post("/api/tenant/logout"), 204, "Validation tenant session could not be closed")
            expect(session.get("/api/tenant/session"), 401, "Logged-out opaque session remained valid")
        except Exception as error:
            errors.append(failure_details(error))
    client._ticketpilot_tenant_sessions = {}
    if errors:
        failure = ValidationError("One or more validation tenant sessions could not be revoked")
        failure.tenant_session_cleanup = {"status": "failed", "failures": errors}
        raise failure


def tracking(client, concern):
    session = client if isinstance(client, TenantHTTP) else capture_sessions(client).get(concern.username)
    require(session is not None, "Restore the owning tenant session before tracking a synthetic concern")
    response = session.get("/api/apartments/concerns/" + concern.record_id, headers={"X-Ticket-Key": concern.key})
    expect(response, 200, "Private concern tracking failed")
    value = response.json()
    require(value.get("id") == concern.record_id and value.get("title") == concern.title, "Tracking returned an unexpected concern")
    require(value.get("version") == concern.version and value.get("status") == concern.status, "Concern version/status did not persist")
    require(not {"tracking_hash", "tracking_key", "internal_notes", "assigned_to", "tenant_id", "password_hash"}.intersection(value), "Private manager/storage fields leaked into a tenant response")
    return value


def exercise_http(client, manager_token, created, title_prefix, expected_storage="firestore", *, tenant_accounts, keep_sessions=False):
    inventory = validate_inventory(tenant_accounts)
    accounts = inventory["accounts"][:2]
    owner = {"X-Admin-Token": manager_token, "Cookie": ""}
    anonymous = {"Cookie": ""}
    health = expect(client.get("/health", headers=anonymous), 200, "Service health failed").json()
    require(health.get("storage_mode") == expected_storage, "Service is not using the expected durable storage")
    for path in ("/", "/tenant"):
        response = client.get(path, headers=anonymous)
        require(response.status_code in {302, 303, 307, 308} and response.headers.get("location", "").split("#", 1)[0] == "/tenant/login", "Anonymous tenant portal did not redirect to login")
    expect(client.get("/tenant/login", headers=anonymous), 200, "Tenant login page unavailable")
    expect(client.get("/manager", headers=anonymous), 200, "Manager login page unavailable")
    expect(client.get("/api/tenant/session", headers=anonymous), 401, "Anonymous tenant session was accepted")
    expect(client.get("/api/apartments/config", headers=anonymous), 401, "Apartment configuration was accessible anonymously")
    # Prove the selected manager token before synthetic tenant writes. This exact
    # random nonexistent ID neither lists a queue nor reads a private concern.
    manager_probe = client.get("/api/apartments/manage/concerns/apt_" + uuid4().hex, headers=owner)
    if manager_probe.status_code == 401:
        raise ValidationError("The selected local ADMIN_TOKEN does not match the service manager token; update the selected private environment file before rerunning")
    expect(manager_probe, 404, "Manager authorization preflight failed; no synthetic concerns were created")
    config = expect(client.get("/api/apartments/config", headers=owner), 200, "Manager apartment configuration unavailable").json()
    require(config.get("intake_available") is True and bool(config.get("units")) and all(a["unit"] in config["units"] for a in inventory["accounts"]), "Configured apartment units do not match the private account inventory")
    demo = expect(client.post("/api/analyze", headers=anonymous, json={"title": "Synthetic API validation", "text": "Production API is unreachable with HTTP 503 server errors. Synthetic validation only."}), 200, "Local CPU classifier/retrieval failed").json()
    require(demo.get("answer_mode") == "retrieval" and bool(demo.get("sources")), "Public inference did not remain retrieval-only")
    expect(client.post("/api/tenant/login", headers={**anonymous, "X-TicketPilot-Login": "1"}, json={"username": accounts[0]["username"], "password": "incorrect-validation-password"}), 401, "Incorrect tenant password was accepted")
    passed = False
    try:
        first_session, second_session = (tenant_login(client, account) for account in accounts)
        for session in (first_session, second_session):
            expect(session.get("/tenant"), 200, "Authenticated tenant portal unavailable")
            scoped = expect(session.get("/api/apartments/config"), 200, "Authenticated tenant configuration unavailable").json()
            require(scoped.get("units") == [session.principal["unit"]], "Tenant configuration did not bind the assigned unit")
        def create(session, category, suffix):
            title = title_prefix + suffix
            body = {"unit": session.principal["unit"], "category": category, "title": title,
                "description": "Synthetic deployment validation only. No real tenant issue, bill, payment or maintenance request.", "language": "fil"}
            response = expect(session.post("/api/apartments/concerns", json=body), 201, "Synthetic concern creation failed")
            value, record = response.json(), response.json().get("ticket", {})
            record_id = record.get("id", "")
            require(isinstance(record_id, str) and bool(re.fullmatch(r"apt_[0-9a-f]{32}", record_id)), "Creation did not return a valid concern ID")
            concern = ConcernReceipt(record_id, title, tenant_id=session.principal["id"], username=session.principal["username"])
            created.append(concern)  # Retain exact ID before any further assertion.
            require(record.get("title") == title and record.get("unit") == session.principal["unit"], "Created concern differs from its owning tenant")
            key = value.get("tracking_key", "")
            require(isinstance(key, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{32,128}", key)), "Creation did not return a valid private tracking key")
            concern.key = key
            require(record.get("version") == 1 and record.get("status") == "received", "Initial concern state is invalid")
            return concern
        forged = {"unit": next((a["unit"] for a in inventory["accounts"] if a["unit"] != accounts[0]["unit"]), "unassigned-unit"), "category": "water", "title": title_prefix + "rejected unit spoof", "description": "Synthetic rejected submission only."}
        expect(first_session.post("/api/apartments/concerns", json=forged), 403, "Tenant could submit for another unit")
        forged["unit"] = first_session.principal["unit"]
        expect(first_session.post("/api/apartments/concerns", csrf=False, json=forged), 403, "Tenant write without CSRF token was accepted")
        expect(client.post("/api/apartments/concerns", headers=owner, json=forged), 401, "Manager token alone could impersonate a tenant")
        first = create(first_session, "water", "water concern")
        second = create(second_session, "billing", "billing concern")
        require(first.record_id != second.record_id and first.key != second.key, "Concern IDs/keys are not distinct")
        expect(client.get("/api/apartments/manage/concerns", headers=anonymous), 401, "Manager queue was accessible anonymously")
        expect(first_session.get("/api/apartments/manage/concerns"), 401, "Tenant session granted manager access")
        expect(client.get("/api/apartments/concerns/" + first.record_id, headers={**anonymous, "X-Ticket-Key": first.key}), 401, "Tracking key bypassed tenant login")
        expect(first_session.get("/api/apartments/concerns/" + first.record_id), 404, "Concern was accessible without its private key")
        expect(first_session.get("/api/apartments/concerns/" + first.record_id, headers={"X-Ticket-Key": second.key}), 404, "Another concern's key granted access")
        expect(second_session.get("/api/apartments/concerns/" + first.record_id, headers={"X-Ticket-Key": first.key}), 404, "Another tenant's valid tracking key bypassed ownership")
        expect(second_session.post("/api/apartments/concerns/" + first.record_id + "/replies", headers={"X-Ticket-Key": first.key}, json={"version": 1, "message": "Synthetic stolen-key denial check"}), 404, "Another tenant's valid tracking key could add a reply")
        tracking(client, first)
        endpoint = "/api/apartments/manage/concerns/" + first.record_id
        private_note = "Private synthetic validator note; must never appear in a tenant response."
        response = expect(client.patch(endpoint, headers=owner, json={"version": 1, "status": "in_progress", "priority": "high", "message": "Synthetic manager update saved.", "internal_note": private_note}), 200, "Manager update failed")
        first.version, first.status = response.json()["version"], "in_progress"
        require(private_note not in json.dumps(tracking(client, first)), "A private manager note leaked to tenant tracking")
        expected_version = first.version
        race_messages = ["Synthetic concurrent update A.", "Synthetic concurrent update B."]
        def race(message):
            return client.patch(endpoint, headers=owner, json={"version": expected_version, "status": "resolved", "priority": "high", "message": message})
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(race, race_messages))
        require(sorted(r.status_code for r in responses) == [200, 409], "Same-version concurrent updates did not produce exactly one success and one conflict")
        first.version, first.status = next(r.json()["version"] for r in responses if r.status_code == 200), "resolved"
        messages = [update["text"] for update in tracking(client, first).get("updates", [])]
        require(sum(message in messages for message in race_messages) == 1, "Concurrent update messages were lost or duplicated")
        response = expect(first_session.post("/api/apartments/concerns/" + first.record_id + "/replies", headers={"X-Ticket-Key": first.key}, json={"version": first.version, "message": "Synthetic tenant reply: reopen this validation concern.", "reopen": True}), 200, "Tenant reply/reopening failed")
        first.version, first.status = response.json()["version"], "received"
        tracking(client, first)
        manager_record = expect(client.get(endpoint, headers=owner), 200, "Manager could not read its synthetic concern").json()
        require(any(note.get("text") == private_note for note in manager_record.get("internal_notes", [])), "Private manager note did not persist")
        response = expect(client.patch("/api/apartments/manage/concerns/" + second.record_id, headers=owner, json={"version": 1, "status": "resolved", "priority": "normal", "message": "Synthetic validation concern closed."}), 200, "Second synthetic concern could not be resolved")
        second.version, second.status = response.json()["version"], "resolved"
        disposable_session = tenant_login(client, accounts[1], register=False)
        expect(disposable_session.post("/api/tenant/logout"), 204, "Tenant logout failed")
        expect(disposable_session.get("/api/tenant/session"), 401, "Logout did not revoke the persisted session")
        passed = True
        return {"health_and_pages": "anonymous portal redirected; authenticated pages passed", "cpu_classifier_and_retrieval": "passed; no paid generation requested",
            "tenant_authentication": "two existing accounts; wrong-password and anonymous denial; scoped units; logout revocation",
            "synthetic_tenant_intake": "two concerns saved", "tenant_ownership": "another tenant denied even with the correct stolen tracking key",
            "csrf_and_unit_spoofing": "rejected", "private_tracking_and_cross_key_denial": "passed", "manager_private_note_isolation": "passed",
            "concurrent_updates": "one success and one conflict", "tenant_reply_and_reopening": "passed", "existing_records_and_building_notices": "not listed or modified"}
    finally:
        if not (passed and keep_sessions):
            # A failing logout must not hide the actual workflow/transport failure.
            # Only fixed validation messages and error class names enter reports.
            primary_error = sys.exc_info()[1]
            try:
                logout_sessions(client)
            except Exception as cleanup_error:
                if primary_error is None:
                    raise
                primary_error.tenant_session_cleanup = getattr(cleanup_error, "tenant_session_cleanup",
                    {"status": "failed", "failures": [{"error_type": type(cleanup_error).__name__}]})


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
    cleanup = getattr(exc, "tenant_session_cleanup", None)
    if isinstance(cleanup, dict) and cleanup.get("status") == "failed":
        value["tenant_session_cleanup"] = cleanup
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--database", default=os.getenv("FIRESTORE_DATABASE", "(default)"))
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--credentials-file", type=Path, default=ROOT / ".secrets/tenant-credentials.json")
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
        inventory = load_tenant_inventory(args.credentials_file)
        from google.cloud import firestore
        database = firestore.Client(project=args.project, database=args.database)
        # A random nonexistent ID checks ADC/database read access before HTTP writes;
        # it never lists a collection or reads another tenant's records.
        database.collection(COLLECTION).document("apt_" + uuid4().hex).get(timeout=10)
        with httpx.Client(base_url=args.url.rstrip("/"), timeout=30, follow_redirects=False, trust_env=False) as client:
            report.update(exercise_http(client, token, created, marker, tenant_accounts=inventory))
            for concern in created:
                snapshot = database.collection(COLLECTION).document(concern.record_id).get(timeout=10)
                value = snapshot.to_dict() if snapshot.exists else {}
                require(value.get("id") == concern.record_id and value.get("title") == concern.title and concern.title.startswith(marker), "Independent Firestore read did not match this validation run")
                require(value.get("kind") == "apartment_ticket" and value.get("queue") == "apartment_tickets", "Independent Firestore record kind is incorrect")
                require(value.get("version") == concern.version and value.get("status") == concern.status, "Independent Firestore state did not match the HTTP workflow")
                require(value.get("tracking_hash") == hashlib.sha256(concern.key.encode()).hexdigest(), "Firestore did not persist the tracking-key hash")
                require(value.get("tenant_id") == concern.tenant_id, "Firestore did not preserve authenticated tenant ownership")
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
                    snapshot = reference.get(field_paths=["id", "title", "kind", "queue", "tenant_id"], timeout=10)
                    if not snapshot.exists:
                        cleanup["already_absent"] += 1
                        continue
                    value = snapshot.to_dict()
                    if value.get("id") != concern.record_id or value.get("title") != concern.title or not concern.title.startswith(marker) or value.get("kind") != "apartment_ticket" or value.get("queue") != "apartment_tickets" or (concern.tenant_id and value.get("tenant_id") != concern.tenant_id):
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
