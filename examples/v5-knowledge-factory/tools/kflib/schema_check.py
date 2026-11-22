"""Declarative schema checker and cross-record semantic linter for Knowledge Factory v5.0."""

from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model import (
    AGENT_ID_RE,
    DECISION_ID_RE,
    ENTITY_KINDS,
    SLUG_RE,
    TRUST_LEVELS,
    WIKILINK_RE,
    canonical_source_digest,
    fact_interval,
    fold_text,
    is_active_head,
    is_fact_visible,
    load_entities,
    load_manifest,
    load_policy,
    load_predicates,
    load_yaml_file,
    parse_date,
    parse_datetime,
    rel_path,
    safe_path,
    scan_records,
    split_frontmatter,
    today,
    validate_confidence,
)
from .templates import SCHEMAS


@dataclass(frozen=True)
class Finding:
    severity: str  # "ERROR" | "WARN"
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "path": self.path, "message": self.message}


HIST_STEM_RE = re.compile(r"\d{4}-\d{2}-\d{2}(?:-[2-9]\d*|-1\d+)?")


def _check_field_type(kind: str, value: Any) -> None:
    if kind == "any":
        return
    if kind == "str":
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"expected non-empty string, got {value!r}")
    elif kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"expected boolean, got {value!r}")
    elif kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"expected integer, got {value!r}")
    elif kind == "list":
        if not isinstance(value, list):
            raise ValueError(f"expected list, got {value!r}")
    elif kind == "date":
        parse_date(value)
    elif kind == "datetime":
        parse_datetime(value)
    elif kind == "confidence":
        validate_confidence(value)


def _load_type_schemas(root: Path) -> tuple[dict[str, dict[str, Any]], list[Finding]]:
    findings: list[Finding] = []
    loaded: dict[str, dict[str, Any]] = {}
    schema_dir = root / "factory/schema"
    for filename in sorted(SCHEMAS.keys()):
        p = schema_dir / filename
        if not p.is_file():
            findings.append(Finding("ERROR", f"factory/schema/{filename}", f"missing required schema file {filename}"))
            continue
        try:
            data = load_yaml_file(p)
            t = data.get("type")
            if not isinstance(t, str):
                findings.append(Finding("ERROR", rel_path(p, root), "schema file missing 'type' string"))
                continue
            loaded[t] = data
        except Exception as exc:
            findings.append(Finding("ERROR", rel_path(p, root), f"invalid schema YAML: {exc}"))
    return loaded, findings


def _validate_against_schema(rel: str, fm: dict[str, Any], schema: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    required = schema.get("required", [])
    fields = schema.get("fields", {})
    for req in required:
        if req not in fm or fm[req] is None:
            findings.append(Finding("ERROR", rel, f"missing required field '{req}'"))
    for key, val in fm.items():
        if key not in fields:
            findings.append(Finding("ERROR", rel, f"unknown frontmatter field '{key}' for type '{schema.get('type')}'"))
            continue
        spec = fields[key]
        if val is None:
            if not spec.get("nullable", False) and key in required:
                findings.append(Finding("ERROR", rel, f"field '{key}' cannot be null"))
            continue
        try:
            _check_field_type(spec.get("kind", "any"), val)
            if "enum" in spec and val not in spec["enum"]:
                findings.append(Finding("ERROR", rel, f"invalid {key} {val!r}; allowed: {spec['enum']}"))
        except ValueError as exc:
            findings.append(Finding("ERROR", rel, f"field '{key}': {exc}"))
    return findings


def _link_resolves(target: str, known_paths: set[str], by_stem: dict[str, list[str]]) -> tuple[bool, bool]:
    cleaned = target.strip().strip("/")
    if not cleaned:
        return True, False
    if cleaned in known_paths or f"{cleaned}.md" in known_paths:
        return True, False
    if "/" not in cleaned:
        matches = by_stem.get(cleaned, [])
        if len(matches) == 1:
            return True, False
        if len(matches) > 1:
            return True, True
    return False, False


def lint_vault(
    root: Path,
    *,
    strict: bool = False,
    check_stale: bool = False,
    check_generated: bool = False,
) -> list[Finding]:
    findings: list[Finding] = []

    manifest_path = root / "factory/schema/manifest.yaml"
    if not manifest_path.is_file():
        return [Finding("ERROR", "factory/schema/manifest.yaml", "missing factory/schema/manifest.yaml")]
    try:
        manifest = load_manifest(root)
    except Exception as exc:
        return [Finding("ERROR", "factory/schema/manifest.yaml", f"cannot parse manifest.yaml: {exc}")]

    if str(manifest.get("spec_version")) != "5.0":
        findings.append(
            Finding("ERROR", "factory/schema/manifest.yaml", f"spec_version must be '5.0', got {manifest.get('spec_version')!r}")
        )
    if manifest.get("protocol") != "knowledge-factory":
        findings.append(
            Finding("ERROR", "factory/schema/manifest.yaml", f"protocol must be 'knowledge-factory', got {manifest.get('protocol')!r}")
        )

    type_schemas, schema_findings = _load_type_schemas(root)
    findings.extend(schema_findings)

    # Validate entities & alias uniqueness
    entities: dict[str, dict[str, Any]] = {}
    ent_path = root / "knowledge/entities.md"
    if not ent_path.is_file():
        findings.append(Finding("ERROR", "knowledge/entities.md", "missing canonical entity registry knowledge/entities.md"))
    else:
        try:
            ent_fm, _ = split_frontmatter(ent_path)
            if "entity-registry" in type_schemas:
                findings.extend(_validate_against_schema("knowledge/entities.md", ent_fm, type_schemas["entity-registry"]))
            owners: dict[str, str] = {}
            for item in ent_fm.get("entities", []) if isinstance(ent_fm.get("entities"), list) else []:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not SLUG_RE.fullmatch(item["id"]):
                    findings.append(Finding("ERROR", "knowledge/entities.md", f"invalid entity declaration: {item!r}"))
                    continue
                eid = item["id"]
                if eid in entities:
                    findings.append(Finding("ERROR", "knowledge/entities.md", f"duplicate entity id '{eid}'"))
                entities[eid] = item
                ekind = item.get("kind")
                if not isinstance(ekind, str) or ekind not in ENTITY_KINDS:
                    findings.append(
                        Finding(
                            "ERROR",
                            "knowledge/entities.md",
                            f"invalid entity kind {ekind!r} on '{eid}'; allowed: {list(ENTITY_KINDS)}",
                        )
                    )
                edisplay = item.get("display")
                if not isinstance(edisplay, str) or not edisplay.strip():
                    findings.append(Finding("ERROR", "knowledge/entities.md", f"entity '{eid}' requires non-empty display name"))
                aliases = item.get("aliases", [])
                if not isinstance(aliases, list):
                    findings.append(Finding("ERROR", "knowledge/entities.md", f"aliases for '{eid}' must be a list"))
                    continue
                for token in [eid, *( [edisplay] if isinstance(edisplay, str) and edisplay.strip() else [] ), *aliases]:
                    if not isinstance(token, str) or not token.strip():
                        findings.append(Finding("ERROR", "knowledge/entities.md", f"empty alias on entity '{eid}'"))
                        continue
                    folded = fold_text(token)
                    if folded in owners and owners[folded] != eid:
                        findings.append(
                            Finding(
                                "ERROR",
                                "knowledge/entities.md",
                                f"alias collision: {token!r} folds to {folded!r} for both '{owners[folded]}' and '{eid}'",
                            )
                        )
                    owners[folded] = eid
        except Exception as exc:
            findings.append(Finding("ERROR", "knowledge/entities.md", str(exc)))

    predicates = load_predicates(root)
    if not predicates:
        findings.append(Finding("ERROR", "factory/schema/predicates.yaml", "predicates.yaml must declare at least one predicate"))

    policy = load_policy(root)
    roles_cfg = policy.get("roles", {})
    namespaces_cfg = {ns["id"]: ns for ns in policy.get("namespaces", []) if isinstance(ns, dict) and "id" in ns}
    agents_cfg = {ag["id"]: ag for ag in policy.get("agents", []) if isinstance(ag, dict) and "id" in ag}

    # Collect all canonical + factory Markdown files
    md_records: list[tuple[Path, str, dict[str, Any], str]] = []
    for plane in ("knowledge", "factory/signals", "factory/proposals", "factory/reviews", "factory/receipts"):
        base = root / plane
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.md")):
            r = rel_path(p, root)
            try:
                fm, body = split_frontmatter(p)
            except Exception as exc:
                findings.append(Finding("ERROR", r, str(exc)))
                continue
            if not fm:
                findings.append(Finding("ERROR", r, "missing YAML frontmatter"))
                continue
            md_records.append((p, r, fm, body))

    # Global unique ID check & schema validation
    seen_ids: dict[str, str] = {}
    known_link_targets: set[str] = set()
    by_stem: dict[str, list[str]] = defaultdict(list)

    for p in sorted((root / "sources").rglob("*.md")) if (root / "sources").exists() else []:
        r = rel_path(p, root)
        known_link_targets.update((r, r.removesuffix(".md")))
        by_stem[p.stem].append(r)

    facts_by_slot: dict[tuple[str, str], list[tuple[Path, str, dict[str, Any]]]] = defaultdict(list)
    skills_by_slug: dict[str, list[tuple[Path, str, dict[str, Any]]]] = defaultdict(list)
    guidance_by_slug: dict[str, list[tuple[Path, str, dict[str, Any]]]] = defaultdict(list)
    decisions_by_id: dict[str, list[tuple[Path, str, dict[str, Any]]]] = defaultdict(list)
    proposals_by_id: dict[str, tuple[str, dict[str, Any]]] = {}
    reviews_list: list[tuple[str, dict[str, Any]]] = []

    for p, r, fm, body in md_records:
        known_link_targets.update((r, r.removesuffix(".md")))
        by_stem[p.stem].append(r)

        rtype = fm.get("type")
        if not isinstance(rtype, str) or rtype not in type_schemas:
            findings.append(Finding("ERROR", r, f"unknown or missing record type {rtype!r}"))
            continue
        findings.extend(_validate_against_schema(r, fm, type_schemas[rtype]))

        rec_id = fm.get("id")
        if isinstance(rec_id, str):
            # Superseded decisions keep decision family slug only if distinct history id; enforce globally unique IDs!
            if rec_id in seen_ids:
                findings.append(Finding("ERROR", r, f"duplicate id '{rec_id}' (already used in {seen_ids[rec_id]})"))
            else:
                seen_ids[rec_id] = r

        # Type-specific semantic invariants
        if rtype == "fact":
            ent = fm.get("entity")
            pred = fm.get("predicate")
            valid_ent = isinstance(ent, str) and bool(SLUG_RE.fullmatch(ent))
            valid_pred = isinstance(pred, str) and bool(SLUG_RE.fullmatch(pred))
            if not valid_ent:
                findings.append(Finding("ERROR", r, f"fact entity {ent!r} must match {SLUG_RE.pattern}"))
            elif ent not in entities:
                findings.append(Finding("ERROR", r, f"unknown entity '{ent}' (declare in knowledge/entities.md)"))
            if not valid_pred:
                findings.append(Finding("ERROR", r, f"fact predicate {pred!r} must match {SLUG_RE.pattern}"))
            elif pred not in predicates:
                findings.append(Finding("ERROR", r, f"unknown predicate '{pred}' (declare in factory/schema/predicates.yaml)"))
            if valid_ent and valid_pred:
                assert isinstance(ent, str) and isinstance(pred, str)
                facts_by_slot[(ent, pred)].append((p, r, fm))
                expected_head = f"knowledge/facts/{ent}/{pred}.md"
                is_hist = p.parent == (root / f"knowledge/facts/{ent}/{pred}") and bool(HIST_STEM_RE.fullmatch(p.stem))
                if is_active_head(fm):
                    if r != expected_head:
                        findings.append(Finding("ERROR", r, f"active fact must reside at {expected_head}"))
                elif fm.get("status") == "superseded":
                    if not is_hist:
                        findings.append(
                            Finding("ERROR", r, f"superseded fact must reside at knowledge/facts/{ent}/{pred}/YYYY-MM-DD[-N].md")
                        )
                else:
                    if r != expected_head:
                        findings.append(
                            Finding("ERROR", r, f"{fm.get('status') or 'non-active'} fact must reside at {expected_head}")
                        )
            elif not r.startswith("knowledge/facts/"):
                findings.append(Finding("ERROR", r, "fact must reside under knowledge/facts/<entity>/<predicate>.md"))
            try:
                start, end = fact_interval(fm)
                if fm.get("status") == "superseded":
                    if start > end:
                        findings.append(
                            Finding("ERROR", r, f"valid_from ({fm.get('valid_from')}) must not be after valid_until ({fm.get('valid_until')})")
                        )
                elif start >= end:
                    findings.append(Finding("ERROR", r, f"valid_from ({fm.get('valid_from')}) must be strictly before valid_until ({fm.get('valid_until')})"))
            except ValueError:
                pass
            if fm.get("status") == "retracted" and (not fm.get("retracted_at") or not fm.get("retraction_reason")):
                findings.append(Finding("ERROR", r, "retracted fact requires retracted_at and retraction_reason"))
            if fm.get("assertion") == "inferred" and not fm.get("derived_from"):
                findings.append(Finding("WARN", r, "inferred fact should cite derived_from evidence"))
            if fm.get("trust") == "external" and fm.get("confidence") is None:
                findings.append(Finding("WARN", r, "external fact should specify numeric confidence"))
            _check_evidence_paths(root, r, fm.get("derived_from", []), findings, ("knowledge/events/", "knowledge/decisions/", "factory/signals/", "sources/"))
            _check_supersedes_chain(root, p, r, fm, "knowledge/facts/", findings, match_keys=("entity", "predicate"))

        elif rtype == "event":
            for ent in fm.get("entities", []) or []:
                if ent not in entities:
                    findings.append(Finding("ERROR", r, f"event references unknown entity '{ent}'"))
            _check_evidence_paths(root, r, fm.get("sources", []), findings, ("sources/",))
            for claim in fm.get("asserts", []) or []:
                if not isinstance(claim, dict) or not {"entity", "predicate", "value"} <= claim.keys():
                    findings.append(Finding("ERROR", r, "event asserts items must contain entity, predicate, value"))
                else:
                    if claim["entity"] not in entities:
                        findings.append(Finding("ERROR", r, f"event asserts unknown entity '{claim['entity']}'"))
                    if claim["predicate"] not in predicates:
                        findings.append(Finding("ERROR", r, f"event asserts unknown predicate '{claim['predicate']}'"))

        elif rtype == "skill":
            slug = fm.get("slug")
            if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
                findings.append(Finding("ERROR", r, f"skill slug {slug!r} must match {SLUG_RE.pattern}"))
            else:
                skills_by_slug[slug].append((p, r, fm))
                expected_head = f"knowledge/skills/{slug}.md"
                is_hist = p.parent == (root / f"knowledge/skills/{slug}") and bool(HIST_STEM_RE.fullmatch(p.stem))
                if is_active_head(fm):
                    if r != expected_head:
                        findings.append(Finding("ERROR", r, f"active skill must reside at {expected_head}"))
                elif fm.get("status") == "superseded":
                    if not is_hist:
                        findings.append(Finding("ERROR", r, f"superseded skill must reside at knowledge/skills/{slug}/YYYY-MM-DD[-N].md"))
                elif r != expected_head:
                    findings.append(Finding("ERROR", r, f"{fm.get('status') or 'non-active'} skill '{slug}' must reside at {expected_head}"))
            ver = fm.get("version")
            if isinstance(ver, int) and not isinstance(ver, bool) and ver < 1:
                findings.append(Finding("ERROR", r, f"skill version must be >= 1, got {ver}"))
            triggers = fm.get("triggers")
            if not isinstance(triggers, list) or not triggers or not all(isinstance(t, str) and t.strip() for t in triggers):
                findings.append(Finding("ERROR", r, "skill must define at least one non-empty string trigger"))
            verif = fm.get("verification")
            if not isinstance(verif, list) or not verif or not all(isinstance(v, str) and v.strip() for v in verif):
                findings.append(Finding("ERROR", r, "skill must define at least one non-empty verification step"))
            if fm.get("status") == "retracted" and (not fm.get("retracted_at") or not fm.get("retraction_reason")):
                findings.append(Finding("ERROR", r, "retracted skill requires retracted_at and retraction_reason"))
            if fm.get("trust") == "external" and fm.get("confidence") is None:
                findings.append(Finding("WARN", r, "external skill should specify numeric confidence"))
            for ent in fm.get("entities", []) or []:
                if ent not in entities:
                    findings.append(Finding("ERROR", r, f"skill references unknown entity '{ent}'"))
            _check_evidence_paths(root, r, fm.get("derived_from", []), findings, ("knowledge/events/", "knowledge/decisions/", "factory/signals/", "sources/"))
            _check_supersedes_chain(root, p, r, fm, "knowledge/skills/", findings, match_keys=("slug",))

        elif rtype == "guidance":
            slug = fm.get("slug")
            if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
                findings.append(Finding("ERROR", r, f"guidance slug {slug!r} must match {SLUG_RE.pattern}"))
            else:
                guidance_by_slug[slug].append((p, r, fm))
                expected_head = f"knowledge/guidance/{slug}.md"
                is_hist = p.parent == (root / f"knowledge/guidance/{slug}") and bool(HIST_STEM_RE.fullmatch(p.stem))
                if is_active_head(fm):
                    if r != expected_head:
                        findings.append(Finding("ERROR", r, f"active guidance must reside at {expected_head}"))
                elif fm.get("status") == "superseded":
                    if not is_hist:
                        findings.append(Finding("ERROR", r, f"superseded guidance must reside at knowledge/guidance/{slug}/YYYY-MM-DD[-N].md"))
                elif r != expected_head:
                    findings.append(Finding("ERROR", r, f"{fm.get('status') or 'non-active'} guidance '{slug}' must reside at {expected_head}"))
            if fm.get("status") == "retracted" and (not fm.get("retracted_at") or not fm.get("retraction_reason")):
                findings.append(Finding("ERROR", r, "retracted guidance requires retracted_at and retraction_reason"))
            for ent in fm.get("entities", []) or []:
                if ent not in entities:
                    findings.append(Finding("ERROR", r, f"guidance references unknown entity '{ent}'"))
            _check_evidence_paths(root, r, fm.get("derived_from", []), findings, ("knowledge/events/", "knowledge/decisions/", "factory/signals/", "sources/"))
            _check_supersedes_chain(root, p, r, fm, "knowledge/guidance/", findings, match_keys=("slug",))

        elif rtype == "decision":
            did = fm.get("id")
            if not isinstance(did, str) or not DECISION_ID_RE.fullmatch(did):
                findings.append(Finding("ERROR", r, f"decision id {did!r} must match DEC-NNN..."))
                family = p.stem
            elif fm.get("status") == "superseded":
                family = p.parent.name
                is_hist = (
                    p.parent.parent == (root / "knowledge/decisions")
                    and bool(DECISION_ID_RE.fullmatch(family))
                    and bool(HIST_STEM_RE.fullmatch(p.stem))
                )
                if not is_hist:
                    findings.append(Finding("ERROR", r, "superseded decision must reside at knowledge/decisions/<DEC-ID>/YYYY-MM-DD[-N].md"))
                elif not did.startswith(family):
                    findings.append(Finding("ERROR", r, f"superseded decision id '{did}' must start with decision family '{family}'"))
                decisions_by_id[family].append((p, r, fm))
            else:
                family = did
                expected_head = f"knowledge/decisions/{did}.md"
                if r != expected_head:
                    findings.append(Finding("ERROR", r, f"decision '{did}' must reside at {expected_head}"))
                decisions_by_id[family].append((p, r, fm))
            dec_by = fm.get("decided_by")
            if isinstance(dec_by, str) and not AGENT_ID_RE.fullmatch(dec_by):
                findings.append(Finding("ERROR", r, f"decision decided_by '{dec_by}' must be a valid agent ID"))
            if fm.get("status") == "retracted" and (not fm.get("retracted_at") or not fm.get("retraction_reason")):
                findings.append(Finding("ERROR", r, "retracted decision requires retracted_at and retraction_reason"))
            for ent in fm.get("entities", []) or []:
                if ent not in entities:
                    findings.append(Finding("ERROR", r, f"decision references unknown entity '{ent}'"))
            _check_evidence_paths(root, r, fm.get("derived_from", []), findings, ("knowledge/events/", "knowledge/decisions/", "factory/proposals/", "factory/signals/", "sources/"))
            if isinstance(fm.get("derived_from"), list) and r in fm["derived_from"]:
                findings.append(Finding("ERROR", r, "decision cannot cite itself in derived_from"))
            _check_supersedes_chain(root, p, r, fm, "knowledge/decisions/", findings, match_keys=(), decision_family=family)

        elif rtype == "signal":
            for ent in fm.get("entities", []) or []:
                if ent not in entities:
                    findings.append(Finding("ERROR", r, f"signal references unknown entity '{ent}'"))
            _check_evidence_paths(root, r, fm.get("evidence", []), findings, ("knowledge/events/", "sources/"))

        elif rtype == "proposal":
            from .governance import compute_proposal_hash

            pid = fm.get("id", "")
            proposals_by_id[pid] = (r, fm)
            ops = fm.get("ops")
            if not isinstance(ops, list) or len(ops) == 0:
                findings.append(Finding("ERROR", r, "proposal must contain at least one executable operation (diagnostic flags belong in factory/signals/)"))
            expected_hash = compute_proposal_hash(fm)
            if fm.get("content_hash") != expected_hash:
                findings.append(Finding("ERROR", r, f"proposal content_hash mismatch: expected {expected_hash}, got {fm.get('content_hash')}"))
            if fm.get("status") == "published":
                rcpt_id = fm.get("receipt_id")
                if not isinstance(rcpt_id, str) or not (root / f"factory/receipts/{rcpt_id}.md").is_file():
                    findings.append(Finding("ERROR", r, f"published proposal requires an existing receipt in factory/receipts/ (got {rcpt_id!r})"))

        elif rtype == "review":
            reviews_list.append((r, fm))

        elif rtype == "note":
            if fm.get("authoritative") is True:
                findings.append(Finding("ERROR", r, "notes under knowledge/notes/ are non-authoritative prose; set authoritative: false or promote to fact/skill/guidance/decision"))

    # Cross-record group checks for facts
    for (ent, pred), group in facts_by_slot.items():
        actives = [(p, r, d) for p, r, d in group if is_active_head(d)]
        has_head = bool(actives) or any(
            r == f"knowledge/facts/{ent}/{pred}.md" and d.get("status") == "retracted"
            for _, r, d in group
        )
        if len(actives) > 1:
            findings.append(Finding("ERROR", actives[0][1], f"multiple active facts for {ent}/{pred}"))
        elif not has_head and any(d.get("status") == "superseded" for _, _, d in group):
            findings.append(Finding("ERROR", group[0][1], f"superseded history chain for {ent}/{pred} has no active head"))
        for idx, (_, r1, d1) in enumerate(group):
            if d1.get("status") == "retracted":
                continue
            for _, r2, d2 in group[idx + 1:]:
                if d2.get("status") == "retracted":
                    continue
                try:
                    a, b = fact_interval(d1), fact_interval(d2)
                    if max(a[0], b[0]) < min(a[1], b[1]) and d1.get("value") != d2.get("value"):
                        findings.append(Finding("ERROR", r1, f"contradicts overlapping fact {r2}"))
                except ValueError:
                    pass

    # Cross-record group checks for skills, guidance, and decisions
    for slug, group in skills_by_slug.items():
        actives = [(p, r, d) for p, r, d in group if is_active_head(d)]
        has_head = bool(actives) or any(
            r == f"knowledge/skills/{slug}.md" and d.get("status") in {"retracted", "deprecated"}
            for _, r, d in group
        )
        if len(actives) > 1:
            findings.append(Finding("ERROR", actives[0][1], f"multiple active skills for '{slug}'"))
        elif not has_head and any(d.get("status") == "superseded" for _, _, d in group):
            findings.append(Finding("ERROR", group[0][1], f"superseded history chain for skill '{slug}' has no active head"))

    for slug, group in guidance_by_slug.items():
        actives = [(p, r, d) for p, r, d in group if is_active_head(d)]
        has_head = bool(actives) or any(
            r == f"knowledge/guidance/{slug}.md" and d.get("status") == "retracted"
            for _, r, d in group
        )
        if len(actives) > 1:
            findings.append(Finding("ERROR", actives[0][1], f"multiple active guidance records for '{slug}'"))
        elif not has_head and any(d.get("status") == "superseded" for _, _, d in group):
            findings.append(Finding("ERROR", group[0][1], f"superseded history chain for guidance '{slug}' has no active head"))

    for family, group in decisions_by_id.items():
        actives = [(p, r, d) for p, r, d in group if is_active_head(d)]
        has_head = bool(actives) or any(
            r == f"knowledge/decisions/{family}.md" and d.get("status") in {"retracted", "deprecated"}
            for _, r, d in group
        )
        if len(actives) > 1:
            findings.append(Finding("ERROR", actives[0][1], f"multiple accepted decisions for '{family}'"))
        elif not has_head and any(d.get("status") == "superseded" for _, _, d in group):
            findings.append(Finding("ERROR", group[0][1], f"superseded history chain for decision '{family}' has no active head"))

    # Cross-record review governance checks
    for r, rev in reviews_list:
        prop_id = rev.get("proposal_id", "")
        if prop_id not in proposals_by_id:
            findings.append(Finding("ERROR", r, f"review references nonexistent proposal '{prop_id}'"))
            continue
        _, prop = proposals_by_id[prop_id]
        reviewer = rev.get("reviewer_id")
        if reviewer == prop.get("proposer_id"):
            findings.append(Finding("ERROR", r, f"self-approval not allowed: reviewer '{reviewer}' is the proposer"))
        ns = prop.get("namespace", "")
        ns_cfg = namespaces_cfg.get(ns, {})
        ag = agents_cfg.get(str(reviewer), {})
        ag_roles = set(ag.get("roles", []))
        allowed_role_names = set(ns_cfg.get("allowed_reviewers", []))
        if allowed_role_names and not (ag_roles & allowed_role_names) and "owner" not in ag_roles:
            findings.append(Finding("ERROR", r, f"reviewer '{reviewer}' lacks allowed reviewer role for namespace '{ns}'"))
        if rev.get("proposal_content_hash") != prop.get("content_hash"):
            findings.append(Finding("WARN", r, f"review hash does not match current content_hash of proposal '{prop_id}' (stale review)"))
        if rev.get("verdict") in {"rejected", "changes_requested"} and not rev.get("comment"):
            findings.append(Finding("ERROR", r, f"verdict '{rev.get('verdict')}' requires a non-empty comment"))

    # Wikilink resolution across canonical knowledge/
    for p, r, fm, body in md_records:
        if not r.startswith("knowledge/"):
            continue
        for raw_link in WIKILINK_RE.findall(body):
            ok, ambiguous = _link_resolves(raw_link, known_link_targets, by_stem)
            if not ok:
                findings.append(Finding("ERROR", r, f"unresolved wikilink: {raw_link}"))
            elif ambiguous:
                findings.append(Finding("ERROR", r, f"ambiguous wikilink: {raw_link}"))

    # Optional / strict staleness check
    if check_stale:
        for stale_rel, reason in compute_stale_records(root):
            findings.append(Finding("WARN", stale_rel, f"stale record: {reason}"))

    # Generated artifact non-edit & freshness check
    require_gen = check_generated or strict or bool(manifest.get("settings", {}).get("require_generated_clean", False))
    if require_gen:
        from .rebuild import verify_generated_integrity

        for gen_rel, msg in verify_generated_integrity(root):
            findings.append(Finding("ERROR" if (strict or check_generated) else "WARN", gen_rel, msg))

    return findings


def _check_evidence_paths(
    root: Path,
    rel: str,
    paths: Any,
    findings: list[Finding],
    prefixes: tuple[str, ...],
) -> None:
    if not isinstance(paths, list):
        return
    for ref in paths:
        try:
            target = safe_path(root, ref, prefixes)
            if not target.is_file():
                findings.append(Finding("ERROR", rel, f"referenced evidence file does not exist: {ref}"))
        except ValueError as exc:
            findings.append(Finding("ERROR", rel, str(exc)))


def _check_supersedes_chain(
    root: Path,
    path: Path,
    rel: str,
    fm: dict[str, Any],
    prefix: str,
    findings: list[Finding],
    *,
    match_keys: tuple[str, ...],
    decision_family: str | None = None,
) -> None:
    sup = fm.get("supersedes")
    if not sup:
        return
    try:
        target = safe_path(root, sup, (prefix,))
    except ValueError as exc:
        findings.append(Finding("ERROR", rel, str(exc)))
        return
    if not target.is_file():
        findings.append(Finding("ERROR", rel, f"supersedes target does not exist: {sup}"))
        return
    prior_fm, _ = split_frontmatter(target)
    if prior_fm.get("type") != fm.get("type"):
        findings.append(Finding("ERROR", rel, f"supersedes target type mismatch: {prior_fm.get('type')!r} != {fm.get('type')!r}"))
    if prior_fm.get("status") != "superseded":
        findings.append(Finding("ERROR", rel, f"supersedes target {sup} must have status 'superseded', got {prior_fm.get('status')!r}"))
    for k in match_keys:
        if prior_fm.get(k) != fm.get(k):
            findings.append(Finding("ERROR", rel, f"supersedes mismatch on '{k}': {prior_fm.get(k)!r} != {fm.get(k)!r}"))
    if decision_family is not None and target.parent.name != decision_family:
        findings.append(Finding("ERROR", rel, f"supersedes decision target {sup} must reside under knowledge/decisions/{decision_family}/"))
    if fm.get("type") == "skill":
        old_ver, new_ver = prior_fm.get("version"), fm.get("version")
        if isinstance(old_ver, int) and isinstance(new_ver, int) and new_ver <= old_ver:
            findings.append(Finding("ERROR", rel, f"superseding skill version ({new_ver}) must be > prior version ({old_ver})"))
    if fm.get("type") == "fact":
        old_end = parse_date(prior_fm.get("valid_until"))
        new_start = parse_date(fm.get("valid_from"))
        if old_end is None or new_start is None:
            findings.append(Finding("ERROR", rel, "fact supersession requires prior valid_until and new valid_from"))
        elif old_end != new_start:
            findings.append(Finding("ERROR", rel, f"half-open boundary mismatch: prior valid_until ({old_end}) != new valid_from ({new_start})"))
    seen = {path.resolve()}
    cursor = target
    while cursor.is_file():
        if cursor.resolve() in seen:
            findings.append(Finding("ERROR", rel, "supersedes chain contains a cycle"))
            break
        seen.add(cursor.resolve())
        anc, _ = split_frontmatter(cursor)
        nxt = anc.get("supersedes")
        if not nxt:
            break
        try:
            cursor = safe_path(root, nxt, (prefix,))
        except ValueError as exc:
            findings.append(Finding("ERROR", rel, str(exc)))
            break
        if not cursor.is_file():
            findings.append(Finding("ERROR", rel, f"supersedes target does not exist: {nxt}"))
            break


def compute_stale_records(root: Path) -> list[tuple[str, str]]:
    manifest = load_manifest(root)
    threshold = int(manifest.get("settings", {}).get("stale_after_days", 180))
    ref = today()
    cutoff = ref - dt.timedelta(days=threshold)
    stale: list[tuple[str, str]] = []
    for folder, rtype in (("knowledge/facts", "fact"), ("knowledge/skills", "skill"), ("knowledge/guidance", "guidance")):
        for path, fm, _ in scan_records(root, folder, rtype):
            if not is_active_head(fm):
                continue
            reasons: list[str] = []
            rev_after = parse_date(fm.get("review_after"))
            if rev_after and rev_after < ref:
                reasons.append(f"review_after {rev_after} < {ref}")
            last_conf = parse_date(fm.get("last_confirmed"))
            if last_conf and last_conf < cutoff:
                reasons.append(f"last_confirmed {last_conf} older than {threshold}d cutoff ({cutoff})")
            if reasons:
                stale.append((rel_path(path, root), "; ".join(reasons)))
    return stale
