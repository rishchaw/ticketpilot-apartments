"""Validate the local Compose app and monitoring stack without cloud API calls."""
from __future__ import annotations
import argparse
import csv
import io
import json
from pathlib import Path
import subprocess
from time import monotonic, sleep
from urllib.parse import urlparse

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def wait_for(client, url, ready=lambda response: response.status_code == 200, seconds=75):
    deadline = monotonic() + seconds
    last = "not contacted"
    while monotonic() < deadline:
        try:
            response = client.get(url)
            last = f"HTTP {response.status_code}"
            if ready(response):
                return response
        except httpx.HTTPError as exc:
            last = type(exc).__name__
        sleep(1)
    raise RuntimeError(f"Service not ready at {url}: {last}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", default="http://127.0.0.1:8080")
    parser.add_argument("--prometheus", default="http://127.0.0.1:9090")
    parser.add_argument("--grafana", default="http://127.0.0.1:3000")
    parser.add_argument("--restart-app", action="store_true", help="Verify persistence by restarting this project's app container")
    args = parser.parse_args()
    for url in (args.app, args.prometheus, args.grafana):
        parsed = urlparse(url)
        if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            parser.error("This validation accepts only local HTTP base URLs")
    values = dotenv_values(ROOT / ".env")
    for key in ("ADMIN_TOKEN", "METRICS_TOKEN", "GRAFANA_ADMIN_PASSWORD"):
        if not values.get(key):
            raise SystemExit(f"Missing {key}; run scripts/setup_local.py first")
    headers = {"X-Admin-Token": values["ADMIN_TOKEN"]}
    report = {}
    with httpx.Client(timeout=10, trust_env=False) as client:
        health = wait_for(client, args.app + "/health").json()
        assert health["storage_mode"] == "sqlite", "Local validation requires SQLite mode"
        report["app_health"] = "ok"
        assert client.get(args.app + "/").status_code == 200
        assert client.get(args.app + "/tenant").status_code == 200
        assert client.get(args.app + "/manager").status_code == 200
        assert client.get(args.app + "/assets/apartments.js").status_code == 200
        assert len(client.get(args.app + "/api/apartments/config").json()["units"]) == 8
        assert client.get(args.app + "/api/apartments/manage/concerns").status_code == 401
        report["apartment_portal"] = "tenant and manager pages available; manager queue requires authentication"
        assert client.get(args.app + "/api/knowledge").json()["total"] == 14
        assert client.get(args.app + "/api/tickets").status_code == 401
        assert client.get(args.app + "/metrics").status_code == 401
        ticket = {"title": "Synthetic local validation outage", "text": "Production API is down and returns HTTP 503 errors for every synthetic customer."}
        response = client.post(args.app + "/api/analyze", json=ticket)
        response.raise_for_status()
        analysis = response.json()
        assert analysis["answer_mode"] == "retrieval"
        assert "KB-007" in {source["id"] for source in analysis["sources"]}
        report["public_analysis"] = "retrieval with expected runbook; no provider request"
        created_id = None
        try:
            response = client.post(args.app + "/api/tickets", headers=headers, json=ticket)
            response.raise_for_status()
            created_id = response.json()["id"]
            response = client.patch(args.app + "/api/tickets/" + created_id, headers=headers, json={"status": "resolved"})
            response.raise_for_status()
            assert response.json()["resolved_at"]
            if args.restart_app:
                subprocess.run(["docker", "compose", "--profile", "local", "restart", "app"], cwd=ROOT, check=True, capture_output=True)
                wait_for(client, args.app + "/health")
            response = client.get(args.app + "/api/tickets", headers=headers)
            response.raise_for_status()
            saved = next(item for item in response.json()["items"] if item["id"] == created_id)
            assert saved["status"] == "resolved"
            exported = client.get(args.app + "/api/export.csv", headers=headers)
            exported.raise_for_status()
            assert created_id in {row["id"] for row in csv.DictReader(io.StringIO(exported.text))}
            report["owner_workflow"] = "create, resolve, list, export"
            report["persistence_after_restart"] = "passed" if args.restart_app else "not requested"
        finally:
            if created_id:
                response = client.delete(args.app + "/api/tickets/" + created_id, headers=headers)
                response.raise_for_status()
                report["validation_ticket_cleanup"] = "deleted only the synthetic ticket created by this run"
        client.post(args.app + "/api/analyze", json=ticket).raise_for_status()
        metrics = client.get(args.app + "/metrics", headers={"Authorization": "Bearer " + values["METRICS_TOKEN"]})
        metrics.raise_for_status()
        assert "ticketpilot_answers_total" in metrics.text
        report["authenticated_metrics"] = "ok"
        wait_for(client, args.prometheus + "/-/ready")
        def scrape_ready(response):
            if response.status_code != 200:
                return False
            targets = response.json().get("data", {}).get("activeTargets", [])
            return any(target.get("labels", {}).get("job") == "ticketpilot" and target.get("health") == "up" for target in targets)
        wait_for(client, args.prometheus + "/api/v1/targets", scrape_ready)
        query = client.get(args.prometheus + "/api/v1/query", params={"query": 'up{job="ticketpilot"}'})
        query.raise_for_status()
        assert query.json()["data"]["result"][0]["value"][1] == "1"
        report["prometheus_scrape"] = "up"
        wait_for(client, args.grafana + "/api/health")
        auth = httpx.BasicAuth("admin", values["GRAFANA_ADMIN_PASSWORD"])
        response = client.get(args.grafana + "/api/dashboards/uid/ticketpilot-aws", auth=auth)
        response.raise_for_status()
        dashboard = response.json()["dashboard"]
        assert len(dashboard["panels"]) == 10
        response = client.get(args.grafana + "/api/datasources/uid/ticketpilot-prometheus/health", auth=auth)
        response.raise_for_status()
        assert response.json()["status"] == "OK"
        report["grafana_dashboard"] = "10 provisioned panels; Prometheus datasource healthy"
        apartment_dashboard = client.get(args.grafana + "/api/dashboards/uid/ticketpilot-apartments", auth=auth)
        apartment_dashboard.raise_for_status()
        assert len(apartment_dashboard.json()["dashboard"]["panels"]) == 6
        report["apartment_grafana_dashboard"] = "6 provisioned apartment workflow/performance panels"
    destination = ROOT / ".tools/local-validation.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()