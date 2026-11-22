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
    AGENT_ID_RE,
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
    slugify,
    split_frontmatter,
    today,
    utc_now,
    write_markdown,
)
from .rebuild import rebuild_all
from .schema_check import HIST_STEM_RE
from .templates import POLICY_YAML, PREDICATES_YAML, init_vault
from .yaml_io import dump_yaml


def _parse_legacy_dt(value: Any, fallback_iso: str) -> str:
    if value is None:
        return fallback_iso
    if isinstance(value, dt.datetime):
        return iso_utc(value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc))
    if isinstance(value, dt.date):
        return f"{value.isoformat()}T00:00:00Z"
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return fallback_iso
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return f"{s}T00:00:00Z"
        norm = s.replace(" ", "T", 1) if " " in s and "T" not in s else s
        return iso_utc(parse_datetime(norm))
    return fallback_iso


def _normalize_legacy_date(value: Any, fallback_date: str) -> str:
    if value is None:
        return fallback_date
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, str) and len(value.strip()) >= 10:
        cand = value.strip()[:10]
        parsed = parse_date(cand)
        if parsed is not None:
            return parsed.isoformat()
    return fallback_date


_DEC_NUM_PREFIX_RE = re.compile(r"^DEC-(\d+)")
_LEGACY_DEC_NUM_RE = re.compile(r"^[Dd][Ee][Cc][-_]?(\d+)(?:[-_](.*))?$")


def _try_coerce_dec_id(token: str) -> str | None:
    if DECISION_ID_RE.fullmatch(token):
        return token
    m = _LEGACY_DEC_NUM_RE.fullmatch(token.strip())
    if not m:
        return None
    num = int(m.group(1))
    rest = (m.group(2) or "").strip("-_ ")
    suffix = f"-{slugify(rest, 24)}" if rest else ""
    cand = f"DEC-{num:03d}{suffix}"
    return cand if DECISION_ID_RE.fullmatch(cand) else None


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
    if custom_map:
        if path_str in custom_map:
            return custom_map[path_str]
        if path_str.endswith(".md") and path_str[:-3] in custom_map:
            mapped = custom_map[path_str[:-3]]
            return mapped if mapped.endswith(".md") else f"{mapped}.md"
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

    # Pre-compute canonical decision paths `{id}.md` (and history/archive paths) so all references/wikilinks rewrite cleanly
    decision_plan: list[tuple[Path, str, str, str, dict[str, Any], str]] = []
    archived_proposed_decisions: list[str] = []
    legacy_path_map: dict[str, str] = {}
    superseded_dec_paths: set[str] = set()
    if (source / "memory/decisions").is_dir():
        raw_dec_entries: list[tuple[Path, str, str, bool, str, dict[str, Any], str]] = []
        for dec_src in sorted((source / "memory/decisions").rglob("*.md")):
            fm, body = split_frontmatter(dec_src)
            if fm.get("type") != "decision":
                continue
            old_rel = f"memory/decisions/{dec_src.relative_to(source / 'memory/decisions').as_posix()}"
            raw_id = str(fm.get("id") or dec_src.stem).strip()
            is_sub = dec_src.parent != (source / "memory/decisions")
            raw_status = str(fm.get("status") or ("superseded" if is_sub else "accepted")).strip()
            if raw_status not in {"accepted", "superseded", "rejected", "proposed", "deprecated", "retracted"}:
                raise ValueError(f"unsupported legacy decision status {raw_status!r} in {old_rel}")
            if raw_status == "proposed":
                rel_under = dec_src.relative_to(source / "memory/decisions")
                dst_arch = archive_root / "decisions" / rel_under
                dst_arch.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dec_src, dst_arch)
                counts["archived_v4_records"] += 1
                arch_rel = rel_path(dst_arch, target)
                archived_proposed_decisions.append(arch_rel)
                legacy_path_map[old_rel] = arch_rel
                legacy_path_map[old_rel.removesuffix(".md")] = arch_rel.removesuffix(".md")
                legacy_path_map.setdefault(dec_src.stem, arch_rel.removesuffix(".md"))
                if raw_id:
                    legacy_path_map.setdefault(raw_id, arch_rel.removesuffix(".md"))
                continue
            raw_dec_entries.append((dec_src, old_rel, raw_id, is_sub, raw_status, fm, body))

        # Group non-proposed decisions into legacy families without colliding multiple distinct heads
        family_buckets: dict[str, list[tuple[Path, str, str, bool, str, dict[str, Any], str]]] = {}
        claimed_head_tokens: set[str] = set()
        # Sort so accepted heads claim their family token before rejected/superseded siblings
        status_order = {"accepted": 0, "deprecated": 1, "retracted": 2, "rejected": 3, "superseded": 4}
        for entry in sorted(raw_dec_entries, key=lambda e: (1 if e[3] else 0, status_order.get(e[4], 9), e[1])):
            dec_src, old_rel, raw_id, is_sub, raw_status, fm, body = entry
            base_tok = dec_src.parent.name if is_sub else raw_id
            is_head_like = (not is_sub) and (raw_status != "superseded")
            if is_head_like:
                fam_tok = base_tok if base_tok not in claimed_head_tokens else f"{base_tok}-{dec_src.stem}"
                while fam_tok in claimed_head_tokens:
                    fam_tok = f"{fam_tok}-dup"
                claimed_head_tokens.add(fam_tok)
            else:
                fam_tok = base_tok
            family_buckets.setdefault(fam_tok, []).append(entry)

        # Assign canonical unique DEC-NNN... family IDs
        used_dec_families: set[str] = set()
        used_dec_nums: set[int] = set()
        canonical_family_map: dict[str, str] = {}

        def _register_family(fam_id: str) -> None:
            used_dec_families.add(fam_id)
            m_num = _DEC_NUM_PREFIX_RE.match(fam_id)
            if m_num:
                used_dec_nums.add(int(m_num.group(1)))

        # Reserve numbers/IDs from archived proposed decisions so newly allocated IDs never steal them
        for arch_rel in archived_proposed_decisions:
            arch_fm, _ = split_frontmatter(target / arch_rel)
            for tok_cand in (str(arch_fm.get("id") or ""), Path(arch_rel).stem):
                coerced_prop = _try_coerce_dec_id(tok_cand) if tok_cand else None
                if coerced_prop:
                    _register_family(coerced_prop)

        # Pass 1: preserve already-valid DEC-NNN... IDs
        for fam_tok, bucket in family_buckets.items():
            cand_id: str | None = None
            if DECISION_ID_RE.fullmatch(fam_tok):
                cand_id = fam_tok
            elif len(bucket) == 1 and not bucket[0][3] and DECISION_ID_RE.fullmatch(bucket[0][0].stem):
                cand_id = bucket[0][0].stem
            if cand_id and cand_id not in used_dec_families:
                canonical_family_map[fam_tok] = cand_id
                _register_family(cand_id)

        # Pass 2: coerce near-DEC tokens (e.g. dec-7, DEC-42) before allocating brand-new numbers
        for fam_tok, bucket in family_buckets.items():
            if fam_tok in canonical_family_map:
                continue
            coerced = _try_coerce_dec_id(fam_tok)
            if coerced is None and len(bucket) == 1 and not bucket[0][3]:
                coerced = _try_coerce_dec_id(bucket[0][0].stem)
            if coerced and coerced not in used_dec_families:
                canonical_family_map[fam_tok] = coerced
                _register_family(coerced)

        # Pass 3: allocate sequential DEC-NNN-<slug> starting after all existing/coerced DEC numbers
        next_dec_num = max(used_dec_nums, default=0) + 1
        for fam_tok in family_buckets:
            if fam_tok in canonical_family_map:
                continue
            slug_tail = slugify(fam_tok, 24)
            while True:
                allocated = f"DEC-{next_dec_num:03d}-{slug_tail}"
                next_dec_num += 1
                if allocated not in used_dec_families:
                    canonical_family_map[fam_tok] = allocated
                    _register_family(allocated)
                    break

        used_dec_paths: set[str] = set()
        used_dec_ids: set[str] = set(used_dec_families)

        for fam_tok in sorted(family_buckets.keys(), key=lambda k: canonical_family_map[k]):
            family = canonical_family_map[fam_tok]
            bucket = family_buckets[fam_tok]
            heads = [e for e in bucket if (not e[3]) and e[4] != "superseded"]
            hists = [e for e in bucket if e[3] or e[4] == "superseded"]
            hists.sort(key=lambda e: (_normalize_legacy_date(e[5].get("decided_at"), ref_today), e[1]))

            promoted_from_superseded = False
            if not heads and hists:
                heads = [hists.pop()]
                promoted_from_superseded = True

            emitted_hist_rels: list[str] = []
            for dec_src, old_rel, raw_id, is_sub, raw_status, fm, body in hists:
                if HIST_STEM_RE.fullmatch(dec_src.stem):
                    base_stem = dec_src.stem
                else:
                    base_stem = _normalize_legacy_date(fm.get("decided_at"), ref_today)
                date_prefix = base_stem[:10]
                cand_rel = f"knowledge/decisions/{family}/{base_stem}.md"
                seq = 2
                while cand_rel in used_dec_paths:
                    cand_rel = f"knowledge/decisions/{family}/{date_prefix}-{seq}.md"
                    seq += 1
                used_dec_paths.add(cand_rel)
                superseded_dec_paths.add(cand_rel)
                emitted_hist_rels.append(cand_rel)

                hist_base_id = f"{family}-hist-{Path(cand_rel).stem.replace('-', '')}"
                did = hist_base_id
                id_seq = 2
                while did in used_dec_ids:
                    did = f"{hist_base_id}-{id_seq}"
                    id_seq += 1
                used_dec_ids.add(did)

                legacy_path_map[old_rel] = cand_rel
                legacy_path_map[old_rel.removesuffix(".md")] = cand_rel.removesuffix(".md")
                if dec_src.stem != Path(cand_rel).stem:
                    legacy_path_map.setdefault(dec_src.stem, cand_rel.removesuffix(".md"))
                if raw_id and raw_id != family:
                    legacy_path_map.setdefault(raw_id, cand_rel.removesuffix(".md"))
                decision_plan.append((dec_src, cand_rel, did, family, dict(fm, status="superseded"), body))

            for dec_src, old_rel, raw_id, is_sub, raw_status, fm, body in heads:
                cand_rel = f"knowledge/decisions/{family}.md"
                used_dec_paths.add(cand_rel)
                if promoted_from_superseded:
                    head_status = "deprecated"
                elif raw_status == "rejected":
                    head_status = "retracted"
                else:
                    head_status = raw_status
                fm_copy = dict(fm, status=head_status, _legacy_raw_status=raw_status)
                if emitted_hist_rels and not fm_copy.get("supersedes"):
                    fm_copy["supersedes"] = emitted_hist_rels[-1]
                legacy_path_map[old_rel] = cand_rel
                legacy_path_map[old_rel.removesuffix(".md")] = cand_rel.removesuffix(".md")
                if dec_src.stem != family:
                    legacy_path_map[dec_src.stem] = cand_rel.removesuffix(".md")
                if raw_id and raw_id != family:
                    legacy_path_map[raw_id] = cand_rel.removesuffix(".md")
                decision_plan.append((dec_src, cand_rel, family, family, fm_copy, body))

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
    for dec_src, cand_rel, did, family, fm, body in decision_plan:
        evidence = [
            _rewrite_legacy_path(str(x), legacy_path_map)
            for x in [*(fm.get("derived_from") or []), *(fm.get("sources") or [])]
        ]
        sup_target: str | None = None
        if fm.get("supersedes"):
            rewritten_sup = _rewrite_legacy_path(str(fm["supersedes"]), legacy_path_map)
            if (
                rewritten_sup in superseded_dec_paths
                and rewritten_sup.startswith(f"knowledge/decisions/{family}/")
                and rewritten_sup != cand_rel
            ):
                sup_target = rewritten_sup
            elif rewritten_sup != cand_rel and rewritten_sup.startswith(
                ("knowledge/decisions/", "knowledge/events/", "factory/signals/", "sources/")
            ):
                evidence.append(rewritten_sup)

        decided_date = _normalize_legacy_date(fm.get("decided_at"), ref_today)
        raw_dec_by = fm.get("decided_by")
        decided_by = str(raw_dec_by) if isinstance(raw_dec_by, str) and AGENT_ID_RE.fullmatch(raw_dec_by) else "agent-owner-00000001"
        status_str = str(fm["status"])
        dec_fm: dict[str, Any] = {
            "type": "decision",
            "id": did,
            "title": str(fm.get("title") or did),
            "status": status_str,
            "decided_at": decided_date,
            "decided_by": decided_by,
            "domain": str(fm.get("domain") or "general"),
            "summary": str(fm.get("summary") or fm.get("title") or did),
            "entities": list(fm.get("entities") or []),
            "derived_from": sorted(s for s in set(evidence) if s != cand_rel),
            "consequences": list(fm.get("consequences") or []),
            "supersedes": sup_target,
            "pinned": bool(fm.get("pinned", True)) if status_str == "accepted" else False,
        }
        if status_str == "retracted":
            dec_fm["retracted_at"] = _parse_legacy_dt(fm.get("retracted_at"), f"{decided_date}T00:00:00Z")
            default_reason = (
                "Migrated rejected v4 decision"
                if fm.get("_legacy_raw_status") == "rejected"
                else "Migrated retracted v4 decision"
            )
            dec_fm["retraction_reason"] = str(fm.get("retraction_reason") or fm.get("reason") or default_reason)
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

    if archived_proposed_decisions:
        sig3 = capture_signal(
            target,
            emitted_by="agent-owner-00000001",
            kind="gap",
            severity="medium",
            target_namespace="decisions",
            summary=f"Review {len(archived_proposed_decisions)} unaccepted v{v4_ver} proposed decision(s) archived under sources/v4-audit-archive/decisions/",
            evidence=archived_proposed_decisions,
            idempotency_key="migrate-proposed-decisions",
        )
        emitted_signals.append(sig3["id"])

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
