"""Bounded-cardinality metrics: never label with ticket text, IDs or credentials."""
import os
import secrets
from time import perf_counter

from fastapi import Header, HTTPException
from fastapi.responses import Response
from prometheus_client import Counter, Histogram, CONTENT_TYPE_LATEST, generate_latest

REQUESTS = Counter("ticketpilot_http_requests_total", "Completed API requests", ["method", "route", "status"])
LATENCY = Histogram("ticketpilot_http_request_duration_seconds", "API latency", ["method", "route"])
ANSWERS = Counter("ticketpilot_answers_total", "Answers by retrieval/generation mode", ["mode"])
RETRIEVAL = Histogram("ticketpilot_retrieved_sources", "Number of sources returned", buckets=(0, 1, 2, 3, 5))
LLM = Counter("ticketpilot_llm_calls_total", "Uncached provider attempts", ["outcome"])
LLM_LATENCY = Histogram("ticketpilot_llm_duration_seconds", "Provider attempt duration")


def install_metrics(app):
    @app.middleware("http")
    async def instrument(request, call_next):
        started = perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            path = getattr(route, "path", "unmatched")
            if path not in {"/metrics", "/health"}:
                method = request.method if request.method in {"GET", "POST", "PATCH", "DELETE", "PUT", "HEAD", "OPTIONS"} else "OTHER"
                REQUESTS.labels(method, path, str(status)).inc()
                LATENCY.labels(method, path).observe(perf_counter() - started)

    @app.get("/metrics", include_in_schema=False)
    def prometheus_metrics(authorization: str | None = Header(default=None)):
        token = os.getenv("METRICS_TOKEN", "")
        if not token:
            raise HTTPException(503, "Metrics disabled: configure METRICS_TOKEN")
        if not authorization or not secrets.compare_digest(authorization, "Bearer " + token):
            raise HTTPException(401, "Invalid metrics credentials")
        return Response(generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})
