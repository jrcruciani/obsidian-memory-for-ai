"""Crash-safe atomic transactions, living knowledge operations, and unified receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .model import (
    AGENT_ID_RE,
    DECISION_ID_RE,
    SLUG_RE,
    TRUST_LEVELS,
    atomic_write_text,
    file_sha256,
    format_markdown,
    iso_utc,
    load_policy,
    load_yaml_file,
    parse_date,
    parse_datetime,
    rel_path,
    safe_path,
    scan_records,
    slugify,
    split_frontmatter,
    split_frontmatter_text,
    text_sha256,
    today,
    utc_now,
    validate_confidence,
    write_markdown,
)
from .rebuild import rebuild_all
from .schema_check import lint_vault
from .yaml_io import dump_yaml, load_yaml

SUPPORTED_OPS = (
    "upsert_entity",
    "create_event",
    "create_fact",
    "supersede_fact",
    "confirm_fact",
    "retract_fact",
    "create_skill",
    "supersede_skill",
    "retract_skill",
    "create_guidance",
    "supersede_guidance",
    "retract_guidance",
    "create_decision",
    "supersede_decision",
)


def git_head(root: Path) -> str | None:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return res.stdout.strip() if res.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def get_agent_entry(root: Path, agent_id: str) -> dict[str, Any]:
    if not isinstance(agent_id, str) or not AGENT_ID_RE.fullmatch(agent_id):
        raise ValueError(f"invalid agent ID {agent_id!r}; expected agent-<name>-<8+hex>")
    policy = load_policy(root)
    for ag in policy.get("agents", []):
        if isinstance(ag, dict) and ag.get("id") == agent_id:
            return ag
    raise ValueError(f"unknown agent {agent_id!r}; declare in factory/schema/policy.yaml")


def get_agent_roles(root: Path, agent_id: str) -> list[str]:
    entry = get_agent_entry(root, agent_id)
    return [str(r) for r in entry.get("roles", [])]


def enforce_direct_transact_allowed(root: Path, actor_id: str) -> None:
    policy = load_policy(root)
    roles_cfg = policy.get("roles", {})
    actor_roles = get_agent_roles(root, actor_id)
    if not any(roles_cfg.get(r, {}).get("direct_transact") is True for r in actor_roles):
        raise ValueError(
            f"actor {actor_id!r} (roles={actor_roles}) is not permitted to run direct_transact; "
            "use `kf.py capture signal` or `kf.py propose create` -> `review` -> `publish`"
        )


def _op_namespace(kind: str) -> str:
    if kind == "upsert_entity":
        return "entities"
    if kind == "create_event":
        return "events"
    if kind.endswith("_fact"):
        return "facts"
    if kind.endswith("_skill"):
        return "skills"
    if kind.endswith("_guidance"):
        return "guidance"
    if kind.endswith("_decision"):
        return "decisions"
    return "mixed"


def enforce_op_trust_policy(
    root: Path,
    op: dict[str, Any],
    author_id: str,
    *,
    reviewed: bool,
) -> None:
    kind = str(op.get("op", ""))
    if kind in {"upsert_entity", "create_event", "confirm_fact", "retract_fact", "retract_skill", "retract_guidance", "create_decision", "supersede_decision"}:
        return
    policy = load_policy(root)
    roles_cfg = policy.get("roles", {})
    author_roles = get_agent_roles(root, author_id)
    default_trust = "owner" if "owner" in author_roles else "agent"
    trust = str(op.get("trust") or default_trust)
    if trust not in TRUST_LEVELS:
        raise ValueError(f"invalid trust level {trust!r}")

    # Role max_trust cap
    caps = [TRUST_LEVELS[roles_cfg[r]["max_trust"]] for r in author_roles if r in roles_cfg and "max_trust" in roles_cfg[r]]
    if caps and TRUST_LEVELS[trust] > max(caps):
        raise ValueError(f"actor {author_id!r} (roles={author_roles}) cannot assert trust={trust!r}")

    ns_name = _op_namespace(kind)
    ns_cfg = next((ns for ns in policy.get("namespaces", []) if isinstance(ns, dict) and ns.get("id") == ns_name), {})
    if trust == "external" and ns_cfg.get("external_requires_review", True) and not reviewed:
        raise ValueError(
            f"trust='external' in namespace '{ns_name}' requires independent proposal review (`propose` -> `review` -> `publish`)"
        )


def find_committed_receipt_by_key(root: Path, idempotency_key: str) -> dict[str, Any] | None:
    for _, fm, _ in scan_records(root, "factory/receipts", "receipt"):
        if fm.get("idempotency_key") == idempotency_key and fm.get("status") == "committed":
            return fm
    return None


def _staging_dir(root: Path, txn_id: str) -> Path:
    if not re.fullmatch(r"txn-[a-z0-9][a-z0-9_-]*", txn_id):
        raise ValueError(f"invalid transaction_id {txn_id!r}")
    return safe_path(root, f"factory/_staging/{txn_id}")


def begin_transaction(
    root: Path,
    *,
    idempotency_key: str,
    actor_id: str,
    expected_revision: str | None = None,
) -> dict[str, Any]:
    if not idempotency_key or not idempotency_key.strip():
        raise ValueError("idempotency_key must be non-empty")
    enforce_direct_transact_allowed(root, actor_id)

    prior = find_committed_receipt_by_key(root, idempotency_key)
    if prior is not None:
        return {
            "transaction_id": prior["id"],
            "receipt_id": prior["id"],
            "status": "committed",
            "idempotent_replay": True,
            "idempotency_key": idempotency_key,
            "actor_id": prior["actor_id"],
        }

    staging_root = root / "factory/_staging"
    if staging_root.exists():
        for meta_path in sorted(staging_root.glob("*/_meta.yaml")):
            existing = load_yaml_file(meta_path)
            if existing.get("idempotency_key") == idempotency_key:
                if existing.get("actor_id") != actor_id:
                    raise ValueError("idempotency_key is already staged by a different actor")
                return existing

    now = utc_now()
    stamp = now.strftime("%Y%m%dt%H%M%Sz")
    suffix = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:8]
    txn_id = f"txn-{slugify(idempotency_key, 20)}-{stamp}-{suffix}"
    meta: dict[str, Any] = {
        "transaction_id": txn_id,
        "idempotency_key": idempotency_key,
        "actor_id": actor_id,
        "created_at": iso_utc(now),
        "expected_revision": expected_revision,
        "status": "pending",
        "ops": [],
    }
    sdir = _staging_dir(root, txn_id)
    atomic_write_text(sdir / "_meta.yaml", dump_yaml(meta))
    atomic_write_text(sdir / ".pending", "pending\n")
    return meta


def add_operations(root: Path, txn_id: str, ops: list[dict[str, Any]]) -> dict[str, Any]:
    sdir = _staging_dir(root, txn_id)
    meta_path = sdir / "_meta.yaml"
    if not meta_path.is_file():
        raise ValueError(f"staged transaction not found: {txn_id}")
    meta = load_yaml_file(meta_path)
    if meta.get("status") != "pending":
        raise ValueError(f"transaction {txn_id} is not pending (status={meta.get('status')!r})")
    if not isinstance(ops, list) or not ops:
        raise ValueError("at least one operation is required")
    for op in ops:
        if not isinstance(op, dict) or op.get("op") not in SUPPORTED_OPS:
            raise ValueError(f"unsupported operation {op!r}; allowed: {SUPPORTED_OPS}")
        enforce_op_trust_policy(root, op, str(meta["actor_id"]), reviewed=False)
    meta["ops"] = [*meta.get("ops", []), *ops]
    atomic_write_text(meta_path, dump_yaml(meta))
    return meta


def _next_history_slot(root: Path, writes: dict[str, str | None], hist_dir_rel: str, date_stem: str) -> str:
    candidate = f"{hist_dir_rel}/{date_stem}.md"
    counter = 2
    while safe_path(root, candidate).exists() or candidate in writes:
        candidate = f"{hist_dir_rel}/{date_stem}-{counter}.md"
        counter += 1
    return candidate


def _read_effective_text(root: Path, writes: dict[str, str | None], rel: str) -> str | None:
    if rel in writes:
        return writes[rel]
    p = safe_path(root, rel)
    return p.read_text(encoding="utf-8") if p.is_file() else None


def _distinct_id(base_id: str, existing_id: str, suffix_hint: str) -> str:
    cand = f"{base_id}-{suffix_hint}"
    if cand == existing_id:
        cand = f"{cand}-2"
    return cand


def compile_operations(
    root: Path,
    ops: list[dict[str, Any]],
    *,
    actor_id: str,
    reviewed: bool,
) -> dict[str, str | None]:
    """Compile high-level operations into a deterministic map of {vault_rel_path: new_markdown_or_None}."""
    writes: dict[str, str | None] = {}
    now = utc_now()
    now_iso = iso_utc(now)
    ref_today = today().isoformat()
    actor_roles = get_agent_roles(root, actor_id)
    default_trust = "owner" if "owner" in actor_roles else "agent"

    for op in ops:
        kind = str(op.get("op", ""))
        if kind not in SUPPORTED_OPS:
            raise ValueError(f"unsupported op {kind!r}")
        enforce_op_trust_policy(root, op, actor_id, reviewed=reviewed)

        if kind == "upsert_entity":
            eid = str(op.get("entity_id") or op.get("id") or "")
            if not SLUG_RE.fullmatch(eid):
                raise ValueError(f"upsert_entity requires slug entity_id, got {eid!r}")
            ent_rel = "knowledge/entities.md"
            cur_text = _read_effective_text(root, writes, ent_rel)
            if cur_text is None:
                fm: dict[str, Any] = {"type": "entity-registry", "id": "entity-registry", "entities": []}
                body = "# Canonical Entities"
            else:
                fm, body = split_frontmatter_text(cur_text, source=ent_rel)
            ent_list = list(fm.get("entities") or [])
            new_entry = {
                "id": eid,
                "kind": str(op.get("kind", "entity")),
                "display": str(op.get("display", eid)),
                "aliases": list(op.get("aliases") or []),
            }
            if op.get("summary"):
                new_entry["summary"] = str(op["summary"])
            replaced = False
            for idx, existing in enumerate(ent_list):
                if isinstance(existing, dict) and existing.get("id") == eid:
                    ent_list[idx] = new_entry
                    replaced = True
                    break
            if not replaced:
                ent_list.append(new_entry)
            ent_list.sort(key=lambda item: str(item.get("id", "")))
            fm["entities"] = ent_list
            writes[ent_rel] = format_markdown(fm, body)

        elif kind == "create_event":
            ev_id = str(op.get("event_id") or op.get("id") or "")
            if not SLUG_RE.fullmatch(ev_id):
                raise ValueError(f"create_event requires slug event_id, got {ev_id!r}")
            occ = parse_datetime(op.get("occurred_at"))
            summary = str(op.get("summary") or "").strip()
            if not summary:
                raise ValueError("create_event requires non-empty summary")
            target_rel = f"knowledge/events/{occ.date().isoformat()}/{ev_id}.md"
            if _read_effective_text(root, writes, target_rel) is not None:
                raise ValueError(f"append-only event already exists: {target_rel}")
            ev_fm: dict[str, Any] = {
                "type": "event",
                "id": ev_id,
                "occurred_at": iso_utc(occ),
                "recorded_by": actor_id,
                "summary": summary,
                "entities": list(op.get("entities") or []),
                "sources": list(op.get("sources") or []),
            }
            if op.get("asserts") is not None:
                ev_fm["asserts"] = op["asserts"]
            if op.get("tags") is not None:
                ev_fm["tags"] = list(op["tags"])
            writes[target_rel] = format_markdown(ev_fm, str(op.get("body") or f"# {summary}"))

        elif kind in {"create_fact", "supersede_fact", "confirm_fact", "retract_fact"}:
            ent = str(op.get("entity") or "")
            pred = str(op.get("predicate") or "")
            if not (SLUG_RE.fullmatch(ent) and SLUG_RE.fullmatch(pred)):
                raise ValueError("fact operations require slug entity and predicate")
            slot_rel = f"knowledge/facts/{ent}/{pred}.md"
            cur_text = _read_effective_text(root, writes, slot_rel)
            if op.get("precondition_hash"):
                p_disk = safe_path(root, slot_rel)
                actual_hash = file_sha256(p_disk) if p_disk.is_file() else None
                if actual_hash != op["precondition_hash"]:
                    raise ValueError(f"precondition_hash mismatch on {slot_rel}")

            if kind == "create_fact":
                if cur_text is not None:
                    raise ValueError(f"fact already exists at {slot_rel}; use supersede_fact")
                if "value" not in op:
                    raise ValueError("create_fact requires value")
                conf = validate_confidence(op.get("confidence"))
                fact_fm: dict[str, Any] = {
                    "type": "fact",
                    "id": str(op.get("id") or f"fact-{ent}-{pred}"),
                    "entity": ent,
                    "predicate": pred,
                    "value": op["value"],
                    "status": "active",
                    "valid_from": str(op["valid_from"]) if op.get("valid_from") else None,
                    "valid_until": str(op["valid_until"]) if op.get("valid_until") else None,
                    "observed_at": str(op.get("observed_at") or now_iso),
                    "confidence": conf,
                    "assertion": str(op.get("assertion") or "stated"),
                    "trust": str(op.get("trust") or default_trust),
                    "derived_from": list(op.get("derived_from") or []),
                    "supersedes": None,
                    "pinned": bool(op.get("pinned", False)),
                    "last_confirmed": str(op.get("last_confirmed") or ref_today),
                    "review_after": str(op["review_after"]) if op.get("review_after") else None,
                }
                writes[slot_rel] = format_markdown(fact_fm, str(op.get("body") or ""))

            elif kind == "supersede_fact":
                if cur_text is None:
                    raise ValueError(f"cannot supersede missing fact {slot_rel}")
                if "value" not in op:
                    raise ValueError("supersede_fact requires value")
                old_fm, old_body = split_frontmatter_text(cur_text, source=slot_rel)
                new_valid_from = str(op.get("valid_from") or ref_today)
                parse_date(new_valid_from)
                hist_stem = str(old_fm.get("valid_from") or parse_datetime(old_fm["observed_at"]).date().isoformat())
                hist_rel = _next_history_slot(root, writes, f"knowledge/facts/{ent}/{pred}", hist_stem)
                archived_fm = dict(old_fm, status="superseded", valid_until=new_valid_from, pinned=False)
                writes[hist_rel] = format_markdown(archived_fm, old_body)

                conf = validate_confidence(op.get("confidence", old_fm.get("confidence")))
                new_id = str(op.get("id") or _distinct_id(f"fact-{ent}-{pred}", str(old_fm["id"]), new_valid_from))
                new_fm: dict[str, Any] = {
                    "type": "fact",
                    "id": new_id,
                    "entity": ent,
                    "predicate": pred,
                    "value": op["value"],
                    "status": "active",
                    "valid_from": new_valid_from,
                    "valid_until": str(op["valid_until"]) if op.get("valid_until") else None,
                    "observed_at": str(op.get("observed_at") or now_iso),
                    "confidence": conf,
                    "assertion": str(op.get("assertion") or "stated"),
                    "trust": str(op.get("trust") or default_trust),
                    "derived_from": list(op.get("derived_from") or []),
                    "supersedes": hist_rel,
                    "pinned": bool(op.get("pinned", old_fm.get("pinned", False))),
                    "last_confirmed": str(op.get("last_confirmed") or new_valid_from),
                    "review_after": str(op["review_after"]) if op.get("review_after") else None,
                }
                writes[slot_rel] = format_markdown(new_fm, str(op.get("body") or ""))

            elif kind == "confirm_fact":
                if cur_text is None:
                    raise ValueError(f"cannot confirm missing fact {slot_rel}")
                old_fm, old_body = split_frontmatter_text(cur_text, source=slot_rel)
                updated_fm = dict(old_fm, last_confirmed=str(op.get("last_confirmed") or ref_today))
                if "review_after" in op:
                    updated_fm["review_after"] = op["review_after"]
                writes[slot_rel] = format_markdown(updated_fm, old_body)

            elif kind == "retract_fact":
                if cur_text is None:
                    raise ValueError(f"cannot retract missing fact {slot_rel}")
                reason = str(op.get("reason") or op.get("retraction_reason") or "").strip()
                if not reason:
                    raise ValueError("retract_fact requires non-empty reason")
                old_fm, old_body = split_frontmatter_text(cur_text, source=slot_rel)
                ret_fm = dict(
                    old_fm,
                    status="retracted",
                    pinned=False,
                    retracted_at=now_iso,
                    retraction_reason=reason,
                )
                writes[slot_rel] = format_markdown(ret_fm, old_body)

        elif kind in {"create_skill", "supersede_skill", "retract_skill"}:
            slug = str(op.get("slug") or "")
            if not SLUG_RE.fullmatch(slug):
                raise ValueError(f"skill op requires slug, got {slug!r}")
            slot_rel = f"knowledge/skills/{slug}.md"
            cur_text = _read_effective_text(root, writes, slot_rel)
            if kind == "create_skill":
                if cur_text is not None:
                    raise ValueError(f"skill already exists at {slot_rel}; use supersede_skill")
                sk_fm: dict[str, Any] = {
                    "type": "skill",
                    "id": str(op.get("id") or f"skill-{slug}-v1"),
                    "slug": slug,
                    "title": str(op["title"]),
                    "status": "active",
                    "version": int(op.get("version", 1)),
                    "domain": str(op["domain"]),
                    "triggers": list(op["triggers"]),
                    "inputs": list(op.get("inputs") or []),
                    "outputs": list(op.get("outputs") or []),
                    "verification": list(op["verification"]),
                    "entities": list(op.get("entities") or []),
                    "derived_from": list(op.get("derived_from") or []),
                    "trust": str(op.get("trust") or default_trust),
                    "confidence": validate_confidence(op.get("confidence", 0.9)),
                    "observed_at": str(op.get("observed_at") or now_iso),
                    "last_confirmed": str(op.get("last_confirmed") or ref_today),
                    "review_after": str(op["review_after"]) if op.get("review_after") else None,
                    "supersedes": None,
                    "pinned": bool(op.get("pinned", False)),
                }
                writes[slot_rel] = format_markdown(sk_fm, str(op.get("body") or f"# {op['title']}"))
            elif kind == "supersede_skill":
                if cur_text is None:
                    raise ValueError(f"cannot supersede missing skill {slot_rel}")
                old_fm, old_body = split_frontmatter_text(cur_text, source=slot_rel)
                hist_rel = _next_history_slot(root, writes, f"knowledge/skills/{slug}", ref_today)
                writes[hist_rel] = format_markdown(dict(old_fm, status="superseded", pinned=False), old_body)
                next_ver = int(op.get("version") or (int(old_fm.get("version", 1)) + 1))
                sk_fm = {
                    "type": "skill",
                    "id": str(op.get("id") or _distinct_id(f"skill-{slug}", str(old_fm["id"]), f"v{next_ver}")),
                    "slug": slug,
                    "title": str(op.get("title") or old_fm["title"]),
                    "status": "active",
                    "version": next_ver,
                    "domain": str(op.get("domain") or old_fm["domain"]),
                    "triggers": list(op.get("triggers") or old_fm["triggers"]),
                    "inputs": list((op.get("inputs") if "inputs" in op else old_fm.get("inputs")) or []),
                    "outputs": list((op.get("outputs") if "outputs" in op else old_fm.get("outputs")) or []),
                    "verification": list(op.get("verification") or old_fm["verification"]),
                    "entities": list((op.get("entities") if "entities" in op else old_fm.get("entities")) or []),
                    "derived_from": list((op.get("derived_from") if "derived_from" in op else old_fm.get("derived_from")) or []),
                    "trust": str(op.get("trust") or default_trust),
                    "confidence": validate_confidence(op.get("confidence", old_fm.get("confidence"))),
                    "observed_at": str(op.get("observed_at") or now_iso),
                    "last_confirmed": str(op.get("last_confirmed") or ref_today),
                    "review_after": str(op["review_after"]) if op.get("review_after") else None,
                    "supersedes": hist_rel,
                    "pinned": bool(op.get("pinned", old_fm.get("pinned", False))),
                }
                writes[slot_rel] = format_markdown(sk_fm, str(op.get("body") or old_body))
            elif kind == "retract_skill":
                if cur_text is None:
                    raise ValueError(f"cannot retract missing skill {slot_rel}")
                reason = str(op.get("reason") or op.get("retraction_reason") or "").strip()
                if not reason:
                    raise ValueError("retract_skill requires reason")
                old_fm, old_body = split_frontmatter_text(cur_text, source=slot_rel)
                writes[slot_rel] = format_markdown(
                    dict(old_fm, status="retracted", pinned=False, retracted_at=now_iso, retraction_reason=reason),
                    old_body,
                )

        elif kind in {"create_guidance", "supersede_guidance", "retract_guidance"}:
            slug = str(op.get("slug") or "")
            if not SLUG_RE.fullmatch(slug):
                raise ValueError(f"guidance op requires slug, got {slug!r}")
            slot_rel = f"knowledge/guidance/{slug}.md"
            cur_text = _read_effective_text(root, writes, slot_rel)
            if kind == "create_guidance":
                if cur_text is not None:
                    raise ValueError(f"guidance already exists at {slot_rel}; use supersede_guidance")
                gd_fm: dict[str, Any] = {
                    "type": "guidance",
                    "id": str(op.get("id") or f"guid-{slug}-v1"),
                    "slug": slug,
                    "title": str(op["title"]),
                    "status": "active",
                    "domain": str(op["domain"]),
                    "scope": str(op.get("scope", "all")),
                    "priority": str(op.get("priority", "normal")),
                    "policy_rule": str(op["policy_rule"]),
                    "anti_patterns": list(op.get("anti_patterns") or []),
                    "entities": list(op.get("entities") or []),
                    "derived_from": list(op.get("derived_from") or []),
                    "trust": str(op.get("trust") or default_trust),
                    "observed_at": str(op.get("observed_at") or now_iso),
                    "last_confirmed": str(op.get("last_confirmed") or ref_today),
                    "review_after": str(op["review_after"]) if op.get("review_after") else None,
                    "supersedes": None,
                    "pinned": bool(op.get("pinned", False)),
                }
                writes[slot_rel] = format_markdown(gd_fm, str(op.get("body") or f"# {op['title']}"))
            elif kind == "supersede_guidance":
                if cur_text is None:
                    raise ValueError(f"cannot supersede missing guidance {slot_rel}")
                old_fm, old_body = split_frontmatter_text(cur_text, source=slot_rel)
                hist_rel = _next_history_slot(root, writes, f"knowledge/guidance/{slug}", ref_today)
                writes[hist_rel] = format_markdown(dict(old_fm, status="superseded", pinned=False), old_body)
                gd_fm = {
                    "type": "guidance",
                    "id": str(op.get("id") or _distinct_id(f"guid-{slug}", str(old_fm["id"]), ref_today)),
                    "slug": slug,
                    "title": str(op.get("title") or old_fm["title"]),
                    "status": "active",
                    "domain": str(op.get("domain") or old_fm["domain"]),
                    "scope": str(op.get("scope") or old_fm["scope"]),
                    "priority": str(op.get("priority") or old_fm["priority"]),
                    "policy_rule": str(op.get("policy_rule") or old_fm["policy_rule"]),
                    "anti_patterns": list((op.get("anti_patterns") if "anti_patterns" in op else old_fm.get("anti_patterns")) or []),
                    "entities": list((op.get("entities") if "entities" in op else old_fm.get("entities")) or []),
                    "derived_from": list((op.get("derived_from") if "derived_from" in op else old_fm.get("derived_from")) or []),
                    "trust": str(op.get("trust") or default_trust),
                    "observed_at": str(op.get("observed_at") or now_iso),
                    "last_confirmed": str(op.get("last_confirmed") or ref_today),
                    "review_after": str(op["review_after"]) if op.get("review_after") else None,
                    "supersedes": hist_rel,
                    "pinned": bool(op.get("pinned", old_fm.get("pinned", False))),
                }
                writes[slot_rel] = format_markdown(gd_fm, str(op.get("body") or old_body))
            elif kind == "retract_guidance":
                if cur_text is None:
                    raise ValueError(f"cannot retract missing guidance {slot_rel}")
                reason = str(op.get("reason") or op.get("retraction_reason") or "").strip()
                if not reason:
                    raise ValueError("retract_guidance requires reason")
                old_fm, old_body = split_frontmatter_text(cur_text, source=slot_rel)
                writes[slot_rel] = format_markdown(
                    dict(old_fm, status="retracted", pinned=False, retracted_at=now_iso, retraction_reason=reason),
                    old_body,
                )

        elif kind in {"create_decision", "supersede_decision"}:
            dec_id = str(op.get("decision_id") or op.get("id") or "")
            if not DECISION_ID_RE.fullmatch(dec_id):
                raise ValueError(f"decision op requires decision_id matching DEC-NNN..., got {dec_id!r}")
            slot_rel = f"knowledge/decisions/{dec_id}.md"
            cur_text = _read_effective_text(root, writes, slot_rel)
            if kind == "create_decision":
                if cur_text is not None:
                    raise ValueError(f"decision already exists at {slot_rel}; use supersede_decision")
                dec_fm: dict[str, Any] = {
                    "type": "decision",
                    "id": dec_id,
                    "title": str(op["title"]),
                    "status": "accepted",
                    "decided_at": str(op.get("decided_at") or ref_today),
                    "decided_by": actor_id,
                    "domain": str(op["domain"]),
                    "summary": str(op["summary"]),
                    "entities": list(op.get("entities") or []),
                    "derived_from": list(op.get("derived_from") or []),
                    "consequences": list(op.get("consequences") or []),
                    "supersedes": None,
                    "pinned": bool(op.get("pinned", False)),
                }
                writes[slot_rel] = format_markdown(dec_fm, str(op.get("body") or f"# {op['title']}"))
            elif kind == "supersede_decision":
                if cur_text is None:
                    raise ValueError(f"cannot supersede missing decision {slot_rel}")
                old_fm, old_body = split_frontmatter_text(cur_text, source=slot_rel)
                hist_rel = _next_history_slot(root, writes, f"knowledge/decisions/{dec_id}", ref_today)
                archived_id = f"{old_fm['id']}-hist-{ref_today.replace('-', '')}"
                writes[hist_rel] = format_markdown(dict(old_fm, id=archived_id, status="superseded", pinned=False), old_body)
                dec_fm = {
                    "type": "decision",
                    "id": dec_id,
                    "title": str(op.get("title") or old_fm["title"]),
                    "status": "accepted",
                    "decided_at": str(op.get("decided_at") or ref_today),
                    "decided_by": actor_id,
                    "domain": str(op.get("domain") or old_fm["domain"]),
                    "summary": str(op.get("summary") or old_fm["summary"]),
                    "entities": list((op.get("entities") if "entities" in op else old_fm.get("entities")) or []),
                    "derived_from": list((op.get("derived_from") if "derived_from" in op else old_fm.get("derived_from")) or []),
                    "consequences": list((op.get("consequences") if "consequences" in op else old_fm.get("consequences")) or []),
                    "supersedes": hist_rel,
                    "pinned": bool(op.get("pinned", old_fm.get("pinned", False))),
                }
                writes[slot_rel] = format_markdown(dec_fm, str(op.get("body") or old_body))

    return writes


def validate_candidate_writes(root: Path, writes: dict[str, str | None]) -> None:
    """Validate candidate writes in an isolated shadow copy before mutating the vault."""
    with tempfile.TemporaryDirectory() as tmp:
        shadow = Path(tmp) / "shadow"
        shutil.copytree(
            root,
            shadow,
            ignore=shutil.ignore_patterns("_staging", "_generated", ".git", "__pycache__", "*.pyc"),
        )
        for rel, content in writes.items():
            target = safe_path(shadow, rel)
            if content is None:
                if target.exists():
                    target.unlink()
            else:
                atomic_write_text(target, content)
        findings = lint_vault(shadow, strict=False, check_stale=False, check_generated=False)
        errors = [f for f in findings if f.severity == "ERROR"]
        if errors:
            detail = "; ".join(f"{e.path}: {e.message}" for e in errors[:5])
            raise ValueError(f"candidate vault failed schema/semantic validation ({len(errors)} error(s)): {detail}")


def execute_atomic_publication(
    root: Path,
    *,
    mode: str,
    idempotency_key: str,
    actor_id: str,
    ops: list[dict[str, Any]],
    writes: dict[str, str | None],
    staging_txn_id: str | None = None,
    expected_revision: str | None = None,
    proposer_id: str | None = None,
    proposal_id: str | None = None,
    review_ids: list[str] | None = None,
    resolved_signals: list[str] | None = None,
    rebuild: bool = False,
) -> dict[str, Any]:
    head = git_head(root)
    if expected_revision and head != expected_revision:
        raise ValueError(f"expected_revision mismatch: Git HEAD is {head!r}, expected {expected_revision!r}")

    validate_candidate_writes(root, writes)

    now = utc_now()
    stamp = now.strftime("%Y%m%dt%H%M%Sz")
    suffix = hashlib.sha256(f"{idempotency_key}:{iso_utc(now)}".encode("utf-8")).hexdigest()[:8]
    rcpt_id = f"rcpt-{slugify(idempotency_key, 20)}-{stamp}-{suffix}"

    sdir = _staging_dir(root, staging_txn_id or f"txn-pub-{stamp}-{suffix}")
    preimages_dir = sdir / "preimages"
    preimages_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(sdir / ".pending", "applying\n")

    touched: list[dict[str, Any]] = []
    preimage_manifest: dict[str, str | None] = {}
    for rel, content in sorted(writes.items()):
        target = safe_path(root, rel)
        existed = target.is_file()
        before_text = target.read_text(encoding="utf-8") if existed else None
        preimage_manifest[rel] = before_text
        before_hash = text_sha256(before_text) if before_text is not None else None
        after_hash = text_sha256(content) if content is not None else None
        action = "deleted" if content is None else ("updated" if existed else "created")
        touched.append({
            "path": rel,
            "action": action,
            "before_hash": before_hash,
            "after_hash": after_hash,
        })
    atomic_write_text(preimages_dir / "manifest.json", json.dumps(preimage_manifest, ensure_ascii=False))

    try:
        for rel, content in sorted(writes.items()):
            target = safe_path(root, rel)
            if content is None:
                if target.exists():
                    target.unlink()
            else:
                atomic_write_text(target, content)
    except Exception as exc:
        # Automatic rollback from preimages
        for rel, before_text in preimage_manifest.items():
            target = safe_path(root, rel)
            if before_text is None:
                if target.exists():
                    target.unlink()
            else:
                atomic_write_text(target, before_text)
        shutil.rmtree(sdir, ignore_errors=True)
        raise RuntimeError(f"publication failed and was rolled back cleanly: {exc}") from exc

    receipt_fm: dict[str, Any] = {
        "type": "receipt",
        "id": rcpt_id,
        "mode": mode,
        "status": "committed",
        "idempotency_key": idempotency_key,
        "actor_id": actor_id,
        "proposer_id": proposer_id,
        "proposal_id": proposal_id,
        "review_ids": list(review_ids or []),
        "resolved_signals": list(resolved_signals or []),
        "created_at": iso_utc(now),
        "committed_at": iso_utc(now),
        "expected_revision": expected_revision,
        "parent_revision": head,
        "ops": ops,
        "touched_files": touched,
        "failure_reason": None,
    }
    body_lines = [
        f"# Receipt: {rcpt_id}",
        "",
        f"- **Mode:** `{mode}`",
        f"- **Actor:** `{actor_id}`",
        f"- **Touched files:** {len(touched)}",
    ]
    if proposal_id:
        body_lines.append(f"- **Proposal:** `{proposal_id}`")
    if resolved_signals:
        body_lines.append(f"- **Resolved signals:** {', '.join(f'`{s}`' for s in resolved_signals)}")
    write_markdown(root / "factory/receipts" / f"{rcpt_id}.md", receipt_fm, "\n".join(body_lines))

    shutil.rmtree(sdir, ignore_errors=True)
    if rebuild:
        rebuild_all(root)

    return {
        "receipt_id": rcpt_id,
        "status": "committed",
        "mode": mode,
        "touched_files": touched,
        "rebuilt": rebuild,
    }


def commit_transaction(root: Path, txn_id: str, *, yes: bool, rebuild: bool = False) -> dict[str, Any]:
    if not yes:
        raise ValueError("commit requires --yes confirmation")
    sdir = _staging_dir(root, txn_id)
    meta_path = sdir / "_meta.yaml"
    if not meta_path.is_file():
        raise ValueError(f"staged transaction not found: {txn_id}")
    meta = load_yaml_file(meta_path)
    actor_id = str(meta["actor_id"])
    enforce_direct_transact_allowed(root, actor_id)
    ops = list(meta.get("ops") or [])
    if not ops:
        raise ValueError(f"transaction {txn_id} has no operations")
    writes = compile_operations(root, ops, actor_id=actor_id, reviewed=False)
    res = execute_atomic_publication(
        root,
        mode="direct_transaction",
        idempotency_key=str(meta["idempotency_key"]),
        actor_id=actor_id,
        ops=ops,
        writes=writes,
        staging_txn_id=txn_id,
        expected_revision=meta.get("expected_revision"),
        rebuild=rebuild,
    )
    return {"transaction_id": txn_id, **res}


def rollback_transaction(root: Path, txn_id: str) -> dict[str, Any]:
    sdir = _staging_dir(root, txn_id)
    if not sdir.exists():
        raise ValueError(f"staged transaction not found: {txn_id}")
    preimage_file = sdir / "preimages/manifest.json"
    if preimage_file.is_file():
        manifest = json.loads(preimage_file.read_text(encoding="utf-8"))
        for rel, before_text in manifest.items():
            target = safe_path(root, rel)
            if before_text is None:
                if target.exists():
                    target.unlink()
            else:
                atomic_write_text(target, before_text)
    shutil.rmtree(sdir)
    return {"transaction_id": txn_id, "status": "rolled_back"}


def recover_transactions(root: Path, *, yes: bool) -> dict[str, Any]:
    if not yes:
        raise ValueError("recover requires --yes confirmation")
    staging_root = root / "factory/_staging"
    recovered: list[str] = []
    if staging_root.exists():
        for child in sorted(staging_root.iterdir()):
            if child.is_dir() and child.name.startswith("txn-"):
                rollback_transaction(root, child.name)
                recovered.append(child.name)
    return {"recovered": recovered}


def list_transactions(root: Path) -> dict[str, Any]:
    staged = []
    staging_root = root / "factory/_staging"
    if staging_root.exists():
        for meta_path in sorted(staging_root.glob("*/_meta.yaml")):
            staged.append(load_yaml_file(meta_path))
    receipts = [fm for _, fm, _ in scan_records(root, "factory/receipts", "receipt")]
    return {"staged": staged, "receipts": receipts}


def load_ops_from_cli(args: argparse.Namespace) -> list[dict[str, Any]]:
    if getattr(args, "ops_file", None):
        raw = Path(args.ops_file).read_text(encoding="utf-8")
        parsed = json.loads(raw) if args.ops_file.endswith(".json") else load_yaml(raw)
        if not isinstance(parsed, list):
            raise ValueError("--ops-file must contain a YAML or JSON list of operation objects")
        return parsed
    if not getattr(args, "op", None):
        raise ValueError("provide --ops-file or --op")
    op: dict[str, Any] = {"op": args.op}
    scalar_keys = (
        "entity_id", "kind", "display", "entity", "predicate", "value", "valid_from",
        "valid_until", "observed_at", "assertion", "trust", "last_confirmed",
        "review_after", "reason", "event_id", "occurred_at", "summary", "slug",
        "title", "domain", "scope", "priority", "policy_rule", "decision_id",
        "decided_at", "body",
    )
    for k in scalar_keys:
        val = getattr(args, k, None)
        if val is not None:
            op[k] = val
    if getattr(args, "op_title", None) is not None:
        op["title"] = args.op_title
    if getattr(args, "confidence", None) is not None:
        op["confidence"] = float(args.confidence)
    if getattr(args, "pinned", None) is not None:
        op["pinned"] = bool(args.pinned)
    for list_key in ("aliases", "entities", "sources", "derived_from", "triggers", "verification", "anti_patterns", "consequences"):
        val = getattr(args, list_key, None)
        if val is not None:
            op[list_key] = list(val)
    return [op]


def register_op_flags(parser: argparse.ArgumentParser, *, exclude: tuple[str, ...] = ()) -> None:
    parser.add_argument("--ops-file", help="Path to YAML/JSON list of operations")
    parser.add_argument("--op", choices=SUPPORTED_OPS, help="Single operation type")
    for flag in (
        "--entity-id", "--kind", "--display", "--entity", "--predicate", "--value",
        "--valid-from", "--valid-until", "--observed-at", "--assertion", "--trust",
        "--last-confirmed", "--review-after", "--reason", "--event-id", "--occurred-at",
        "--summary", "--slug", "--title", "--op-title", "--domain", "--scope", "--priority",
        "--policy-rule", "--decision-id", "--decided-at", "--body",
    ):
        if flag not in exclude:
            parser.add_argument(flag)
    parser.add_argument("--confidence", type=float)
    parser.add_argument("--pinned", action=argparse.BooleanOptionalAction, default=None)
    for lflag in (
        "--aliases", "--entities", "--sources", "--derived-from",
        "--triggers", "--verification", "--anti-patterns", "--consequences",
    ):
        parser.add_argument(lflag, nargs="+")
