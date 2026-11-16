"""Eight-unit tenant intake and private capability-based tracking. No paid AI calls."""
from collections import OrderedDict, deque, Counter
from datetime import datetime, timezone
import hashlib
import json
import os
import secrets
from threading import Lock
from time import monotonic
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from prometheus_client import Counter as MetricCounter
from ticketpilot import apartment_store as store, storage

router = APIRouter(prefix="/api/apartments", tags=["Apartment concerns"])
EVENTS = MetricCounter("ticketpilot_apartment_events_total", "Successful apartment workflow actions", ["action"])
Category = Literal["water", "maintenance", "electrical", "billing", "renewal", "other"]
Status = Literal["received", "acknowledged", "scheduled", "in_progress", "waiting_for_tenant", "resolved"]
Priority = Literal["normal", "high", "urgent"]
CATEGORIES = [
    {"id": "water", "en": "Water / plumbing", "fil": "Tubig / tubo"},
    {"id": "maintenance", "en": "Repairs / maintenance", "fil": "Pagkukumpuni"},
    {"id": "electrical", "en": "Electrical concern", "fil": "Problema sa kuryente"},
    {"id": "billing", "en": "Rent / utility billing", "fil": "Renta / singil"},
    {"id": "renewal", "en": "Contract renewal", "fil": "Pag-renew ng kontrata"},
    {"id": "other", "en": "Other concern", "fil": "Iba pang concern"},
]
GUIDANCE = {
 "water": {"en": "Tell management when the problem started, which taps are affected, and whether there is no water or low pressure. Management must confirm the cause and any restoration estimate.", "fil": "Sabihin kung kailan nagsimula, aling gripo ang apektado, at kung walang tubig o mahina ang pressure. Management ang magkukumpirma ng sanhi at oras ng pagbalik."},
 "maintenance": {"en": "Describe the damage and exact location. Management will arrange any repair and access with you; submitting this form does not schedule a visit.", "fil": "Ilarawan ang sira at eksaktong lokasyon. Makikipag-ayos ang management tungkol sa pagkukumpuni at pagpasok sa unit; hindi awtomatikong naka-schedule ang pagbisita."},
 "electrical": {"en": "Describe the location and what you noticed. For immediate danger, use your established emergency contact instead of waiting for a ticket update. A qualified person must assess repairs.", "fil": "Ilarawan ang lokasyon at napansin ninyo. Kung may agarang panganib, gamitin ang inyong emergency contact at huwag maghintay ng ticket update. Kwalipikadong tao ang dapat magsuri ng pagkukumpuni."},
 "billing": {"en": "Include the billing period and the item you want checked. Do not send bank passwords, card details, or account credentials. Management must verify the actual bill or payment.", "fil": "Ilagay ang billing period at ang singil na gustong ipa-check. Huwag magpadala ng password, card details, o login. Management ang magbe-verify ng bill o bayad."},
 "renewal": {"en": "State when your agreement ends and what you want to ask. Management must review your actual agreement; submitting a request does not approve renewal or change its terms.", "fil": "Sabihin kung kailan matatapos ang kasunduan at ang inyong tanong. Susuriin ng management ang aktuwal na kontrata; hindi nito awtomatikong inaaprubahan ang renewal o binabago ang terms."},
 "other": {"en": "Describe the concern and its location. Management will review it. For immediate danger, use your established emergency contact.", "fil": "Ilarawan ang concern at lokasyon. Susuriin ito ng management. Kung may agarang panganib, gamitin ang inyong emergency contact."},
}
_attempts = OrderedDict()
_lock = Lock()


def now():
    return datetime.now(timezone.utc).isoformat()


def units():
    return [value.strip() for value in os.getenv("APARTMENT_UNITS", "1,2,3,4,5,6,7,8").split(",") if value.strip()][:50]


def manager_refresh_seconds():
    try:
        value = int(os.getenv("APARTMENT_REFRESH_SECONDS", "30"))
    except ValueError:
        value = 30
    return max(30, min(value, 3600)) if value > 0 else 0


def queue_limit():
    try:
        value = int(os.getenv("APARTMENT_QUEUE_LIMIT", "200"))
    except ValueError:
        value = 200
    return max(1, min(value, 200))


def ready():
    if not os.getenv("ADMIN_TOKEN") or storage.mode() == "none":
        raise HTTPException(503, "Apartment intake is unavailable until management configures storage and access.")


def manager(token):
    ready()
    if not token or not secrets.compare_digest(token, os.environ["ADMIN_TOKEN"]):
        raise HTTPException(401, "Manager access required")


def throttle(request):
    # Bounded process-local protection, not a distributed/cloud-wide quota.
    key = request.client.host if request.client else "unknown"
    instant = monotonic()
    with _lock:
        attempts = _attempts.setdefault(key, deque())
        while attempts and attempts[0] <= instant - 60:
            attempts.popleft()
        if len(attempts) >= 30:
            raise HTTPException(429, "Too many requests. Please wait a minute.", headers={"Retry-After": "60"})
        attempts.append(instant)
        _attempts.move_to_end(key)
        while len(_attempts) > 1024:
            _attempts.popitem(last=False)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Concern(Input):
    unit: str = Field(min_length=1, max_length=40)
    category: Category
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=10, max_length=2000)
    language: Literal["en", "fil"] = "en"
    urgent: bool = False


class ManagerUpdate(Input):
    version: int = Field(ge=1)
    status: Status
    priority: Priority
    assigned_to: str = Field(default="", max_length=80)
    message: str = Field(default="", max_length=1000)
    internal_note: str = Field(default="", max_length=1000)


class Reply(Input):
    version: int = Field(ge=1)
    message: str = Field(min_length=3, max_length=1000)
    reopen: bool = False


class Notice(Input):
    version: int | None = Field(default=None, ge=1)
    title: str = Field(default="", max_length=120)
    message: str = Field(default="", max_length=1200)
    active: bool = True


def commit(record, version=None):
    if version is not None and record.get("version", version) != version:
        raise HTTPException(409, "This record changed. Refresh and try again.")
    if len(json.dumps(record, ensure_ascii=False).encode("utf-8")) > 250000:
        raise HTTPException(413, "This concern has reached its content limit. Contact management.")
    try:
        return store.save(record, version)
    except store.Conflict as exc:
        raise HTTPException(409, "This record changed. Refresh and try again.") from exc


def find(ticket_id):
    record = store.get(ticket_id) if ticket_id.startswith("apt_") else None
    if not record or record.get("kind") != "apartment_ticket":
        raise HTTPException(404, "Concern not found or tracking key is incorrect")
    return record


def tenant_record(ticket_id, key):
    ready()
    # Do not disclose whether an ID exists to someone without a valid key.
    if not key or len(key) > 128:
        raise HTTPException(404, "Concern not found or tracking key is incorrect")
    record = find(ticket_id)
    if not secrets.compare_digest(record["tracking_hash"], hashlib.sha256(key.encode()).hexdigest()):
        raise HTTPException(404, "Concern not found or tracking key is incorrect")
    return record


def public_record(record):
    fields = ("id", "reference", "unit", "category", "title", "description", "language", "priority", "status", "created_at", "updated_at", "resolved_at", "updates", "version")
    return {key: record[key] for key in fields}


def owner_record(record):
    return {**public_record(record), "assigned_to": record["assigned_to"], "internal_notes": record["internal_notes"]}


def append_message(record, field, author, text):
    if not text:
        return
    if len(record[field]) >= 100:
        raise HTTPException(409, "This concern has reached its update limit. Contact management.")
    record[field].append({"author": author, "text": text, "at": now()})


@router.get("/config")
def config():
    notice = store.get("apartment_notice") if storage.mode() != "none" else None
    return {"building_name": os.getenv("APARTMENT_NAME", "Our Apartment"), "units": units(), "categories": CATEGORIES,
            "guidance": GUIDANCE, "notice": {key: notice[key] for key in ("title", "message", "updated_at")} if notice and notice["active"] else None,
            "intake_available": bool(os.getenv("ADMIN_TOKEN")) and storage.mode() != "none", "manager_refresh_seconds": manager_refresh_seconds(), "queue_limit": queue_limit()}


@router.post("/concerns", status_code=201)
def create(item: Concern, request: Request):
    ready()
    if item.unit not in units():
        raise HTTPException(422, "Choose a configured apartment unit")
    throttle(request)
    key = secrets.token_urlsafe(32)
    ticket_id = "apt_" + uuid4().hex
    stamp = now()
    record = {"id": ticket_id, "queue": "apartment_tickets", "kind": "apartment_ticket",
              "reference": "APT-" + ticket_id[4:16].upper(), **item.model_dump(exclude={"urgent"}),
              "tracking_hash": hashlib.sha256(key.encode()).hexdigest(), "status": "received",
              "priority": "urgent" if item.urgent else "high" if item.category in {"water", "electrical"} else "normal",
              "assigned_to": "", "internal_notes": [], "updates": [], "created_at": stamp, "updated_at": stamp, "resolved_at": None}
    saved = commit(record)
    EVENTS.labels("created").inc()
    return {"ticket": public_record(saved), "tracking_key": key, "guidance": GUIDANCE[item.category][item.language],
            "receipt": "Saved for management review. This does not confirm a manager has read it or received an automatic notification."}


@router.get("/concerns/{ticket_id}")
def track(ticket_id: str, x_ticket_key: str | None = Header(default=None)):
    return public_record(tenant_record(ticket_id, x_ticket_key))


@router.post("/concerns/{ticket_id}/replies")
def reply(ticket_id: str, item: Reply, request: Request, x_ticket_key: str | None = Header(default=None)):
    record = tenant_record(ticket_id, x_ticket_key)
    throttle(request)
    append_message(record, "updates", "tenant", item.message)
    if item.reopen:
        if record["status"] != "resolved":
            raise HTTPException(409, "Only a resolved concern can be reopened")
        record["status"] = "received"
        record["resolved_at"] = None
    record["updated_at"] = now()
    saved = commit(record, item.version)
    EVENTS.labels("tenant_reply").inc()
    return public_record(saved)


@router.get("/manage/concerns")
def queue(x_admin_token: str | None = Header(default=None)):
    manager(x_admin_token)
    records = store.recent(queue_limit())
    active = [r for r in records if r["status"] != "resolved"]
    groups = []
    for category in ("water", "electrical", "maintenance"):
        affected = {r["unit"] for r in active if r["category"] == category}
        if len(affected) > 1:
            groups.append({"category": category, "unit_count": len(affected), "note": "Possible shared issue; management must confirm the cause."})
    return {"items": [owner_record(r) for r in records], "scope": f"Showing up to {queue_limit()} recent concerns; older concerns may not appear. Counts describe only the records shown.",
            "counts": dict(Counter(r["status"] for r in records)), "possible_shared_issues": groups}


@router.get("/manage/concerns/{ticket_id}")
def owner_get(ticket_id: str, x_admin_token: str | None = Header(default=None)):
    manager(x_admin_token)
    return owner_record(find(ticket_id))


@router.patch("/manage/concerns/{ticket_id}")
def update(ticket_id: str, item: ManagerUpdate, x_admin_token: str | None = Header(default=None)):
    manager(x_admin_token)
    record = find(ticket_id)
    append_message(record, "updates", "manager", item.message)
    append_message(record, "internal_notes", "manager", item.internal_note)
    if record["status"] != item.status:
        append_message(record, "updates", "system", "Status: " + item.status)
    record.update(status=item.status, priority=item.priority, assigned_to=item.assigned_to, updated_at=now())
    record["resolved_at"] = record.get("resolved_at") or now() if item.status == "resolved" else None
    saved = commit(record, item.version)
    EVENTS.labels("manager_update").inc()
    return owner_record(saved)


@router.get("/manage/notice")
def get_notice(x_admin_token: str | None = Header(default=None)):
    manager(x_admin_token)
    record = store.get("apartment_notice")
    return {key: record[key] for key in ("title", "message", "active", "version")} if record else {"title": "", "message": "", "active": False, "version": None}


@router.put("/manage/notice")
def set_notice(item: Notice, x_admin_token: str | None = Header(default=None)):
    manager(x_admin_token)
    if item.active and (not item.title or not item.message):
        raise HTTPException(422, "An active notice needs a title and message")
    stamp = now()
    saved = commit({"id": "apartment_notice", "queue": "apartment_notices", "created_at": stamp, "updated_at": stamp,
                    "title": item.title, "message": item.message, "active": item.active}, item.version)
    return {key: saved[key] for key in ("title", "message", "active", "version")}
