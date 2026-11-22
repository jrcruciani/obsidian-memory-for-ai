"""Automated offline vault migrator: v4.0 / v4.1 -> Knowledge Factory v5.0."""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import shutil
from pathlib import Path
from typing import Any

from .capture import capture_signal
from .model import (
    DECISION_ID_RE,
    ENTITY_KINDS,
    WIKILINK_RE,
    atomic_write_text,
    file_sha256,
    iso_utc,
    load_yaml_file,
    parse_date,
    parse_datetime,
    rel_path,
    split_frontmatter,
    today,
    utc_now,
    write_markdown,
)
from .rebuild import rebuild_all
from .templates import POLICY_YAML, PREDICATES_YAML, init_vault
from .yaml_io import dump_yaml


def _parse_legacy_dt(value: Any, fallback_iso: str) -> str:
    if value is None:
        return fallback_iso
    if isinstance(value, str):
        norm = value.strip().replace(" ", "T", 1) if " " in value.strip() and "T" not in value else value.strip()
        return iso_utc(parse_datetime(norm))
    return fallback_iso


_LEGACY_ENTITY_KIND_MAP = {
    "org": "organization",
    "tool": "instrument",
    "entity": "concept",
}


def _normalize_entity_kind(value: Any) -> str:
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned in ENTITY_KINDS:
            return cleaned
        if cleaned in _LEGACY_ENTITY_KIND_MAP:
            return _LEGACY_ENTITY_KIND_MAP[cleaned]
    return "concept"


def _rewrite_legacy_path(path_str: str, custom_map: dict[str, str] | None = None) -> str:
    if custom_map and path_str in custom_map:
        return custom_map[path_str]
    if path_str in {"memory/entities.md", "memory/entities"}:
        return "knowledge/entities.md" if path_str.endswith(".md") else "knowledge/entities"
    if path_str.startswith("memory/entities/"):
        return "knowledge/entities.md" if path_str.endswith(".md") else "knowledge/entities"
    rewrites = (
        ("memory/facts/", "knowledge/facts/"),
        ("memory/events/", "knowledge/events/"),
        ("memory/decisions/", "knowledge/decisions/"),
        ("memory/people/", "knowledge/notes/people/"),
        ("memory/projects/", "knowledge/notes/projects/"),
        ("memory/context/", "knowledge/notes/context/"),
        ("memory/insights/", "knowledge/notes/insights/"),
    )
    for old_p, new_p in rewrites:
        if path_str.startswith(old_p):
            return new_p + path_str[len(old_p):]
    return path_str


def _rewrite_body_wikilinks(body: str, custom_map: dict[str, str] | None = None) -> str:
    def _sub(match: re.Match[str]) -> str:
        full = match.group(0)
        target = match.group(1).strip()
        new_target = _rewrite_legacy_path(target, custom_map)
        if new_target == target:
            return full
        return full.replace(target, new_target, 1)

    return WIKILINK_RE.sub(_sub, body)


def migrate_v4_to_v5(
    source: Path,
    target: Path,
    *,
    yes: bool = False,
) -> dict[str, Any]:
    if not yes:
        raise ValueError("migrate requires --yes confirmation")
    source = source.resolve()
    target = target.resolve()
    if not (source / "memory").is_dir():
        raise ValueError(f"source {source} does not look like a v4.x vault (missing memory/ directory)")
    if target.exists() and any(target.iterdir()):
        raise ValueError(f"target directory {target} already exists and is non-empty")

    v4_ver = load_yaml_file(source / "memory/schema/version.yaml").get("spec_version", "4.x")

    # 1. Initialize clean v5.0 scaffold
    init_vault(target, force=True)

    now = utc_now()
    now_iso = iso_utc(now)
    ref_today = today().isoformat()

    counts = {
        "entities": 0,
        "facts": 0,
        "events": 0,
        "decisions": 0,
        "notes": 0,
        "sources": 0,
        "archived_v4_records": 0,
    }
    uncalibrated_confidence_facts: list[str] = []
    migrated_insight_notes: list[str] = []

    # 2. Copy raw `sources/` byte-for-byte
    if (source / "sources").is_dir():
        for src_file in sorted((source / "sources").rglob("*")):
            if src_file.is_file():
                rel = src_file.relative_to(source / "sources")
                dst_file = target / "sources" / rel
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                counts["sources"] += 1

    # 3. Archive v4 governance logs (_transactions, _proposals, _reviews) into sources/v4-audit-archive/
    archive_root = target / "sources/v4-audit-archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    for audit_dir in ("_transactions", "_proposals", "_reviews"):
        v4_audit = source / "memory" / audit_dir
        if v4_audit.is_dir():
            for f in sorted(v4_audit.rglob("*.md")):
                dst_f = archive_root / audit_dir.lstrip("_") / f.relative_to(v4_audit)
                dst_f.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst_f)
                counts["archived_v4_records"] += 1

    # 4. Merge predicates.yaml
    merged_preds: dict[str, dict[str, Any]] = {p["id"]: dict(p) for p in PREDICATES_YAML["predicates"]}
    v4_preds = load_yaml_file(source / "memory/schema/predicates.yaml").get("predicates", [])
    for item in v4_preds if isinstance(v4_preds, list) else []:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            merged_preds[item["id"]] = {"id": item["id"], "description": str(item.get("description", ""))}
        elif isinstance(item, str):
            merged_preds.setdefault(item, {"id": item, "description": "Migrated predicate"})
    atomic_write_text(
        target / "factory/schema/predicates.yaml",
        dump_yaml({"predicates": [merged_preds[k] for k in sorted(merged_preds)]}),
    )

    # 5. Merge roles.yaml -> policy.yaml
    policy = {
        "roles": dict(POLICY_YAML["roles"]),
        "namespaces": list(POLICY_YAML["namespaces"]),
        "agents": [dict(a) for a in POLICY_YAML["agents"]],
    }
    known_agent_ids = {a["id"] for a in policy["agents"]}
    v4_roles = load_yaml_file(source / "memory/schema/roles.yaml")
    role_map = {"admin": "owner", "reviewer": "reviewer", "proposer": "curator"}
    for ag in v4_roles.get("agents", []) if isinstance(v4_roles.get("agents"), list) else []:
        if isinstance(ag, dict) and isinstance(ag.get("id"), str) and ag["id"] not in known_agent_ids:
            mapped_roles = sorted({role_map.get(str(r), "executor") for r in (ag.get("roles") or [])}) or ["curator"]
            policy["agents"].append({
                "id": ag["id"],
                "display_name": str(ag.get("display_name", ag["id"])),
                "roles": mapped_roles,
            })
            known_agent_ids.add(ag["id"])
    atomic_write_text(target / "factory/schema/policy.yaml", dump_yaml(policy))

    # 6. Migrate entities (`memory/entities.md` + `memory/entities/*.md`)
    entities_by_id: dict[str, dict[str, Any]] = {}
    if (source / "memory/entities.md").is_file():
        efm, _ = split_frontmatter(source / "memory/entities.md")
        for ent in efm.get("entities", []) or []:
            if isinstance(ent, dict) and isinstance(ent.get("id"), str):
                entry_obj: dict[str, Any] = {
                    "id": ent["id"],
                    "kind": _normalize_entity_kind(ent.get("kind")),
                    "display": str(ent.get("display", ent["id"])),
                    "aliases": list(ent.get("aliases") or []),
                }
                if ent.get("summary"):
                    entry_obj["summary"] = str(ent["summary"])
                entities_by_id[ent["id"]] = entry_obj
    if (source / "memory/entities").is_dir():
        for ep in sorted((source / "memory/entities").rglob("*.md")):
            efm, ebody = split_frontmatter(ep)
            eid = str(efm.get("id") or ep.stem).strip()
            if not eid:
                continue
            if eid in entities_by_id:
                extra = [a for a in (efm.get("aliases") or []) if a not in entities_by_id[eid]["aliases"]]
                entities_by_id[eid]["aliases"].extend(extra)
                if efm.get("display") and entities_by_id[eid]["display"] == eid:
                    entities_by_id[eid]["display"] = str(efm["display"])
                if efm.get("kind") and entities_by_id[eid]["kind"] == "concept":
                    entities_by_id[eid]["kind"] = _normalize_entity_kind(efm["kind"])
                if efm.get("summary") and "summary" not in entities_by_id[eid]:
                    entities_by_id[eid]["summary"] = str(efm["summary"])
            else:
                heading = next((ln.lstrip("# ").strip() for ln in ebody.splitlines() if ln.startswith("# ")), eid)
                new_ent: dict[str, Any] = {
                    "id": eid,
                    "kind": _normalize_entity_kind(efm.get("kind")),
                    "display": str(efm.get("display") or efm.get("title") or heading),
                    "aliases": list(efm.get("aliases") or []),
                }
                if efm.get("summary"):
                    new_ent["summary"] = str(efm["summary"])
                entities_by_id[eid] = new_ent
    ent_list = [entities_by_id[k] for k in sorted(entities_by_id)]
    counts["entities"] = len(ent_list)
    write_markdown(
        target / "knowledge/entities.md",
        {"type": "entity-registry", "id": "entity-registry", "entities": ent_list},
        "# Canonical Entities\n\nMigrated from v" + str(v4_ver) + " entity index.",
    )

    # Pre-compute canonical decision paths `{id}.md` (and history paths) so all references/wikilinks rewrite cleanly
    decision_plan: list[tuple[Path, str, str, dict[str, Any], str]] = []
    legacy_path_map: dict[str, str] = {}
    if (source / "memory/decisions").is_dir():
        used_dec_paths: set[str] = set()
        for dec_src in sorted((source / "memory/decisions").rglob("*.md")):
            fm, body = split_frontmatter(dec_src)
            if fm.get("type") != "decision":
                continue
            raw_id = str(fm.get("id") or dec_src.stem).strip()
            is_sub = dec_src.parent != (source / "memory/decisions")
            status_val = str(fm.get("status") or ("superseded" if is_sub else "accepted"))
            if status_val == "superseded" or is_sub:
                family = dec_src.parent.name if is_sub else raw_id
                base_stem = (
                    dec_src.stem
                    if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:-[2-9]\d*|-1\d+)?", dec_src.stem)
                    else str(fm.get("decided_at") or ref_today)
                )
                cand_rel = f"knowledge/decisions/{family}/{base_stem}.md"
                seq = 2
                while cand_rel in used_dec_paths:
                    cand_rel = f"knowledge/decisions/{family}/{base_stem}-{seq}.md"
                    seq += 1
                did = f"{family}-hist-{Path(cand_rel).stem.replace('-', '')}" if raw_id == family else raw_id
                status_val = "superseded"
            else:
                did = raw_id
                if not DECISION_ID_RE.fullmatch(did) and DECISION_ID_RE.fullmatch(dec_src.stem):
                    did = dec_src.stem
                cand_rel = f"knowledge/decisions/{did}.md"
            used_dec_paths.add(cand_rel)
            old_rel = f"memory/decisions/{dec_src.relative_to(source / 'memory/decisions').as_posix()}"
            legacy_path_map[old_rel] = cand_rel
            legacy_path_map[old_rel.removesuffix(".md")] = cand_rel.removesuffix(".md")
            if dec_src.stem != Path(cand_rel).stem:
                legacy_path_map[dec_src.stem] = Path(cand_rel).stem
            decision_plan.append((dec_src, cand_rel, did, dict(fm, status=status_val), body))

    # 7. Migrate events (`memory/events/**`)
    if (source / "memory/events").is_dir():
        for ev_src in sorted((source / "memory/events").rglob("*.md")):
            fm, body = split_frontmatter(ev_src)
            if fm.get("type") != "event":
                continue
            rel_sub = ev_src.relative_to(source / "memory/events")
            occ_iso = _parse_legacy_dt(fm.get("occurred_at"), now_iso)
            ev_fm: dict[str, Any] = {
                "type": "event",
                "id": str(fm.get("id") or ev_src.stem),
                "occurred_at": occ_iso,
                "recorded_by": str(fm.get("recorded_by") or "agent-owner-00000001"),
                "summary": str(fm.get("summary") or ev_src.stem),
                "entities": list(fm.get("entities") or []),
                "sources": [_rewrite_legacy_path(str(s), legacy_path_map) for s in (fm.get("sources") or [])],
            }
            if fm.get("asserts"):
                ev_fm["asserts"] = fm["asserts"]
            if fm.get("tags"):
                ev_fm["tags"] = list(fm["tags"])
            write_markdown(target / "knowledge/events" / rel_sub, ev_fm, _rewrite_body_wikilinks(body, legacy_path_map))
            counts["events"] += 1

    # 8. Migrate decisions (`memory/decisions/**`) -> canonical `knowledge/decisions/{id}.md`
    for dec_src, cand_rel, did, fm, body in decision_plan:
        evidence = [
            _rewrite_legacy_path(str(x), legacy_path_map)
            for x in [*(fm.get("derived_from") or []), *(fm.get("sources") or [])]
        ]
        dec_fm: dict[str, Any] = {
            "type": "decision",
            "id": did,
            "title": str(fm.get("title") or did),
            "status": str(fm["status"]),
            "decided_at": str(fm.get("decided_at") or ref_today),
            "decided_by": "agent-owner-00000001",
            "domain": str(fm.get("domain") or "general"),
            "summary": str(fm.get("summary") or fm.get("title") or did),
            "entities": list(fm.get("entities") or []),
            "derived_from": sorted(set(evidence)),
            "consequences": list(fm.get("consequences") or []),
            "supersedes": _rewrite_legacy_path(str(fm["supersedes"]), legacy_path_map) if fm.get("supersedes") else None,
            "pinned": bool(fm.get("pinned", True)) if fm["status"] == "accepted" else False,
        }
        write_markdown(target / cand_rel, dec_fm, _rewrite_body_wikilinks(body, legacy_path_map))
        counts["decisions"] += 1

    # 9. Migrate facts & temporal history (`memory/facts/**`)
    if (source / "memory/facts").is_dir():
        for fact_src in sorted((source / "memory/facts").rglob("*.md")):
            fm, body = split_frontmatter(fact_src)
            if fm.get("type") != "fact":
                continue
            rel_sub = fact_src.relative_to(source / "memory/facts")
            ent = str(fm["entity"])
            pred = str(fm["predicate"])
            is_head = rel_sub.as_posix() == f"{ent}/{pred}.md"

            # Convert inclusive legacy valid_to -> exclusive valid_until (+1 day)
            valid_until: str | None = None
            if fm.get("valid_until") is not None:
                valid_until = str(fm["valid_until"])
            elif fm.get("valid_to") is not None:
                legacy_end = parse_date(str(fm["valid_to"]))
                if legacy_end:
                    valid_until = (legacy_end + dt.timedelta(days=1)).isoformat()

            if fm.get("status") == "retracted":
                status = "retracted"
            elif not is_head or valid_until is not None:
                status = "superseded" if not is_head else "active"
            else:
                status = "active"

            obs_iso = _parse_legacy_dt(fm.get("observed_at") or fm.get("created_at") or fm.get("recorded_at"), now_iso)
            raw_conf = fm.get("confidence")
            if isinstance(raw_conf, str) and raw_conf in {"high", "medium", "low"}:
                num_conf: float | None = None
                uncalibrated_confidence_facts.append(f"knowledge/facts/{rel_sub.as_posix()} (legacy={raw_conf!r})")
            elif isinstance(raw_conf, (int, float)) and not isinstance(raw_conf, bool):
                num_conf = float(raw_conf)
            else:
                num_conf = None

            derived = [_rewrite_legacy_path(str(x), legacy_path_map) for x in [*(fm.get("derived_from") or []), *(fm.get("sources") or [])]]
            derived_clean = sorted(set(derived))
            last_conf = str(fm.get("last_confirmed") or fm.get("last_reviewed") or obs_iso[:10])
            decay_raw = fm.get("decay")
            decay = decay_raw if isinstance(decay_raw, dict) else {}
            pinned = bool(fm.get("pinned", decay.get("pin", False))) if status == "active" else False

            fact_fm: dict[str, Any] = {
                "type": "fact",
                "id": str(fm.get("id") or f"fact-{ent}-{pred}-{fact_src.stem}"),
                "entity": ent,
                "predicate": pred,
                "value": fm.get("value"),
                "status": status,
                "valid_from": str(fm["valid_from"]) if fm.get("valid_from") else None,
                "valid_until": valid_until,
                "observed_at": obs_iso,
                "confidence": num_conf,
                "assertion": str(fm.get("assertion") or "stated"),
                "trust": str(fm.get("trust") or "owner"),
                "derived_from": derived_clean,
                "supersedes": _rewrite_legacy_path(str(fm["supersedes"]), legacy_path_map) if fm.get("supersedes") else None,
                "pinned": pinned,
                "last_confirmed": last_conf,
                "review_after": str(fm["review_after"]) if fm.get("review_after") else None,
            }
            if status == "retracted":
                fact_fm["retracted_at"] = _parse_legacy_dt(fm.get("retracted_at"), now_iso)
                fact_fm["retraction_reason"] = str(fm.get("reason") or "Migrated retracted fact")

            write_markdown(target / "knowledge/facts" / rel_sub, fact_fm, _rewrite_body_wikilinks(body, legacy_path_map))
            counts["facts"] += 1

    # 10. Migrate human prose folders (`people`, `projects`, `context`, `insights`) -> `knowledge/notes/`
    note_folders = (
        ("people", "person"),
        ("projects", "project"),
        ("context", "context"),
        ("insights", "insight"),
    )
    for folder_name, note_kind in note_folders:
        src_folder = source / "memory" / folder_name
        if not src_folder.is_dir():
            continue
        for note_src in sorted(src_folder.rglob("*.md")):
            fm, body = split_frontmatter(note_src)
            heading = next((ln.lstrip("# ").strip() for ln in body.splitlines() if ln.startswith("# ")), note_src.stem)
            title = str(fm.get("title") or heading)
            ents: list[str] = []
            if isinstance(fm.get("entity"), str) and fm["entity"] in entities_by_id:
                ents.append(fm["entity"])
            for e in fm.get("entities") or []:
                if isinstance(e, str) and e in entities_by_id and e not in ents:
                    ents.append(e)
            if note_src.stem in entities_by_id and note_src.stem not in ents:
                ents.append(note_src.stem)
            dst_rel = Path("knowledge/notes") / folder_name / note_src.relative_to(src_folder)
            note_fm: dict[str, Any] = {
                "type": "note",
                "id": f"note-{note_kind}-{note_src.stem}",
                "title": title,
                "kind": note_kind,
                "entities": ents,
                "authoritative": False,
            }
            write_markdown(target / dst_rel, note_fm, _rewrite_body_wikilinks(body, legacy_path_map))
            counts["notes"] += 1
            if note_kind in {"insight", "context"}:
                migrated_insight_notes.append(dst_rel.as_posix())

    # 11. Emit curation signals for legacy qualitative confidences and unpromoted insights/context
    emitted_signals: list[str] = []
    if uncalibrated_confidence_facts:
        sig = capture_signal(
            target,
            emitted_by="agent-owner-00000001",
            kind="observation",
            severity="low",
            target_namespace="facts",
            summary=f"Calibrate {len(uncalibrated_confidence_facts)} legacy qualitative confidence label(s) migrated from v{v4_ver} (set to null rather than fabricating numbers)",
            related_paths=[item.split(" ")[0] for item in uncalibrated_confidence_facts],
            idempotency_key="migrate-legacy-confidence-labels",
            body="## Uncalibrated Legacy Facts\n\n" + "\n".join(f"- `{item}`" for item in uncalibrated_confidence_facts),
        )
        emitted_signals.append(sig["id"])

    if migrated_insight_notes:
        sig2 = capture_signal(
            target,
            emitted_by="agent-owner-00000001",
            kind="gap",
            severity="low",
            target_namespace="guidance",
            summary=f"Review {len(migrated_insight_notes)} migrated v{v4_ver} insight/context note(s) for promotion into living skills or guidance",
            related_paths=migrated_insight_notes,
            idempotency_key="migrate-promote-insights-guidance",
        )
        emitted_signals.append(sig2["id"])

    # 12. Write formal `mode: migration` receipt recording every canonical file created
    touched: list[dict[str, Any]] = []
    for plane in ("knowledge", "factory/schema", "factory/signals"):
        base = target / plane
        for p in sorted(base.rglob("*")):
            if p.is_file():
                touched.append({
                    "path": rel_path(p, target),
                    "action": "created",
                    "before_hash": None,
                    "after_hash": file_sha256(p),
                })

    stamp = now.strftime("%Y%m%dt%H%M%Sz")
    suffix = hashlib.sha256(f"migrate:{source}:{now_iso}".encode("utf-8")).hexdigest()[:8]
    rcpt_id = f"rcpt-migrate-v4-to-v5-{stamp}-{suffix}"
    rcpt_fm: dict[str, Any] = {
        "type": "receipt",
        "id": rcpt_id,
        "mode": "migration",
        "status": "committed",
        "idempotency_key": f"migrate-{v4_ver}-to-5.0",
        "actor_id": "agent-owner-00000001",
        "proposer_id": None,
        "proposal_id": None,
        "review_ids": [],
        "resolved_signals": [],
        "created_at": now_iso,
        "committed_at": now_iso,
        "expected_revision": None,
        "parent_revision": None,
        "ops": [{"op": "migrate_vault", "from_version": str(v4_ver), "to_version": "5.0"}],
        "touched_files": touched,
        "failure_reason": None,
    }
    write_markdown(
        target / "factory/receipts" / f"{rcpt_id}.md",
        rcpt_fm,
        f"# Migration Receipt: v{v4_ver} -> v5.0\n\nMigrated {counts} into Knowledge Factory v5.0 layout.",
    )

    # 13. Rebuild derived views & indexes
    rebuild_all(target)

    return {
        "from_version": str(v4_ver),
        "to_version": "5.0",
        "receipt_id": rcpt_id,
        "migrated_counts": counts,
        "emitted_signals": emitted_signals,
    }
