"""Measure bounded, sequential HTTPS requests to a TicketPilot cloud release."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.cloud import CloudError, REGIONS, context_for, valid_url

CASES = (
    ("health", "GET", "/health", None),
    ("tenant_login_page", "GET", "/tenant/login", None),
    ("it_demo_retrieval", "POST", "/api/analyze", {
        "title": "Production API outage",
        "text": "Production API down with HTTP 503 errors for every customer.",
    }),
)


def request_sample(client, method, path, payload):
    started = time.perf_counter()
    try:
        response = client.request(method, path, json=payload) if payload else client.request(method, path)
        valid = response.status_code == 200
        if valid and path == "/api/analyze":
            value = response.json()
            valid = value.get("answer_mode") == "retrieval" and bool(value.get("sources"))
        return {"ms": round((time.perf_counter() - started) * 1000, 3),
                "status": response.status_code, "valid": bool(valid)}
    except (httpx.HTTPError, ValueError) as error:
        return {"ms": round((time.perf_counter() - started) * 1000, 3),
                "status": None, "valid": False, "error_type": type(error).__name__}


def summarize(samples):
    elapsed = sorted(item["ms"] for item in samples if item["valid"])
    return {
        "requests": len(samples),
        "successes": len(elapsed),
        "failures": len(samples) - len(elapsed),
        "http_statuses": dict(Counter(str(item["status"]) for item in samples)),
        "p50_ms": round(statistics.median(elapsed), 3) if elapsed else None,
        "p95_ms": elapsed[math.ceil(len(elapsed) * 0.95) - 1] if elapsed else None,
        "max_ms": elapsed[-1] if elapsed else None,
        "samples": samples,
    }


def benchmark(client, *, samples, interval):
    endpoints = {}
    for name, method, path, payload in CASES:
        first = request_sample(client, method, path, payload)
        warmup = []
        for _ in range(3):
            time.sleep(interval)
            warmup.append(request_sample(client, method, path, payload))
        measured = []
        for _ in range(samples):
            time.sleep(interval)
            measured.append(request_sample(client, method, path, payload))
        endpoints[name] = {
            "method": method, "path": path,
            "first_observed": first,
            "warmup": summarize(warmup),
            "measured": summarize(measured),
        }
    return endpoints


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=("aws", "gcp"))
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--interval", type=float, default=0.25)
    args = parser.parse_args(argv)
    if not 5 <= args.samples <= 100:
        parser.error("Use 5 through 100 measured requests per endpoint")
    if not math.isfinite(args.interval) or not 0.1 <= args.interval <= 5:
        parser.error("Use a finite interval from 0.1 through 5 seconds")
    context = context_for(ROOT, args.provider, required=True)
    url = valid_url(args.provider, context.get("url"))
    started = datetime.now(timezone.utc).isoformat()
    with httpx.Client(base_url=url, timeout=45, follow_redirects=False, trust_env=False) as client:
        health = client.get("/health")
        health.raise_for_status()
        value = health.json()
        expected = {"aws": "dynamodb", "gcp": "firestore"}[args.provider]
        if value.get("storage_mode") != expected or value.get("llm_configured") is not False:
            raise CloudError("Confirm the intended backend and disabled paid AI before benchmarking")
        endpoints = benchmark(client, samples=args.samples, interval=args.interval)
    image = context.get("image") or context.get("image_uri") or ""
    git = subprocess.run(
        ["git", "-c", "safe.directory=" + ROOT.as_posix(), "rev-parse", "HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    success = all(
        result["first_observed"]["valid"]
        and result["warmup"]["failures"] == 0
        and result["measured"]["failures"] == 0
        for result in endpoints.values()
    )
    report = {
        "schema_version": 1, "provider": args.provider, "region": REGIONS[args.provider],
        "started_at_utc": started, "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "One sequential keep-alive HTTP client, 3 warmups then measured requests per endpoint; no retries",
        "limitations": "Client-observed elapsed time includes network and full response body. First observed requests follow a health preflight. Cold starts are unverified. Tenant database workflows and throughput are outside this sample.",
        "p95_method": "Nearest-rank over successful measured requests",
        "checkout_commit": git.stdout.strip() if git.returncode == 0 else None,
        "recorded_image_digest": image.split("@")[-1] if "@sha256:" in image else None,
        "storage_mode": expected, "paid_ai_enabled": False,
        "samples_per_endpoint": args.samples, "interval_seconds": args.interval,
        "concurrency": 1, "status": "passed" if success else "failed",
        "endpoints": endpoints,
    }
    destination = ROOT / ".tools" / ("cloud-benchmark-" + args.provider + ".json")
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CloudError, httpx.HTTPError, OSError, ValueError):
        print("Benchmark stopped. Check provider status, login and private deployment records.", file=sys.stderr)
        raise SystemExit(1)
