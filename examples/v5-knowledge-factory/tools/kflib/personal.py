"""Personal Memory Mode ("Solo Owner / Fast-Track") operations.

Provides low-friction single-command operations (`remember_fact`, `forget_fact`,
`write_note`) for personal Obsidian vaults while preserving ironclad
risk-tiered governance:
- Routine personal `facts`, `events`, and `notes` from the owner/trusted agent
  write atomically with full bitemporal supersession and audit receipts.
- High-risk mutations (`trust="external"`, `skills`, `guidance`) STILL require
  the full `propose -> review -> publish` pipeline to prevent prompt injection.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .locking import vault_write_lock
from .model import (
    ENTITY_KINDS,
    SLUG_RE,
    atomic_write_text,
    format_markdown,
    is_active_head,
    iso_utc,
    load_entities,
    load_manifest,
    slugify,
    split_frontmatter,
    today,
    utc_now,
)

NOTE_KINDS = ("person", "project", "context", "insight", "general")
from .transact import (
    compile_operations,
    enforce_direct_transact_allowed,
    execute_atomic_publication,
    validate_candidate_writes,
)


def default_personal_actor(root: Path) -> str:
    manifest = load_manifest(root)
    settings = manifest.get("settings") or {}
    actor = settings.get("default_actor")
    if isinstance(actor, str) and actor.strip():
        return actor.strip()
    return "agent-owner-00000001"


def remember_fact(
    root: Path,
    *,
    entity: str,
    predicate: str,
    value: Any,
    valid_from: str | None = None,
    valid_until: str | None = None,
    pinned: bool = False,
    trust: str = "owner",
    assertion: str = "stated",
    confidence: float | None = 1.0,
    derived_from: list[str] | None = None,
    auto_entity: bool = True,
    entity_kind: str = "concept",
    entity_display: str | None = None,
    entity_aliases: list[str] | None = None,
    body: str = "",
    actor_id: str | None = None,
    rebuild: bool = True,
) -> dict[str, Any]:
    """Remember (create, confirm, or supersede) a personal fact in one atomic command.

    Blocks ``trust="external"`` to maintain prompt-injection defense; external
    claims must enter via ``capture signal`` / ``propose -> review -> publish``.
    """
    if trust == "external":
        raise ValueError(
            "remember_fact refuses trust='external' to prevent prompt injection; "
            "use `kf.py capture signal` + `propose -> review -> publish` for external sources"
        )
    if not SLUG_RE.fullmatch(entity):
        raise ValueError(f"entity must be a valid slug, got {entity!r}")
    if not SLUG_RE.fullmatch(predicate):
        raise ValueError(f"predicate must be a valid slug, got {predicate!r}")

    actor = actor_id or default_personal_actor(root)
    enforce_direct_transact_allowed(root, actor)

    with vault_write_lock(root):
        ops: list[dict[str, Any]] = []
        entities = load_entities(root)
        entity_created = False
        if entity not in entities:
            if not auto_entity:
                raise ValueError(f"unknown entity {entity!r} (pass auto_entity=True or register in knowledge/entities.md)")
            ekind = entity_kind if entity_kind in ENTITY_KINDS else "concept"
            ops.append({
                "op": "upsert_entity",
                "entity_id": entity,
                "kind": ekind,
                "display": entity_display or entity.replace("-", " ").title(),
                "aliases": list(entity_aliases or []),
            })
            entity_created = True

        slot_path = root / f"knowledge/facts/{entity}/{predicate}.md"
        eff_valid_from = valid_from or today().isoformat()
        action = "created"

        if slot_path.is_file():
            cur_fm, _ = split_frontmatter(slot_path)
            if is_active_head(cur_fm):
                if cur_fm.get("value") == value:
                    ops.append({
                        "op": "confirm_fact",
                        "entity": entity,
                        "predicate": predicate,
                    })
                    action = "confirmed"
                else:
                    ops.append({
                        "op": "supersede_fact",
                        "entity": entity,
                        "predicate": predicate,
                        "value": value,
                        "valid_from": eff_valid_from,
                        "valid_until": valid_until,
                        "trust": trust,
                        "assertion": assertion,
                        "confidence": confidence,
                        "derived_from": list(derived_from or []),
                        "pinned": pinned,
                        "body": body,
                    })
                    action = "superseded"
            else:
                ops.append({
                    "op": "create_fact",
                    "entity": entity,
                    "predicate": predicate,
                    "value": value,
                    "valid_from": eff_valid_from,
                    "valid_until": valid_until,
                    "trust": trust,
                    "assertion": assertion,
                    "confidence": confidence,
                    "derived_from": list(derived_from or []),
                    "pinned": pinned,
                    "body": body,
                })
                action = "created"
        else:
            ops.append({
                "op": "create_fact",
                "entity": entity,
                "predicate": predicate,
                "value": value,
                "valid_from": eff_valid_from,
                "valid_until": valid_until,
                "trust": trust,
                "assertion": assertion,
                "confidence": confidence,
                "derived_from": list(derived_from or []),
                "pinned": pinned,
                "body": body,
            })

        writes = compile_operations(root, ops, actor_id=actor, reviewed=False)
        stamp = utc_now().strftime("%Y%m%dt%H%M%Sz")
        h = hashlib.sha256(f"{entity}:{predicate}:{value!r}:{eff_valid_from}:{stamp}".encode("utf-8")).hexdigest()[:10]
        ikey = f"remember-{slugify(entity, 12)}-{slugify(predicate, 12)}-{h}"

        receipt = execute_atomic_publication(
            root,
            mode="direct_transaction",
            idempotency_key=ikey,
            actor_id=actor,
            ops=ops,
            writes=writes,
            rebuild=rebuild,
        )
        return {
            "action": action,
            "entity": entity,
            "entity_created": entity_created,
            "predicate": predicate,
            "value": value,
            "path": f"knowledge/facts/{entity}/{predicate}.md",
            "receipt_id": receipt["receipt_id"],
        }


def forget_fact(
    root: Path,
    *,
    entity: str,
    predicate: str,
    reason: str,
    actor_id: str | None = None,
    rebuild: bool = True,
) -> dict[str, Any]:
    """Non-destructively retract a personal fact in one command."""
    clean_reason = reason.strip()
    if not clean_reason:
        raise ValueError("forget_fact requires a non-empty reason")
    actor = actor_id or default_personal_actor(root)
    enforce_direct_transact_allowed(root, actor)

    with vault_write_lock(root):
        ops = [{
            "op": "retract_fact",
            "entity": entity,
            "predicate": predicate,
            "reason": clean_reason,
        }]
        writes = compile_operations(root, ops, actor_id=actor, reviewed=False)
        stamp = utc_now().strftime("%Y%m%dt%H%M%Sz")
        h = hashlib.sha256(f"forget:{entity}:{predicate}:{clean_reason}:{stamp}".encode("utf-8")).hexdigest()[:10]
        receipt = execute_atomic_publication(
            root,
            mode="direct_transaction",
            idempotency_key=f"forget-{slugify(entity, 12)}-{slugify(predicate, 12)}-{h}",
            actor_id=actor,
            ops=ops,
            writes=writes,
            rebuild=rebuild,
        )
        return {
            "status": "retracted",
            "entity": entity,
            "predicate": predicate,
            "path": f"knowledge/facts/{entity}/{predicate}.md",
            "receipt_id": receipt["receipt_id"],
        }


def write_note(
    root: Path,
    *,
    slug: str,
    title: str,
    body: str,
    kind: str = "general",
    entities: list[str] | None = None,
    tags: list[str] | None = None,
    append: bool = False,
) -> dict[str, Any]:
    """Create or update a non-authoritative narrative note in `knowledge/notes/`."""
    clean_slug = slugify(slug, 64)
    if not clean_slug or not SLUG_RE.fullmatch(clean_slug):
        raise ValueError(f"invalid note slug: {slug!r}")
    if kind not in NOTE_KINDS:
        raise ValueError(f"invalid note kind {kind!r}; allowed: {list(NOTE_KINDS)}")

    rel = f"knowledge/notes/{kind}/{clean_slug}.md"
    target = root / rel
    now_iso = iso_utc(utc_now())

    with vault_write_lock(root):
        final_body = body.strip()
        merged_entities = list(entities or [])
        merged_tags = list(tags or [])
        if append and target.is_file():
            old_fm, old_body = split_frontmatter(target)
            final_body = (old_body.strip() + "\n\n" + final_body).strip()
            merged_entities = sorted(set(old_fm.get("entities") or []) | set(merged_entities))
            merged_tags = sorted(set(old_fm.get("tags") or []) | set(merged_tags))

        fm: dict[str, Any] = {
            "type": "note",
            "id": f"note-{kind}-{clean_slug}",
            "title": title.strip() or clean_slug,
            "kind": kind,
            "entities": merged_entities,
            "authoritative": False,
            "updated_at": now_iso,
        }
        if merged_tags:
            fm["tags"] = merged_tags

        rendered = format_markdown(fm, final_body)
        validate_candidate_writes(root, {rel: rendered})
        atomic_write_text(target, rendered)
        return {"path": rel, "id": fm["id"], "title": fm["title"], "kind": kind}
