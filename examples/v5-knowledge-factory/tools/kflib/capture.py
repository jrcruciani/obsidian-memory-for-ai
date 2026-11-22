"""Executor low-friction capture layer: append-only `signals` and `events`."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .model import (
    NAMESPACES,
    SIGNAL_KINDS,
    SLUG_RE,
    atomic_write_text,
    format_markdown,
    iso_utc,
    load_policy,
    parse_datetime,
    rel_path,
    scan_records,
    slugify,
    today,
    utc_now,
)
from .transact import enforce_no_pending_recovery, get_agent_roles, validate_candidate_writes
from .yaml_io import load_yaml


def _enforce_can_capture(root: Path, agent_id: str) -> None:
    policy = load_policy(root)
    roles_cfg = policy.get("roles", {})
    roles = get_agent_roles(root, agent_id)
    if not any(roles_cfg.get(r, {}).get("can_capture", True) for r in roles):
        raise ValueError(f"agent {agent_id!r} is not permitted to capture signals/events")


def find_signal_by_key(root: Path, idempotency_key: str) -> tuple[str, dict[str, Any]] | None:
    for path, fm, _ in scan_records(root, "factory/signals", "signal"):
        if fm.get("idempotency_key") == idempotency_key:
            return rel_path(path, root), fm
    return None


def capture_signal(
    root: Path,
    *,
    emitted_by: str,
    kind: str,
    summary: str,
    severity: str = "medium",
    target_namespace: str = "facts",
    entities: list[str] | None = None,
    related_paths: list[str] | None = None,
    evidence: list[str] | None = None,
    idempotency_key: str | None = None,
    body: str = "",
) -> dict[str, Any]:
    enforce_no_pending_recovery(root)
    _enforce_can_capture(root, emitted_by)
    if kind not in SIGNAL_KINDS:
        raise ValueError(f"invalid signal kind {kind!r}; allowed: {SIGNAL_KINDS}")
    if severity not in {"low", "medium", "high"}:
        raise ValueError(f"invalid severity {severity!r}")
    if target_namespace not in NAMESPACES:
        raise ValueError(f"invalid target_namespace {target_namespace!r}")
    clean_summary = summary.strip()
    if not clean_summary:
        raise ValueError("signal summary must be non-empty")

    if idempotency_key:
        existing = find_signal_by_key(root, idempotency_key)
        if existing is not None:
            rel, fm = existing
            return dict(fm, path=rel, idempotent_replay=True)

    now = utc_now()
    date_folder = today().isoformat()
    stamp = now.strftime("%Y%m%dt%H%M%Sz")
    seed = idempotency_key or f"{emitted_by}:{kind}:{clean_summary}:{iso_utc(now)}"
    suffix = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]
    sig_id = f"sig-{slugify(clean_summary, 20)}-{stamp}-{suffix}"
    rel = f"factory/signals/{date_folder}/{sig_id}.md"

    fm = {
        "type": "signal",
        "id": sig_id,
        "kind": kind,
        "severity": severity,
        "status": "open",
        "created_at": iso_utc(now),
        "emitted_by": emitted_by,
        "summary": clean_summary,
        "target_namespace": target_namespace,
        "entities": list(entities or []),
        "related_paths": list(related_paths or []),
        "evidence": list(evidence or []),
        "idempotency_key": idempotency_key,
        "proposal_id": None,
        "resolved_at": None,
        "resolved_by_receipt": None,
        "resolution_note": None,
    }
    md_body = body.strip() or f"# Signal ({kind}): {clean_summary}\n\nEmitted by `{emitted_by}` for curation into `{target_namespace}`."
    rendered = format_markdown(fm, md_body)
    validate_candidate_writes(root, {rel: rendered})
    atomic_write_text(root / rel, rendered)
    return dict(fm, path=rel, idempotent_replay=False)


def capture_event(
    root: Path,
    *,
    recorded_by: str,
    event_id: str,
    occurred_at: str,
    summary: str,
    entities: list[str] | None = None,
    sources: list[str] | None = None,
    asserts_raw: str | list[dict[str, Any]] | None = None,
    tags: list[str] | None = None,
    body: str = "",
) -> dict[str, Any]:
    enforce_no_pending_recovery(root)
    _enforce_can_capture(root, recorded_by)
    if not SLUG_RE.fullmatch(event_id):
        raise ValueError(f"event_id must be a valid slug, got {event_id!r}")
    occ = parse_datetime(occurred_at)
    clean_summary = summary.strip()
    if not clean_summary:
        raise ValueError("event summary must be non-empty")

    rel = f"knowledge/events/{occ.date().isoformat()}/{event_id}.md"
    if (root / rel).exists():
        raise ValueError(f"append-only event already exists: {rel}")

    parsed_asserts: list[dict[str, Any]] | None = None
    if isinstance(asserts_raw, str) and asserts_raw.strip():
        loaded = json.loads(asserts_raw) if asserts_raw.lstrip().startswith("[") else load_yaml(asserts_raw)
        if not isinstance(loaded, list):
            raise ValueError("--asserts must parse to a list of {entity, predicate, value} objects")
        parsed_asserts = loaded
    elif isinstance(asserts_raw, list):
        parsed_asserts = asserts_raw

    fm: dict[str, Any] = {
        "type": "event",
        "id": event_id,
        "occurred_at": iso_utc(occ),
        "recorded_by": recorded_by,
        "summary": clean_summary,
        "entities": list(entities or []),
        "sources": list(sources or []),
    }
    if parsed_asserts is not None:
        fm["asserts"] = parsed_asserts
    if tags is not None:
        fm["tags"] = list(tags)

    md_body = body.strip() or f"# {clean_summary}"
    rendered = format_markdown(fm, md_body)
    validate_candidate_writes(root, {rel: rendered})
    atomic_write_text(root / rel, rendered)
    return dict(fm, path=rel)
