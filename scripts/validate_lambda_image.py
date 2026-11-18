"""Exercise the Lambda image with isolated fictional tenant accounts via local RIE."""
from __future__ import annotations
import argparse
import base64
import json
from pathlib import Path
import socket
import subprocess
import sys
from threading import Lock
from time import monotonic, sleep
from uuid import uuid4
import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.validate_gcp_deployment import exercise_http, synthetic_inventory, failure_details, require, ValidationError, write_report

OWNER_TOKEN = "local-validation-only-not-a-cloud-token"


class LambdaRuntimeTransport(httpx.BaseTransport):
    """Preserve HTTP API v2 cookies/headers across the real local Lambda handler."""
    def __init__(self, runtime, endpoint):
        self.runtime, self.endpoint = runtime, endpoint
        self._invocation_lock = Lock()

    def handle_request(self, request):
        # One standalone RIE represents one on-demand execution environment.
        # Lambda orchestration supplies additional environments in the cloud;
        # concurrent HTTP posts to this one emulator are not that orchestration.
        with self._invocation_lock:
            return self._invoke(request)

    def _invoke(self, request):
        headers = dict(request.headers)
        headers["x-forwarded-proto"] = "https"
        event = {"version": "2.0", "routeKey": "$default", "rawPath": request.url.path,
            "rawQueryString": request.url.query.decode("ascii"), "headers": headers,
            "requestContext": {"http": {"method": request.method, "path": request.url.path,
                "sourceIp": "127.0.0.1", "protocol": "HTTP/1.1"}, "domainName": "localhost"},
            "isBase64Encoded": False}
        if request.content:
            event["body"] = request.content.decode("utf-8")
        if request.headers.get("cookie"):
            event["cookies"] = [part.strip() for part in request.headers["cookie"].split(";") if part.strip()]
        response = self.runtime.post(self.endpoint, json=event)
        response.raise_for_status()
        payload = response.json()
        require(isinstance(payload, dict) and isinstance(payload.get("statusCode"), int), "Local Lambda returned a runtime error")
        output_headers = list(payload.get("headers", {}).items())
        output_headers.extend(("set-cookie", cookie) for cookie in payload.get("cookies", []))
        body = payload.get("body", "")
        content = base64.b64decode(body) if payload.get("isBase64Encoded") else body.encode("utf-8")
        return httpx.Response(payload["statusCode"], headers=output_headers, content=content, request=request)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="ticketpilot-aws-lambda:local")
    parser.add_argument("--port", type=int, default=9000)
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("Use a nonprivileged local port")
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", args.port))
        except OSError:
            parser.error("Validation port is occupied; select another --port")
    name = "ticketpilot-lambda-validation-" + uuid4().hex[:10]
    inventory = synthetic_inventory()
    command = ["docker", "run", "--rm", "-d", "--name", name, "--read-only", "--tmpfs", "/tmp:rw,size=128m", "--memory", "1g",
        "-p", f"127.0.0.1:{args.port}:8080", "-e", "STORAGE_MODE=sqlite", "-e", "SQLITE_PATH=/tmp/validation.db",
        "-e", "LLM_PROVIDER=none", "-e", "AWS_EC2_METADATA_DISABLED=true", "-e", "ADMIN_TOKEN=" + OWNER_TOKEN,
        "-e", "METRICS_TOKEN=local-validation-only-metrics", "-e", "APARTMENT_UNITS=1,2,3,4,5,6,7,8", args.image]
    started = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    require(started.returncode == 0, "Local Lambda container could not start; no test access codes were printed")
    container_id, created = started.stdout.strip(), []
    report = {"runtime": "built Linux Lambda image via local emulator", "root_filesystem": "read-only; temporary state under /tmp",
        "aws_and_bedrock_calls": "none; isolated fictional SQLite and tenant configuration",
        "emulator_invocation_model": "one serialized invocation per local RIE execution environment"}
    passed = False
    try:
        seeded = subprocess.run(["docker", "exec", "-i", container_id, "python", "-m", "ticketpilot.tenant_accounts", "apply", "--credentials-stdin"],
            cwd=ROOT, input=json.dumps(inventory), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
        require(seeded.returncode == 0, "Local fictional tenant provisioning failed; no accounts were printed")
        with httpx.Client(timeout=35, trust_env=False) as runtime:
            endpoint = f"http://127.0.0.1:{args.port}/2015-03-31/functions/function/invocations"
            with httpx.Client(base_url="https://localhost", transport=LambdaRuntimeTransport(runtime, endpoint), follow_redirects=False) as app:
                deadline = monotonic() + 75
                while True:
                    try:
                        if app.get("/health").status_code == 200: break
                    except httpx.HTTPError:
                        pass
                    require(monotonic() < deadline, "Local Lambda runtime did not become ready")
                    sleep(1)
                report.update(exercise_http(app, OWNER_TOKEN, created, "Synthetic Lambda check " + uuid4().hex[:12] + ": ",
                                           expected_storage="sqlite", tenant_accounts=inventory))
                report["concurrent_updates"] = "serialized same-version updates yielded one success and one conflict; concurrent CAS is tested separately on ASGI/Firestore/kind"
                owner = {"X-Admin-Token": OWNER_TOKEN, "Cookie": ""}
                require(app.get("/api/tickets", headers={"Cookie": ""}).status_code == 401, "Legacy owner access was allowed anonymously")
                ticket = {"title": "Synthetic Lambda validation outage", "text": "Production API down with HTTP503 server errors for all synthetic customers."}
                result = app.post("/api/tickets", json=ticket, headers=owner)
                require(result.status_code == 201, "Legacy ticket creation failed")
                ticket_id = result.json()["id"]
                result = app.patch("/api/tickets/" + ticket_id, json={"status": "resolved"}, headers=owner)
                require(result.status_code == 200 and result.json().get("resolved_at"), "Legacy owner resolution failed")
                require(app.delete("/api/tickets/" + ticket_id, headers=owner).status_code == 204, "Legacy synthetic cleanup failed")
                report["owner_workflow"] = "legacy synthetic create/resolve/delete passed; tenant session grants no manager role"
        passed = True
    except Exception as error:
        report.update(failure_details(error))
    finally:
        stopped = subprocess.run(["docker", "stop", "--time", "5", container_id], cwd=ROOT, capture_output=True, text=True, timeout=30)
        report["validation_container_cleanup"] = "removed disposable local container/data" if stopped.returncode == 0 else "failed"
        passed = passed and stopped.returncode == 0
        report["status"] = "passed" if passed else "failed"
        write_report(ROOT / ".tools/lambda-validation.json", report)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
