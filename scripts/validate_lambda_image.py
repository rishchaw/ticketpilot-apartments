"""Exercise the built Lambda image through its local Runtime Interface Emulator."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import socket
import subprocess
from time import monotonic, sleep
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
OWNER_TOKEN = "local-validation-only-not-a-cloud-token"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="ticketpilot-aws-lambda:local")
    parser.add_argument("--port", type=int, default=9000)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Use a nonprivileged local port")
    with socket.socket() as port_check:
        try:
            port_check.bind(("127.0.0.1", args.port))
        except OSError:
            raise SystemExit("Validation port is occupied; select a different --port")
    name = "ticketpilot-lambda-validation-" + uuid4().hex[:10]
    command = [
        "docker", "run", "--rm", "-d", "--name", name,
        "--read-only", "--tmpfs", "/tmp:rw,size=128m", "--memory", "1g",
        "-p", f"127.0.0.1:{args.port}:8080",
        "-e", "STORAGE_MODE=sqlite", "-e", "SQLITE_PATH=/tmp/validation.db",
        "-e", "LLM_PROVIDER=none", "-e", "AWS_EC2_METADATA_DISABLED=true",
        "-e", "ADMIN_TOKEN=" + OWNER_TOKEN,
        "-e", "METRICS_TOKEN=local-validation-only-metrics", args.image,
    ]
    started = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if started.returncode:
        raise SystemExit(started.stderr)
    container_id = started.stdout.strip()
    report = {}
    try:
        with httpx.Client(timeout=30, trust_env=False) as client:
            url = f"http://127.0.0.1:{args.port}/2015-03-31/functions/function/invocations"
            def invoke(method, path, body=None, owner=False, ticket_key=None):
                headers = {"host": "localhost", "content-type": "application/json"}
                if owner:
                    headers["x-admin-token"] = OWNER_TOKEN
                if ticket_key:
                    headers["x-ticket-key"] = ticket_key
                event = {
                    "version": "2.0", "routeKey": "$default", "rawPath": path,
                    "rawQueryString": "", "headers": headers,
                    "requestContext": {"http": {"method": method, "path": path, "sourceIp": "127.0.0.1", "protocol": "HTTP/1.1"}},
                    "isBase64Encoded": False,
                }
                if body is not None:
                    event["body"] = json.dumps(body)
                response = client.post(url, json=event)
                response.raise_for_status()
                payload = response.json()
                if "statusCode" not in payload:
                    raise RuntimeError("Lambda runtime error: " + json.dumps(payload))
                return payload
            deadline = monotonic() + 75
            while True:
                try:
                    health = invoke("GET", "/health")
                    break
                except (httpx.ConnectError, httpx.ReadError):
                    if monotonic() >= deadline:
                        raise RuntimeError("Local Lambda runtime did not become ready")
                    sleep(1)
            assert health["statusCode"] == 200
            assert json.loads(health["body"])["storage_mode"] == "sqlite"
            assert invoke("GET", "/")["statusCode"] == 200
            assert invoke("GET", "/api/tickets")["statusCode"] == 401
            ticket = {"title": "Synthetic Lambda validation outage", "text": "Production API down with HTTP 503 server errors for all synthetic customers."}
            analysis = invoke("POST", "/api/analyze", ticket)
            assert analysis["statusCode"] == 200
            answer = json.loads(analysis["body"])
            assert answer["answer_mode"] == "retrieval"
            assert "KB-007" in {source["id"] for source in answer["sources"]}
            created = invoke("POST", "/api/tickets", ticket, owner=True)
            assert created["statusCode"] == 201
            ticket_id = json.loads(created["body"])["id"]
            changed = invoke("PATCH", "/api/tickets/" + ticket_id, {"status": "resolved"}, owner=True)
            assert changed["statusCode"] == 200
            assert json.loads(changed["body"])["resolved_at"]
            assert invoke("DELETE", "/api/tickets/" + ticket_id, owner=True)["statusCode"] == 204
            apartment = invoke("POST", "/api/apartments/concerns", {"unit": "1", "category": "water", "title": "Synthetic water report", "description": "Walang tubig sa kusina. Synthetic Lambda validation only.", "language": "fil"})
            assert apartment["statusCode"] == 201
            receipt = json.loads(apartment["body"])
            apartment_path = "/api/apartments/concerns/" + receipt["ticket"]["id"]
            assert invoke("GET", apartment_path)["statusCode"] == 404
            assert invoke("GET", apartment_path, ticket_key=receipt["tracking_key"])["statusCode"] == 200
            assert invoke("GET", "/api/apartments/manage/concerns")["statusCode"] == 401
            changed = invoke("PATCH", "/api/apartments/manage/concerns/" + receipt["ticket"]["id"], {"version": 1, "status": "resolved", "priority": "high", "message": "Synthetic update", "internal_note": "Private synthetic note"}, owner=True)
            assert changed["statusCode"] == 200
            public = invoke("GET", apartment_path, ticket_key=receipt["tracking_key"])
            assert json.loads(public["body"])["status"] == "resolved"
            assert "Private synthetic note" not in public["body"]
            report = {
                "apartment_workflow": "tenant intake, private tracking, manager update and private-note isolation passed",
                "runtime": "built Linux Lambda image via local emulator",
                "root_filesystem": "read-only; temporary state under /tmp",
                "website_and_health": "passed",
                "public_analysis": "classifier and cited retrieval passed",
                "anonymous_owner_access": "denied",
                "owner_workflow": "create, resolve, delete passed",
                "aws_and_bedrock_calls": "none; synthetic local configuration",
            }
    finally:
        subprocess.run(["docker", "stop", "--time", "5", container_id], cwd=ROOT, check=True, capture_output=True)
    (ROOT / ".tools/lambda-validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()