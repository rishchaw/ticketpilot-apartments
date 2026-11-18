"""Provision exactly eight private tenant accounts without printing credentials.

Native CLI credentials select the backing store through existing environment
configuration. Password inventories stay in private files/stdin, never Terraform,
command arguments, public reports or logs. Explicit reset uses a durable private
pending file so interruption does not lose the replacement password.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
from uuid import uuid4
from ticketpilot import tenant_auth as auth, tenant_auth_store as store

ROOT = Path(__file__).resolve().parents[1]
MAX_INVENTORY_BYTES = 32768


class AccountError(Exception):
    """A fixed, credential-free explanation safe to show to the operator."""


def _units(value):
    values = [part.strip() for part in value.split(",")] if isinstance(value, str) else []
    if len(values) != 8 or any(not unit or len(unit) > 40 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]*", unit) for unit in values):
        raise AccountError("Provide exactly eight nonempty unit labels")
    return values


def _canonical(value):
    try:
        result = auth.canonical_username(value)
    except ValueError:
        raise AccountError("Credential inventory has an invalid username") from None
    if result != value:
        raise AccountError("Credential inventory usernames must be canonical")
    return result


def validate_inventory(value, units=None):
    if not isinstance(value, dict) or set(value) != {"schema_version", "accounts"} or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise AccountError("Unsupported private credential inventory format")
    accounts = value.get("accounts")
    if not isinstance(accounts, list) or len(accounts) != 8:
        raise AccountError("Credential inventory must contain exactly eight accounts")
    names, identifiers = set(), set()
    for entry in accounts:
        if not isinstance(entry, dict) or set(entry) != {"tenant_id", "username", "unit", "password"}:
            raise AccountError("Credential inventory account fields are invalid")
        username = _canonical(entry.get("username"))
        tenant_id, unit, password = entry.get("tenant_id"), entry.get("unit"), entry.get("password")
        if not isinstance(tenant_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", tenant_id):
            raise AccountError("Credential inventory tenant identifier is invalid")
        if not isinstance(unit, str) or not unit or len(unit) > 40 or unit != unit.strip():
            raise AccountError("Credential inventory unit is invalid")
        if not isinstance(password, str) or not 15 <= len(password) <= 128:
            raise AccountError("Credential inventory password length is invalid")
        if username in names or tenant_id in identifiers:
            raise AccountError("Credential inventory has duplicate account identifiers")
        names.add(username)
        identifiers.add(tenant_id)
    if units is not None and [entry["unit"] for entry in accounts] != list(units):
        raise AccountError("Private inventory does not match the explicitly selected eight units")
    if len(_encoded(value)) > MAX_INVENTORY_BYTES:
        raise AccountError("Private credential inventory exceeds its size limit")
    return value


def new_inventory(units):
    if not isinstance(units, list) or len(units) != 8:
        raise AccountError("Provide exactly eight unit labels")
    accounts, used = [], set()
    for unit in units:
        base = "unit-" + re.sub(r"[^a-z0-9]+", "-", unit.casefold()).strip("-")
        username, suffix = base, 2
        while username in used:
            username = base + "-" + str(suffix)
            suffix += 1
        _canonical(username)
        used.add(username)
        accounts.append({"tenant_id": uuid4().hex, "username": username, "unit": unit, "password": secrets.token_urlsafe(24)})
    return validate_inventory({"schema_version": 1, "accounts": accounts}, units)


def _encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _digest(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AccountError("Duplicate fields in private credential JSON")
        result[key] = value
    return result


def _reject_constant(value):
    raise AccountError("Invalid private JSON numeric value")


def _decode(data):
    if len(data) > MAX_INVENTORY_BYTES:
        raise AccountError("Private credential input exceeds its size limit")
    try:
        return json.loads(data.decode("utf-8-sig"), object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError):
        raise AccountError("Private credential input is not valid JSON") from None


def _private_path(path):
    path = Path(path).absolute()
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise AccountError("Refusing a symlink in a private credential path")
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(ROOT.resolve())
    except ValueError:
        pass  # Explicit paths outside the source tree remain operator-selected.
    else:
        if not relative.parts or relative.parts[0].casefold() not in {".secrets", ".tools"}:
            raise AccountError("Keep credential files inside .secrets, .tools or outside the source tree")
    if path.exists() and (not path.is_file() or path.stat().st_nlink > 1):
        raise AccountError("Private credential path must be a regular non-linked file")
    return path


def _read_private(path):
    path = _private_path(path)
    if not path.is_file():
        raise AccountError("Restore the existing private credential file before continuing")
    with path.open("rb") as stream:
        data = stream.read(MAX_INVENTORY_BYTES + 1)
    return _decode(data)


def _write_private(path, value, *, exclusive=False):
    path = _private_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix="tenant-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_encoded(value))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        if exclusive:
            # Same-directory hard link publishes a complete file without replacing
            # a concurrently created inventory. Remove the private temporary name.
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _file_lock(path):
    path = _private_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _private_path(path.with_name(path.name + ".lock"))
    # Keep a fixed inode and let the OS release its lock on process termination.
    # A durable O_EXCL marker would strand interrupted reset recovery forever.
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    locked = False
    try:
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"0")
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError:
            raise AccountError("Another tenant account operation holds this private file lock") from None
        yield path
    finally:
        if locked:
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _slots(inventory):
    return [{key: entry[key] for key in ("tenant_id", "username", "unit")} for entry in inventory["accounts"]]


def _check_registry(value, inventory, *, ready=False):
    if not value or value.get("kind") != "tenant_registry" or value.get("slots") != _slots(inventory) or value.get("status") not in ({"ready"} if ready else {"ready", "provisioning"}):
        raise AccountError("Existing tenant registry differs; restore its matching private inventory")
    return value


def _check_user(user, entry, *, verify_secret):
    if not user or user.get("kind") != "tenant_user" or any(user.get(key) != entry[key] for key in ("tenant_id", "username", "unit")) or type(user.get("credential_version")) is not int or user["credential_version"] < 1 or type(user.get("active")) is not bool:
        raise AccountError("Existing tenant account differs; explicit operator recovery is required")
    if verify_secret and not auth.verify_password(user.get("password_hash"), entry["password"]):
        raise AccountError("An existing tenant password differs; provisioning never resets passwords")
    return user


def apply_inventory(inventory):
    inventory = validate_inventory(inventory)
    registry = store.get(auth.REGISTRY_ID)
    if registry is None:
        try:
            registry = store.put_if_version(auth.REGISTRY_ID, {"kind": "tenant_registry", "status": "provisioning", "slots": _slots(inventory)})
        except store.Conflict:
            registry = store.get(auth.REGISTRY_ID)
    _check_registry(registry, inventory)
    created = 0
    for entry in inventory["accounts"]:
        record_id = "user:" + entry["username"]
        user = store.get(record_id)
        if user is None:
            if registry["status"] == "ready":
                raise AccountError("A ready registry has a missing account; explicit recovery is required")
            value = auth.new_user(entry["username"], entry["unit"], password=entry["password"], tenant_id=entry["tenant_id"])
            try:
                user = store.put_if_version(record_id, value)
                created += 1
            except store.Conflict:
                user = store.get(record_id)
        _check_user(user, entry, verify_secret=True)
    for _ in range(6):
        registry = _check_registry(store.get(auth.REGISTRY_ID), inventory)
        if registry["status"] == "ready":
            break
        try:
            store.put_if_version(auth.REGISTRY_ID, {**registry, "status": "ready"}, registry["version"])
            break
        except store.Conflict:
            continue
    else:
        raise AccountError("Tenant registry changed repeatedly; retry using the same private inventory")
    return {"accounts": 8, "created_users": created, "ready": True}


def generate(path, units):
    units = _units(units) if isinstance(units, str) else units
    with _file_lock(path) as path:
        if path.exists():
            validate_inventory(_read_private(path), units)
            return {"accounts": 8, "created_file": False}
        _write_private(path, new_inventory(units), exclusive=True)
        return {"accounts": 8, "created_file": True}


def provision(path, units):
    units = _units(units) if isinstance(units, str) else units
    with _file_lock(path) as path:
        registry = store.get(auth.REGISTRY_ID)  # Auth errors are never treated as absence.
        if registry is not None and not path.exists():
            raise AccountError("An existing registry requires its original private credential file")
        created_file = not path.exists()
        if created_file:
            _write_private(path, new_inventory(units), exclusive=True)
        inventory = validate_inventory(_read_private(path), units)
        result = apply_inventory(inventory)
        return {**result, "created_file": created_file}


def _pending_path(path):
    return path.with_name(path.name + ".reset-pending.json")


def reset(path, username):
    username = _canonical(username)
    with _file_lock(path) as path:
        inventory = validate_inventory(_read_private(path))
        _check_registry(store.get(auth.REGISTRY_ID), inventory, ready=True)
        entry = next((entry for entry in inventory["accounts"] if entry["username"] == username), None)
        if entry is None:
            raise AccountError("Selected account is not in this private inventory")
        user = _check_user(store.get("user:" + username), entry, verify_secret=False)
        pending_path = _pending_path(path)
        if pending_path.exists():
            pending = _read_private(pending_path)
            if not isinstance(pending, dict) or pending.get("schema_version") != 1 or pending.get("action") != "reset" or pending.get("username") != username or pending.get("tenant_id") != user["tenant_id"] or type(pending.get("old_credential_version")) is not int or pending["old_credential_version"] < 1:
                raise AccountError("Pending reset needs explicit operator review")
            replacement = validate_inventory(pending.get("inventory"))
            if _slots(replacement) != _slots(inventory) or _digest(inventory) not in {pending.get("base_digest"), _digest(replacement)}:
                raise AccountError("Private inventory changed during the pending reset")
            if any(old != new for old, new in zip(inventory["accounts"], replacement["accounts"]) if old["username"] != username):
                raise AccountError("Pending reset changes another account; explicit review is required")
            if _digest(inventory) == pending.get("base_digest"):
                old_target = next(item for item in inventory["accounts"] if item["username"] == username)
                new_target = next(item for item in replacement["accounts"] if item["username"] == username)
                if old_target["password"] == new_target["password"]:
                    raise AccountError("Pending reset has no replacement password")
        else:
            replacement = copy.deepcopy(inventory)
            target = next(item for item in replacement["accounts"] if item["username"] == username)
            target["password"] = secrets.token_urlsafe(24)
            pending = {"schema_version": 1, "action": "reset", "username": username, "tenant_id": user["tenant_id"], "old_credential_version": user["credential_version"], "base_digest": _digest(inventory), "inventory": replacement}
            _write_private(pending_path, pending, exclusive=True)
        target = next(item for item in replacement["accounts"] if item["username"] == username)
        next_version = pending["old_credential_version"] + 1
        user = _check_user(store.get("user:" + username), entry, verify_secret=False)
        already_applied = user["credential_version"] == next_version and auth.verify_password(user.get("password_hash"), target["password"])
        if not already_applied:
            if user["credential_version"] != pending["old_credential_version"]:
                raise AccountError("Account changed while its reset was pending; review before retrying")
            store.put_if_version(user["id"], {**user, "password_hash": auth.hash_password(target["password"]), "credential_version": next_version}, user["version"])
        _write_private(path, replacement)
        # A file lock protects normal operators; refuse deleting an edited or
        # substituted pending secret even when the main inventory is committed.
        if _read_private(pending_path) != pending:
            raise AccountError("Pending reset file changed; manual review is required")
        pending_path.unlink()
        return {"accounts": 8, "changed": not already_applied, "reset_complete": True}


def set_active(path, username, active):
    if type(active) is not bool:
        raise AccountError("Choose an explicit account enabled state")
    username = _canonical(username)
    with _file_lock(path) as path:
        inventory = validate_inventory(_read_private(path))
        _check_registry(store.get(auth.REGISTRY_ID), inventory, ready=True)
        entry = next((entry for entry in inventory["accounts"] if entry["username"] == username), None)
        if entry is None:
            raise AccountError("Selected account is not in this private inventory")
        user = _check_user(store.get("user:" + username), entry, verify_secret=False)
        changed = user["active"] is not active
        if changed:
            store.put_if_version(user["id"], {**user, "active": active, "credential_version": user["credential_version"] + 1}, user["version"])
        return {"accounts": 8, "changed": changed, "active": active}


class PrivateArguments(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "Tenant account command arguments are invalid; use --help\n")


def main(argv=None):
    parser = PrivateArguments(prog="ticketpilot-tenant-accounts", description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for name in ("generate", "provision"):
        command = commands.add_parser(name)
        command.add_argument("--credentials-file", type=Path, required=True)
        command.add_argument("--units", required=True)
    command = commands.add_parser("apply")
    command.add_argument("--credentials-stdin", action="store_true", required=True)
    for name in ("reset", "disable", "enable"):
        command = commands.add_parser(name)
        command.add_argument("--credentials-file", type=Path, required=True)
        command.add_argument("--username", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "generate":result = generate(args.credentials_file, args.units)
        elif args.action == "provision":result = provision(args.credentials_file, args.units)
        elif args.action == "apply":
            stream = getattr(sys.stdin, "buffer", None)
            data = stream.read(MAX_INVENTORY_BYTES + 1) if stream is not None else sys.stdin.read(MAX_INVENTORY_BYTES + 1).encode("utf-8")
            result = apply_inventory(validate_inventory(_decode(data)))
        elif args.action == "reset":result = reset(args.credentials_file, args.username)
        else:result = set_active(args.credentials_file, args.username, args.action == "enable")
        print(json.dumps(result, sort_keys=True))
        return 0
    except AccountError as exc:
        print(str(exc), file=sys.stderr)
    except Exception:
        print("Tenant account operation failed; preserve private files and review authentication-store access", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
