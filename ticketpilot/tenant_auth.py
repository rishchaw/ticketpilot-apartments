"""Closed tenant accounts and private, persisted opaque browser sessions.

No public signup or provider-specific identity service is required. Credentials
and sessions live only in the dedicated auth store. The registry contains exactly
eight approved slots; unit claims never come from browser input.
"""
from __future__ import annotations
import hashlib
import os
import re
import secrets
import time
from urllib.parse import urlsplit
from uuid import uuid4
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from ticketpilot import tenant_auth_store as store

class PrivateAuthRoute(APIRoute):
    """Prevent validation errors from reflecting raw credential request bodies."""
    def get_route_handler(self):
        original = super().get_route_handler()
        async def protected_validation(request):
            # Bound the actual stream before Pydantic parses credential input;
            # Content-Length alone is not sufficient for chunked requests.
            if request.method in {"POST", "PUT", "PATCH"}:
                try:
                    declared = int(request.headers.get("content-length", "0"))
                except ValueError:
                    declared = 4097
                if declared < 0 or declared > 4096:
                    return JSONResponse(status_code=413, content={"detail": "Tenant request is too large"}, headers={"Cache-Control": "no-store"})
                body = bytearray()
                async for chunk in request.stream():
                    if len(body) + len(chunk) > 4096:
                        return JSONResponse(status_code=413, content={"detail": "Tenant request is too large"}, headers={"Cache-Control": "no-store"})
                    body.extend(chunk)
                # Starlette's body/json readers reuse this request-local cache.
                request._body = bytes(body)
            try:
                return await original(request)
            except RequestValidationError:
                return JSONResponse(status_code=422, content={"detail": "Invalid tenant authentication request"}, headers={"Cache-Control": "no-store"})
        return protected_validation


router = APIRouter(prefix="/api/tenant", tags=["Tenant login"], route_class=PrivateAuthRoute)
PASSWORDS = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, hash_len=32, salt_len=16, type=Type.ID)
_DUMMY_HASH = PASSWORDS.hash(secrets.token_urlsafe(32))
SESSION_SECONDS = 8 * 60 * 60
REGISTRY_ID = "registry"
MAX_CAS_ATTEMPTS = 6


def canonical_username(value):
    if not isinstance(value, str):
        raise ValueError("Invalid tenant username")
    value = value.strip().casefold()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,63}", value):
        raise ValueError("Invalid tenant username")
    return value


def hash_password(password):
    if not isinstance(password, str) or not 15 <= len(password) <= 128:
        raise ValueError("Use a password between 15 and 128 characters")
    return PASSWORDS.hash(password)


def verify_password(password_hash, password):
    if not isinstance(password, str) or not 1 <= len(password) <= 128:
        return False
    try:
        return PASSWORDS.verify(password_hash, password)
    except (VerificationError, InvalidHashError, TypeError, ValueError):
        return False


def new_user(username, unit, *, password, tenant_id=None):
    username = canonical_username(username)
    if not isinstance(unit, str) or not unit.strip() or len(unit.strip()) > 40:
        raise ValueError("Invalid tenant unit")
    tenant_id = tenant_id or uuid4().hex
    if not isinstance(tenant_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", tenant_id):
        raise ValueError("Invalid tenant identifier")
    return {"kind": "tenant_user", "tenant_id": tenant_id, "username": username,
            "unit": unit.strip(), "password_hash": hash_password(password),
            "credential_version": 1, "active": True}


def cookie_secure():
    # Production defaults fail closed. Only explicit local/test setup disables it.
    return os.getenv("TENANT_COOKIE_SECURE", "true").casefold() != "false"


def cookie_name():
    return "__Host-ticketpilot_tenant" if cookie_secure() else "ticketpilot_tenant_local"


def _unavailable():
    return HTTPException(503, "Tenant login is temporarily unavailable")


def _read(record_id):
    try:
        return store.get(record_id)
    except store.Unavailable:
        raise _unavailable() from None


def _registry():
    value = _read(REGISTRY_ID)
    if not value or value.get("kind") != "tenant_registry" or value.get("status") != "ready":
        raise _unavailable()
    slots = value.get("slots")
    if not isinstance(slots, list) or len(slots) != 8:
        raise _unavailable()
    usernames, identifiers = set(), set()
    for slot in slots:
        if not isinstance(slot, dict):
            raise _unavailable()
        username, tenant_id, unit = slot.get("username"), slot.get("tenant_id"), slot.get("unit")
        try:
            if canonical_username(username) != username:
                raise _unavailable()
        except ValueError:
            raise _unavailable() from None
        if not isinstance(tenant_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", tenant_id) or not isinstance(unit, str) or not unit.strip() or len(unit) > 40 or username in usernames or tenant_id in identifiers:
            raise _unavailable()
        usernames.add(username)
        identifiers.add(tenant_id)
    return slots


def _registered_user(username, slots=None):
    slots = _registry() if slots is None else slots
    slot = next((entry for entry in slots if entry["username"] == username), None)
    if slot is None:
        return None
    user = _read("user:" + username)
    if not user or user.get("kind") != "tenant_user" or user.get("active") is not True:
        return None
    if any(user.get(key) != slot[key] for key in ("username", "tenant_id", "unit")):
        return None
    if type(user.get("credential_version")) is not int or user["credential_version"] < 1:
        return None
    return user


def _principal(user):
    return {"id": user["tenant_id"], "username": user["username"], "unit": user["unit"]}


def _origin(request):
    # Compare browser origin with the request's host without trusting forwarded
    # scheme headers. Cloud Run may terminate TLS ahead of Uvicorn.
    origin = request.headers.get("origin")
    if not origin:
        return
    try:
        parsed = urlsplit(origin)
        host = urlsplit(("https" if cookie_secure() else parsed.scheme) + "://" + request.headers.get("host", ""))
        expected_scheme = "https" if cookie_secure() else parsed.scheme
        valid = parsed.scheme in {"https", "http"} and parsed.scheme == expected_scheme and parsed.hostname and parsed.username is None and parsed.password is None and not parsed.path and not parsed.query and not parsed.fragment and parsed.hostname.casefold() == (host.hostname or "").casefold() and (parsed.port or (443 if parsed.scheme == "https" else 80)) == (host.port or (443 if host.scheme == "https" else 80))
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(403, "Request origin is not permitted")


def _counter(record_id, *, limit, seconds):
    instant = int(time.time())
    window = instant // seconds
    for attempt in range(MAX_CAS_ATTEMPTS):
        previous = _read(record_id)
        if previous and previous.get("kind") != "tenant_rate":
            raise _unavailable()
        if previous:
            if type(previous.get("window")) is not int or type(previous.get("version")) is not int or previous["version"] < 1:
                raise _unavailable()
            # An in-flight request from the preceding window cannot rewind the
            # newer persisted bucket and reset its allowance.
            window = max(window, previous["window"])
        count = previous.get("count", 0) if previous and previous.get("window") == window else 0
        if type(count) is not int or count < 0:
            raise _unavailable()
        if count >= limit:
            raise HTTPException(429, "Too many login attempts. Please try again later.", headers={"Retry-After": str(max(1, (window + 1) * seconds - instant))})
        value = {"kind": "tenant_rate", "window": window, "count": count + 1, "window_ends_at": (window + 1) * seconds}
        try:
            store.put_if_version(record_id, value, previous["version"] if previous else None)
            return
        except store.Conflict:
            if attempt + 1 < MAX_CAS_ATTEMPTS:
                time.sleep(min(0.002 * (2 ** attempt), 0.03))
        except store.Unavailable:
            raise _unavailable() from None
    raise _unavailable()


def _throttle(username, slots):
    _counter("rate:global", limit=60, seconds=300)
    known = any(slot["username"] == username for slot in slots)
    _counter("rate:" + username if known else "rate:unknown", limit=10, seconds=900)


def _session(request):
    token = request.cookies.get(cookie_name())
    if not token or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise HTTPException(401, "Tenant login required")
    record_id = "session:" + hashlib.sha256(token.encode("ascii")).hexdigest()
    record = _read(record_id)
    if not record or record.get("kind") != "tenant_session" or type(record.get("auth_expires_at")) is not int or record["auth_expires_at"] <= int(time.time()):
        raise HTTPException(401, "Tenant login required")
    username = record.get("username")
    try:
        if canonical_username(username) != username:
            raise HTTPException(401, "Tenant login required")
    except ValueError:
        raise HTTPException(401, "Tenant login required") from None
    user = _registered_user(username)
    if not user or user["tenant_id"] != record.get("tenant_id") or user["credential_version"] != record.get("credential_version"):
        raise HTTPException(401, "Tenant login required")
    if not isinstance(record.get("csrf_token"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", record["csrf_token"]):
        raise HTTPException(401, "Tenant login required")
    return record_id, record, user


def _csrf(request, record):
    _origin(request)
    supplied = request.headers.get("x-csrf-token", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", supplied) or not secrets.compare_digest(supplied, record["csrf_token"]):
        raise HTTPException(403, "Refresh the page before submitting this request")


def require_tenant(request, write=False):
    _, record, user = _session(request)
    if write:
        _csrf(request, record)
    return _principal(user)


def tenant_from_request(request):
    try:
        return require_tenant(request)
    except HTTPException as exc:
        if exc.status_code == 401:
            return None
        raise


def _payload(record, user):
    return {"tenant": _principal(user), "csrf_token": record["csrf_token"], "expires_at": record["auth_expires_at"]}


def _issue(user, response):
    for _ in range(3):
        token = secrets.token_urlsafe(32)
        record_id = "session:" + hashlib.sha256(token.encode("ascii")).hexdigest()
        value = {"kind": "tenant_session", "tenant_id": user["tenant_id"], "username": user["username"],
                 "credential_version": user["credential_version"], "csrf_token": secrets.token_urlsafe(32),
                 "auth_expires_at": int(time.time()) + SESSION_SECONDS}
        try:
            record = store.put_if_version(record_id, value)
        except store.Conflict:
            continue
        except store.Unavailable:
            raise _unavailable() from None
        response.set_cookie(cookie_name(), token, max_age=SESSION_SECONDS, path="/", secure=cookie_secure(), httponly=True, samesite="strict")
        response.headers["Cache-Control"] = "no-store"
        return _payload(record, user)
    raise _unavailable()


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    username: str
    password: SecretStr = Field(min_length=1, max_length=128)


class PasswordInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    current_password: SecretStr
    new_password: SecretStr


@router.post("/login")
def login(item: LoginInput, request: Request, response: Response):
    if request.headers.get("x-ticketpilot-login") != "1":
        raise HTTPException(403, "Open the tenant login page to sign in")
    _origin(request)
    slots = _registry()
    try:
        username = canonical_username(item.username)
    except ValueError:
        username = None
    _throttle(username, slots)
    user = _registered_user(username, slots)
    password = item.password.get_secret_value()
    candidate = user.get("password_hash") if user else _DUMMY_HASH
    valid = verify_password(candidate, password)
    if not user or not valid:
        raise HTTPException(401, "Invalid username or password")
    return _issue(user, response)


@router.get("/session")
def session(request: Request, response: Response):
    _, record, user = _session(request)
    response.headers["Cache-Control"] = "no-store"
    return _payload(record, user)


@router.post("/logout", status_code=204)
def logout(request: Request):
    record_id, record, _ = _session(request)
    _csrf(request, record)
    try:
        # Concurrent deletion is already a logged-out session; no active row is
        # deleted if its version unexpectedly changed.
        removed = store.delete(record_id, record["version"])
        if not removed and _read(record_id) is not None:
            raise _unavailable()
    except store.Unavailable:
        raise _unavailable() from None
    response = Response(status_code=204)
    response.delete_cookie(cookie_name(), path="/", secure=cookie_secure(), httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/password")
def change_password(item: PasswordInput, request: Request, response: Response):
    record_id, record, user = _session(request)
    _csrf(request, record)
    _throttle(user["username"], _registry())
    current, replacement = item.current_password.get_secret_value(), item.new_password.get_secret_value()
    if not verify_password(user.get("password_hash"), current):
        raise HTTPException(401, "Current password is incorrect")
    if replacement == current:
        raise HTTPException(400, "Choose a different password")
    try:
        encoded = hash_password(replacement)
    except ValueError:
        raise HTTPException(400, "Use a password between 15 and 128 characters") from None
    value = {**user, "password_hash": encoded, "credential_version": user["credential_version"] + 1}
    try:
        saved = store.put_if_version("user:" + user["username"], value, user["version"])
        store.delete(record_id, record["version"])
    except store.Conflict:
        raise HTTPException(409, "Account changed. Sign in again before retrying.") from None
    except store.Unavailable:
        raise _unavailable() from None
    return _issue(saved, response)
