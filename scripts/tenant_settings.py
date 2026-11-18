"""Shared non-secret unit-label validation for provider deployment scripts."""
import re


def units_csv(value):
    units = [part.strip() for part in value.split(",")] if isinstance(value, str) else []
    if len(units) != 8 or any(not unit or len(unit) > 40 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]*", unit) for unit in units):
        raise ValueError("Provide exactly eight valid unit labels")
    return ",".join(units)
