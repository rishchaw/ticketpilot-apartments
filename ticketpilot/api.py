"""TicketPilot AWS: classifier, retrieval, optional Bedrock, operations API."""
from __future__ import annotations
import csv
import io
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from ticketpilot.tenant_auth import router as tenant_auth_router, tenant_from_request
from ticketpilot.assistant import suggest
from ticketpilot.cloud_inference import ROOT, classify
from ticketpilot.knowledge import index
from ticketpilot.storage import Conflict, mode, upsert, recent, get, delete, summary
from ticketpilot.observability import install_metrics, ANSWERS, RETRIEVAL

app = FastAPI(title="TicketPilot AI — Support Operations", version="2.0.0",
              description="Cloud-native helpdesk ML + retrieval + human-in-the-loop workflow")

@app.exception_handler(Conflict)
async def storage_conflict_handler(request, error):
    return JSONResponse(status_code=409, content={"detail": "The record changed; reload before retrying"})


TEAMS = {"access": "Identity & Access", "billing": "Finance & Billing",
         "infrastructure": "Infrastructure / SRE", "product": "Product Support"}
install_metrics(app)
HIGH = ("outage", "production", "down", "security breach", "payment failure", "data loss", "unreachable", "500 error", "compromised", "breach")
MEDIUM = ("urgent", "asap", "failed", "cannot", "blocked", "timeout", "refund", "broken", "incorrect")

class TicketInput(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    text: str = Field(min_length=10, max_length=2000)

class StatusUpdate(BaseModel):
    status: str = Field(pattern="^(open|in_progress|resolved)$")

class Analysis(BaseModel):
    predicted_category: str
    assigned_team: str
    confidence: float
    priority: str
    requires_human_review: bool
    review_reason: str | None
    category_probabilities: dict[str, float]
    suggested_answer: str
    answer_mode: str
    sources: list[dict]


def _verify(token: str | None) -> None:
    secret = os.getenv("ADMIN_TOKEN", "")
    if not secret:
        raise HTTPException(status_code=503, detail="Owner operations disabled: configure ADMIN_TOKEN on the server")
    if not token or not secrets.compare_digest(secret, token):
        raise HTTPException(status_code=401, detail="Invalid or missing owner token")
    if mode() == "none":
        raise HTTPException(status_code=503, detail="Persistence is disabled; configure a supported storage backend")

def _priority(text: str) -> str:
    lower = text.casefold()
    if any(re.search(r"\b" + re.escape(word) + r"\b", lower) for word in HIGH):
        return "high"
    if any(re.search(r"\b" + re.escape(word) + r"\b", lower) for word in MEDIUM):
        return "medium"
    return "low"

def _analyze(item: TicketInput, use_llm: bool = False) -> dict:
    label, confidence, probs = classify(item.title + ". " + item.text)
    threshold = float(os.getenv("CONFIDENCE_THRESHOLD", "0.70"))
    needs_review = confidence < threshold
    response, retrieved, answer_mode = suggest(item.title + ". " + item.text, label, use_llm=use_llm)
    ANSWERS.labels(answer_mode).inc()
    RETRIEVAL.observe(len(retrieved))
    return Analysis(
        predicted_category=label,
        assigned_team="Human triage queue" if needs_review else TEAMS[label],
        confidence=round(confidence, 4),
        priority=_priority(item.title + " " + item.text),
        requires_human_review=needs_review,
        review_reason="Confidence below routing threshold" if needs_review else None,
        category_probabilities=probs,
        suggested_answer=response,
        answer_mode=answer_mode,
        sources=[{"id": a["id"], "title": a["title"], "relevance": a["relevance"],
                  "steps": a["steps"], "escalation": a["escalation"]} for a in retrieved],
    ).model_dump()

@app.get("/", include_in_schema=False)
def home(request: Request):
    return tenant_portal(request)

@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0", "storage_mode": mode(),
            "model": "PyTorch-trained / NumPy inference", "llm_configured": os.getenv("LLM_PROVIDER") == "bedrock"}

@app.get("/api/knowledge")
def knowledge():
    docs = index()[0]
    return {"total": len(docs), "articles": [{k: d[k] for k in ("id", "title", "category", "summary")} for d in docs]}

@app.post("/api/analyze", response_model=Analysis)
def analyze_public(item: TicketInput):
    """Public playground is intentionally read-only and makes no paid LLM requests."""
    return _analyze(item, use_llm=False)

@app.post("/api/tickets", status_code=201)
def create_ticket(item: TicketInput, x_admin_token: str | None = Header(default=None), use_llm: bool = False):
    _verify(x_admin_token)
    result = _analyze(item, use_llm=use_llm)
    now = datetime.now(timezone.utc).isoformat()
    record = {"id": str(uuid4()), "title": item.title, "text": item.text,
              **result, "status": "open", "created_at": now, "updated_at": now, "resolved_at": None}
    record.pop("category_probabilities", None)
    return upsert(record)

@app.get("/api/tickets")
def list_tickets(x_admin_token: str | None = Header(default=None), limit: int = Query(50, ge=1, le=100)):
    _verify(x_admin_token)
    return {"items": recent(limit), "max_returned": limit}

@app.patch("/api/tickets/{ticket_id}")
def update_ticket(ticket_id: str, patch: StatusUpdate, x_admin_token: str | None = Header(default=None)):
    _verify(x_admin_token)
    item = get(ticket_id)
    if not item:
        raise HTTPException(status_code=404, detail="Ticket not found")
    item["status"] = patch.status
    now = datetime.now(timezone.utc).isoformat()
    item["updated_at"] = now
    item["resolved_at"] = now if patch.status == "resolved" else None
    return upsert(item)

@app.delete("/api/tickets/{ticket_id}", status_code=204)
def delete_ticket(ticket_id: str, x_admin_token: str | None = Header(default=None)):
    _verify(x_admin_token)
    if not delete(ticket_id):
        raise HTTPException(status_code=404, detail="Ticket not found")
    return Response(status_code=204)

@app.get("/api/metrics")
def metrics(x_admin_token: str | None = Header(default=None)):
    _verify(x_admin_token)
    return summary(recent(200))

@app.get("/api/export.csv")
def export_csv(x_admin_token: str | None = Header(default=None)):
    _verify(x_admin_token)
    rows = recent(200)
    output = io.StringIO()
    fields = ["id", "title", "predicted_category", "assigned_team", "priority", "confidence", "status", "requires_human_review", "created_at"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for item in rows:
        sanitized = {k: str(item.get(k, "")) for k in fields}
        for key in fields:
            if sanitized[key].lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                sanitized[key] = "'" + sanitized[key]
        writer.writerow(sanitized)
    return Response(content=output.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=ticketpilot-report.csv"})

# Fully synthetic portfolio examples. Every write is owner-authenticated.
SAMPLE_TICKETS = [
    ("Production API outage", "Our production API is unreachable and all customers receive 503 errors since noon."),
    ("Invoice charged twice", "My October subscription has a duplicate payment and an incorrect invoice amount."),
    ("Cannot sign in", "I forgot my password and my account is locked after too many failed login attempts."),
    ("Export button broken", "The analytics CSV download button is not working on the dashboard."),
    ("MFA recovery", "I changed phones and can no longer access my authenticator verification codes."),
    ("Data breach alert", "Security breach suspected and confidential data might be exposed; require immediate help."),
    ("Refund request", "Please issue a refund for a cancelled annual subscription I accidentally renewed."),
    ("Slow database query", "Database timeouts are causing slow API responses and customers are reporting delays."),
    ("SSO permission denied", "Users get 403 forbidden errors after signing in through single sign on."),
    ("Checkout failure", "All customers get payment failure errors at checkout; orders are blocked."),
    ("Dashboard layout issue", "The mobile dashboard layout breaks and the navigation button is hidden."),
    ("New feature suggestion", "Can we add a new feature to schedule recurring analytics reports?")
]

@app.post("/api/admin/seed")
def seed_examples(x_admin_token: str | None = Header(default=None)):
    _verify(x_admin_token)
    existing = len(recent(100))
    if existing:
        return {"created": 0, "message": "Existing tickets found; seed is intentionally not repeatable"}
    for title, text in SAMPLE_TICKETS:
        result = _analyze(TicketInput(title=title, text=text))
        now = datetime.now(timezone.utc).isoformat()
        item = {"id": str(uuid4()), "title": title, "text": text,
                **result, "status": "open", "created_at": now, "updated_at": now, "resolved_at": None}
        item.pop("category_probabilities", None)
        upsert(item)
    return {"created": len(SAMPLE_TICKETS), "message": "Synthetic portfolio tickets created"}


# Apartment portal; original support demo stays available at /demo.
from ticketpilot.apartments import router as apartment_router
app.include_router(apartment_router)
app.include_router(tenant_auth_router)


@app.get("/tenant", include_in_schema=False)
def tenant_portal(request: Request):
    if tenant_from_request(request) is None:
        return RedirectResponse("/tenant/login", status_code=303)
    return FileResponse(ROOT / "ticketpilot" / "static" / "apartments.html")


@app.get("/tenant/login", include_in_schema=False)
def tenant_login_page():
    return FileResponse(ROOT / "ticketpilot" / "static" / "tenant-login.html")


@app.get("/assets/tenant-login.js", include_in_schema=False)
def tenant_login_script():
    return FileResponse(ROOT / "ticketpilot" / "static" / "tenant-login.js", media_type="text/javascript")


@app.get("/manager", include_in_schema=False)
def manager_portal():
    return FileResponse(ROOT / "ticketpilot" / "static" / "apartments.html")


@app.get("/demo", include_in_schema=False)
def original_demo():
    return FileResponse(ROOT / "ticketpilot" / "static" / "index.html")


@app.get("/assets/apartments.js", include_in_schema=False)
def apartment_script():
    return FileResponse(ROOT / "ticketpilot" / "static" / "apartments.js", media_type="text/javascript")


@app.get("/assets/apartments.css", include_in_schema=False)
def apartment_styles():
    return FileResponse(ROOT / "ticketpilot" / "static" / "apartments.css", media_type="text/css")


@app.middleware("http")
async def apartment_privacy_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/api/apartments", "/api/tenant")) or request.url.path in {"/", "/tenant", "/tenant/login", "/manager"}:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    return response
