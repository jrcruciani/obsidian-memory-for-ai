"""Core data model, path safety, frontmatter I/O, entity resolution, and source digests."""

from __future__ import annotations

import datetime as dt
import hashlib
import math
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from .yaml_io import YAMLError, dump_yaml, load_yaml

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---(?:\n|\Z)", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
AGENT_ID_RE = re.compile(r"^agent-[a-z0-9][a-z0-9-]*-[a-f0-9]{8,}$")
DECISION_ID_RE = re.compile(r"^DEC-[0-9]{3,}[a-z0-9-]*$")

TRUST_LEVELS = {"external": 0, "agent": 1, "owner": 2}
ENTITY_KINDS = ("person", "project", "organization", "instrument", "system", "place", "concept")
ASSERTION_KINDS = ("stated", "observed", "inferred")
SIGNAL_KINDS = (
    "gap",
    "contradiction",
    "friction",
    "stale",
    "observation",
    "broken_reference",
    "uncurated_claim",
)
SIGNAL_STATUSES = ("open", "proposed", "resolved", "dismissed")
PROPOSAL_STATUSES = ("draft", "proposed", "changes_requested", "approved", "rejected", "conflict", "published")
REVIEW_VERDICTS = ("approved", "rejected", "changes_requested")
NAMESPACES = ("entities", "facts", "events", "skills", "guidance", "decisions", "mixed")


def utc_now() -> dt.datetime:
    override = os.environ.get("KF_NOW")
    if override:
        return parse_datetime(override)
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso_utc(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today() -> dt.date:
    raw = os.environ.get("KF_TODAY") or os.environ.get("MEMORY_TODAY")
    if raw:
        return dt.date.fromisoformat(raw)
    return dt.date.today()


def parse_date(value: Any) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        raise ValueError(f"expected YYYY-MM-DD date, got datetime {value!r}")
    if isinstance(value, dt.date):
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"expected ISO date YYYY-MM-DD, got {value!r}")
    return dt.date.fromisoformat(value)


def parse_datetime(value: Any) -> dt.datetime:
    if isinstance(value, dt.datetime) and value.tzinfo is not None:
        return value.astimezone(dt.timezone.utc)
    if not isinstance(value, str) or "T" not in value:
        raise ValueError(f"expected timezone-aware ISO datetime, got {value!r}")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(f"datetime must include timezone offset or 'Z': {value!r}")
    return parsed.astimezone(dt.timezone.utc)


def slugify(text: str, limit: int = 28) -> str:
    folded = fold_text(text)
    slug = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")
    return slug[:limit].strip("-") or "item"


def fold_text(value: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(ch)
    ).strip()


def rel_path(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def safe_path(root: Path, rel: str, allowed_prefixes: tuple[str, ...] = ()) -> Path:
    if not isinstance(rel, str) or not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
        raise ValueError(f"invalid vault-relative path: {rel!r}")
    candidate = root / rel
    root_resolved = root.resolve()
    if not candidate.resolve().is_relative_to(root_resolved):
        raise ValueError(f"path escapes vault root: {rel!r}")
    for part in (candidate, *candidate.parents):
        if part == root or not part.is_relative_to(root):
            break
        if part.is_symlink():
            raise ValueError(f"symlinks are forbidden inside canonical vault paths: {rel!r}")
    if allowed_prefixes and not any(rel.startswith(prefix) for prefix in allowed_prefixes):
        raise ValueError(f"path {rel!r} outside permitted prefixes {allowed_prefixes}")
    return candidate


def split_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    return split_frontmatter_text(text, source=str(path))


def split_frontmatter_text(text: str, source: str = "<memory>") -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        parsed = load_yaml(match.group(1))
    except YAMLError as exc:
        raise ValueError(f"{source}: invalid YAML frontmatter: {exc}") from exc
    if parsed is None:
        parsed = {}
    if not isinstance(parsed, dict):
        raise ValueError(f"{source}: frontmatter must be a YAML mapping")
    return parsed, text[match.end():]


def format_markdown(frontmatter: dict[str, Any], body: str = "", *, sort_keys: bool = False) -> str:
    yaml_block = dump_yaml(frontmatter, sort_keys=sort_keys).strip()
    header = f"---\n{yaml_block}\n---\n"
    clean_body = body.strip("\n")
    return f"{header}\n{clean_body}\n" if clean_body else header


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def write_markdown(path: Path, frontmatter: dict[str, Any], body: str = "", *, sort_keys: bool = False) -> None:
    atomic_write_text(path, format_markdown(frontmatter, body, sort_keys=sort_keys))


def file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = load_yaml(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected YAML mapping")
    return data


def load_manifest(root: Path) -> dict[str, Any]:
    return load_yaml_file(root / "factory/schema/manifest.yaml")


def load_policy(root: Path) -> dict[str, Any]:
    return load_yaml_file(root / "factory/schema/policy.yaml")


def load_predicates(root: Path) -> dict[str, dict[str, Any]]:
    raw = load_yaml_file(root / "factory/schema/predicates.yaml")
    preds = raw.get("predicates", [])
    result: dict[str, dict[str, Any]] = {}
    if isinstance(preds, list):
        for item in preds:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                result[item["id"]] = item
            elif isinstance(item, str):
                result[item] = {"id": item}
    return result


def load_entities(root: Path) -> dict[str, dict[str, Any]]:
    reg_path = root / "knowledge/entities.md"
    if not reg_path.is_file():
        return {}
    fm, _ = split_frontmatter(reg_path)
    entries = fm.get("entities", [])
    if not isinstance(entries, list):
        raise ValueError("knowledge/entities.md: entities must be a list")
    out: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            aliases = entry.get("aliases") or []
            if not isinstance(aliases, list):
                raise ValueError(f"aliases for {entry['id']} must be a list")
            out[entry["id"]] = dict(entry, aliases=list(aliases))
    return out


def entity_Folded_names(entry: dict[str, Any]) -> set[str]:
    candidates = [entry.get("id", ""), entry.get("display", ""), *(entry.get("aliases") or [])]
    return {fold_text(val) for val in candidates if isinstance(val, str) and val.strip()}


def resolve_entity(root: Path, query: str) -> list[str]:
    needle = fold_text(query)
    if not needle:
        return []
    entities = load_entities(root)
    return sorted(eid for eid, entry in entities.items() if needle in entity_Folded_names(entry))


def validate_confidence(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"confidence must be a float in 0.0..1.0 or null (legacy string labels are rejected in v5.0), got {value!r}")
    if not (0.0 <= float(value) <= 1.0):
        raise ValueError(f"confidence must be between 0.0 and 1.0, got {value!r}")
    return float(value)


def fact_interval(data: dict[str, Any]) -> tuple[dt.date, dt.date]:
    start = parse_date(data.get("valid_from")) or dt.date.min
    end = parse_date(data.get("valid_until")) or dt.date.max
    return start, end


def is_active_head(data: dict[str, Any]) -> bool:
    """Return True if the record is the structural active/accepted head for its slot."""
    rtype = data.get("type")
    status = data.get("status", "active")
    if rtype == "decision":
        return status == "accepted"
    return status == "active"


def is_current_record(data: dict[str, Any]) -> bool:
    if data.get("type") == "fact":
        return is_fact_visible(data)
    return is_active_head(data)


def is_fact_visible(data: dict[str, Any], as_of: dt.date | None = None) -> bool:
    status = data.get("status", "active")
    if status == "retracted":
        return False
    if status == "superseded" and data.get("valid_until") is None:
        return False
    ref = as_of or today()
    start, end = fact_interval(data)
    return start <= ref < end


def scan_records(root: Path, rel_folder: str, record_type: str | None = None) -> list[tuple[Path, dict[str, Any], str]]:
    folder = root / rel_folder
    if not folder.exists():
        return []
    rows: list[tuple[Path, dict[str, Any], str]] = []
    for path in sorted(folder.rglob("*.md")):
        if any(part.startswith("_") for part in path.relative_to(root).parts):
            continue
        fm, body = split_frontmatter(path)
        if record_type is None or fm.get("type") == record_type:
            rows.append((path, fm, body))
    return rows


def canonical_source_digest(root: Path, ref_date: dt.date | None = None) -> str:
    """Compute a deterministic SHA-256 digest over all canonical truth & factory state."""
    date_val = (ref_date or today()).isoformat()
    hasher = hashlib.sha256()
    hasher.update(f"kf-v5.0-date:{date_val}\n".encode("utf-8"))
    for folder in ("knowledge", "factory/schema", "factory/signals", "factory/proposals", "factory/reviews", "factory/receipts", "sources"):
        base = root / folder
        if not base.exists():
            continue
        for path in sorted(p for p in base.rglob("*") if p.is_file() and not p.name.startswith(".")):
            rel = rel_path(path, root)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            hasher.update(f"{rel}:{digest}\n".encode("utf-8"))
    return "sha256:" + hasher.hexdigest()
