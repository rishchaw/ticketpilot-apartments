"""Local endpoint latency benchmark; NOT evidence of business productivity gains."""
from __future__ import annotations
import json
import os
import statistics
import time
from pathlib import Path
import numpy as np
from fastapi.testclient import TestClient

os.environ["STORAGE_MODE"] = "none"
from ticketpilot.api import app

SAMPLES = [
    "Production database server is unreachable and reports a timeout",
    "My invoice has an incorrect billing charge for the account",
    "Cannot log in; reset the password for the customer dashboard",
    "Please add a new export feature to the reports dashboard",
    "I have a question and need some help about settings",
]

def main() -> None:
    client = TestClient(app)
    # Warm the model to isolate steady-state request time from cold-start model loading.
    client.post('/triage', json={'text': SAMPLES[0]})
    milliseconds = []
    review_count = 0
    n = 100
    for i in range(n):
        start = time.perf_counter()
        response = client.post('/triage', json={'text': SAMPLES[i % len(SAMPLES)]})
        elapsed = (time.perf_counter() - start) * 1000
        response.raise_for_status()
        milliseconds.append(elapsed)
        review_count += response.json()['requires_human_review']
    report = {
        'notice': 'Local synthetic repeated requests; includes TestClient overhead. Not cloud load testing and not production measured productivity.',
        'request_count': n,
        'p50_ms': round(statistics.median(milliseconds), 2),
        'p95_ms': round(float(np.percentile(milliseconds, 95)), 2),
        'review_fraction_on_repeated_demo_requests': round(review_count/n, 3)
    }
    out = Path('artifacts/benchmark-local.json')
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
