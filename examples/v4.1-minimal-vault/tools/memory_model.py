"""Shared, read-only v4.1 record semantics."""

from __future__ import annotations

import datetime as dt
import math
import os
from pathlib import Path
from typing import Any

import yaml

from lint import parse_date, parse_datetime, split_frontmatter


FACT_FIELDS = (
    "valid_from", "valid_until", "observed_at", "derived_from", "assertion",
    "confidence", "trust", "pinned", "last_confirmed", "review_after",
)
TRUST_LEVELS = {"external": 0, "agent": 1, "owner": 2}


def config(root: Path, name: str) -> dict[str, Any]:
    path = root / "memory/schema" / name
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a YAML object")
    return data


def enabled(root: Path) -> bool:
    return str(config(root, "version.yaml").get("spec_version")) == "4.1"


def today() -> dt.date:
    return dt.date.fromisoformat(os.environ.get("MEMORY_TODAY", dt.date.today().isoformat()))


def safe_path(root: Path, value: str, prefixes: tuple[str, ...] = ()) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
        raise ValueError(f"invalid vault-relative path: {value!r}")
    path = root / value
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"path escapes vault: {value!r}")
    if prefixes and not any(value.startswith(prefix) for prefix in prefixes):
        raise ValueError(f"path is outside permitted folders: {value!r}")
    # Do not let an in-vault symlink silently redirect a canonical write.
    if any(part.is_symlink() for part in (path, *path.parents) if part.is_relative_to(root)):
        raise ValueError(f"symlink path is not supported: {value!r}")
    return path


def records(root: Path, folder: str, typ: str) -> list[tuple[Path, dict[str, Any]]]:
    rows = []
    for path in sorted((root / folder).rglob("*.md")):
        data, _ = split_frontmatter(path)
        if data.get("type") == typ:
            rows.append((path, data))
    return rows


def observed(data: dict[str, Any]) -> dt.datetime:
    value = data.get("observed_at") or data.get("created_at") or data.get("recorded_at")
    return parse_datetime(value).astimezone(dt.timezone.utc)


def interval(data: dict[str, Any]) -> tuple[dt.date, dt.date]:
    """Exclusive upper bound for v4.1; retain inclusive legacy valid_to."""
    start = parse_date(data.get("valid_from")) or dt.date.min
    if "valid_until" in data:
        end = parse_date(data.get("valid_until")) or dt.date.max
    else:
        legacy = parse_date(data.get("valid_to"))
        end = legacy + dt.timedelta(days=1) if legacy and legacy < dt.date.max else dt.date.max
    return start, end


def current(data: dict[str, Any]) -> bool:
    return data.get("valid_until", data.get("valid_to")) is None


def visible(data: dict[str, Any], as_of: dt.date | None = None) -> bool:
    if data.get("status") == "retracted":
        return False
    if as_of is None:
        return current(data)
    start, end = interval(data)
    return start <= as_of < end


def agent_roles(root: Path, agent: str | None) -> list[str]:
    for entry in config(root, "roles.yaml").get("agents", []):
        if entry.get("id") == agent:
            return entry.get("roles", [])
    return []


def effective_fact(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    result = dict(data)
    result.setdefault("assertion", "stated")
    result.setdefault("trust", "owner" if "admin" in agent_roles(root, data.get("agent_id")) else "agent")
    result["observed_at"] = observed(data).isoformat().replace("+00:00", "Z")
    return result


def confidence(value: Any) -> float | None:
    if value is None or value in ("high", "medium", "low"):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("confidence must be a finite number in 0..1 or a legacy high/medium/low label")
    if not 0 <= value <= 1:
        raise ValueError("confidence must be in 0..1")
    return float(value)


def parse_confidence(value: str) -> str | float:
    if value in {"high", "medium", "low"}:
        return value
    number = float(value)
    confidence(number)
    return number


def enforce_trust(root: Path, data: dict[str, Any], agent: str, reviewed: bool) -> None:
    if not enabled(root):
        return
    roles = config(root, "roles.yaml")
    namespace = next((ns for ns in roles.get("namespaces", []) if ns.get("id") == "facts"), {})
    trust = data.get("trust", "owner" if "admin" in agent_roles(root, agent) else "agent")
    if trust not in TRUST_LEVELS:
        raise ValueError(f"unknown trust class: {trust!r}")
    caps = namespace.get("max_trust_by_role")
    if caps is not None:
        if not isinstance(caps, dict) or any(v not in TRUST_LEVELS for v in caps.values()):
            raise ValueError("invalid max_trust_by_role policy")
        limits = [TRUST_LEVELS[caps[role]] for role in agent_roles(root, agent) if role in caps]
        if not limits or TRUST_LEVELS[trust] > max(limits):
            raise ValueError(f"agent {agent!r} cannot assert trust: {trust} under max_trust_by_role")
    if trust == "external" and namespace.get("external_requires_review") and not reviewed:
        raise ValueError("external facts require review; use propose.py create and review.py")
