"""Unified query, search, graph, alias resolution, and full Factory lineage (`why`)."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Any

from .bootstrap import render_scalar_inline
from .model import (
    fact_interval,
    file_sha256,
    fold_text,
    is_active_head,
    is_fact_visible,
    load_entities,
    parse_date,
    parse_datetime,
    rel_path,
    resolve_entity,
    safe_path,
    scan_records,
    split_frontmatter,
)
from .rebuild import build_all_indexes, compute_graph_edges


def query_facts(
    root: Path,
    *,
    entity: str | None = None,
    predicate: str | None = None,
    as_of: str | None = None,
    history: bool = False,
    trust: str | None = None,
    min_confidence: float | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    as_of_date = parse_date(as_of) if as_of else None
    rows = scan_records(root, "knowledge/facts", "fact")
    if history:
        rows.sort(key=lambda r: (fact_interval(r[1])[0], parse_datetime(r[1]["observed_at"]), rel_path(r[0], root)))

    matches: list[dict[str, Any]] = []
    lines: list[str] = []
    for path, fm, _ in rows:
        if entity and fm.get("entity") != entity:
            continue
        if predicate and fm.get("predicate") != predicate:
            continue
        if not history and not is_fact_visible(fm, as_of_date):
            continue
        if trust and fm.get("trust") != trust:
            continue
        if min_confidence is not None:
            c = fm.get("confidence")
            if c is None or float(c) < min_confidence:
                continue
        r = rel_path(path, root)
        rec = dict(fm, path=r)
        matches.append(rec)
        lines.append(f"{r}: {fm['entity']}/{fm['predicate']} = {render_scalar_inline(fm.get('value'))}")
        if history:
            lines.append(
                f"  status={fm.get('status')} valid={fm.get('valid_from') or 'open'}..{fm.get('valid_until') or 'present'} observed={fm.get('observed_at')}"
            )
    if not lines:
        lines.append("No facts found.")
    return "\n".join(lines) + "\n", matches


def query_skills(
    root: Path,
    *,
    domain: str | None = None,
    trigger: str | None = None,
    history: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    needle = fold_text(trigger) if trigger else None
    matches: list[dict[str, Any]] = []
    lines: list[str] = []
    for path, fm, body in scan_records(root, "knowledge/skills", "skill"):
        if not history and not is_active_head(fm):
            continue
        if domain and fm.get("domain") != domain:
            continue
        if needle:
            hay = " ".join([str(fm.get("slug", "")), str(fm.get("title", "")), *(str(t) for t in (fm.get("triggers") or []))])
            if needle not in fold_text(hay):
                continue
        r = rel_path(path, root)
        matches.append(dict(fm, path=r, body=body.strip()))
        lines.append(f"{r}: {fm['slug']} (v{fm['version']}, {fm['domain']}) — {fm['title']} | triggers={fm.get('triggers')}")
    if not lines:
        lines.append("No skills found.")
    return "\n".join(lines) + "\n", matches


def query_guidance(
    root: Path,
    *,
    domain: str | None = None,
    scope: str | None = None,
    priority: str | None = None,
    history: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    matches: list[dict[str, Any]] = []
    lines: list[str] = []
    for path, fm, body in scan_records(root, "knowledge/guidance", "guidance"):
        if not history and not is_active_head(fm):
            continue
        if domain and fm.get("domain") != domain:
            continue
        if scope and fm.get("scope") not in {scope, "all"}:
            continue
        if priority and fm.get("priority") != priority:
            continue
        r = rel_path(path, root)
        matches.append(dict(fm, path=r, body=body.strip()))
        lines.append(f"{r}: [{fm['priority'].upper()}] {fm['slug']} ({fm['domain']}/{fm['scope']}) — {fm['policy_rule']}")
    if not lines:
        lines.append("No guidance found.")
    return "\n".join(lines) + "\n", matches


def query_decisions(
    root: Path,
    *,
    domain: str | None = None,
    status: str | None = "accepted",
    history: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    matches: list[dict[str, Any]] = []
    lines: list[str] = []
    for path, fm, body in scan_records(root, "knowledge/decisions", "decision"):
        if not history and status and fm.get("status") != status:
            continue
        if domain and fm.get("domain") != domain:
            continue
        r = rel_path(path, root)
        matches.append(dict(fm, path=r, body=body.strip()))
        lines.append(f"{r}: {fm['id']} [{fm['status']}] ({fm['decided_at']}) — {fm['title']}: {fm['summary']}")
    if not lines:
        lines.append("No decisions found.")
    return "\n".join(lines) + "\n", matches


def query_events(
    root: Path,
    *,
    since: str | None = None,
    until: str | None = None,
    entity: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    d_since = parse_date(since) if since else None
    d_until = parse_date(until) if until else None
    if d_since and d_until and d_since > d_until:
        raise ValueError("--since must be <= --until")
    matches: list[dict[str, Any]] = []
    lines: list[str] = []
    for path, fm, _ in scan_records(root, "knowledge/events", "event"):
        ev_date = parse_datetime(fm["occurred_at"]).date()
        if d_since and ev_date < d_since:
            continue
        if d_until and ev_date > d_until:
            continue
        if entity and entity not in (fm.get("entities") or []):
            continue
        r = rel_path(path, root)
        matches.append(dict(fm, path=r))
        ents = ", ".join(fm.get("entities") or [])
        lines.append(f"{ev_date.isoformat()} — {fm['summary']} [{ents}] — {r}")
    if not lines:
        lines.append("No events found.")
    return "\n".join(lines) + "\n", matches


def query_signals(
    root: Path,
    *,
    status: str | None = None,
    kind: str | None = None,
    severity: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    matches: list[dict[str, Any]] = []
    lines: list[str] = []
    for path, fm, _ in scan_records(root, "factory/signals", "signal"):
        if status and fm.get("status") != status:
            continue
        if kind and fm.get("kind") != kind:
            continue
        if severity and fm.get("severity") != severity:
            continue
        r = rel_path(path, root)
        matches.append(dict(fm, path=r))
        lines.append(f"{fm['id']} [{fm['status']}/{fm['severity']}/{fm['kind']}] {fm['summary']} — {r}")
    if not lines:
        lines.append("No signals found.")
    return "\n".join(lines) + "\n", matches


def query_receipts(
    root: Path,
    *,
    mode: str | None = None,
    actor: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    matches: list[dict[str, Any]] = []
    lines: list[str] = []
    for path, fm, _ in scan_records(root, "factory/receipts", "receipt"):
        if mode and fm.get("mode") != mode:
            continue
        if actor and fm.get("actor_id") != actor:
            continue
        r = rel_path(path, root)
        matches.append(dict(fm, path=r))
        lines.append(f"{fm['id']} [{fm['mode']}/{fm['status']}] actor={fm['actor_id']} — {r}")
    if not lines:
        lines.append("No receipts found.")
    return "\n".join(lines) + "\n", matches


def query_resolve_entity(root: Path, name: str) -> tuple[int, str, dict[str, Any]]:
    hits = resolve_entity(root, name)
    if len(hits) == 1:
        return 0, f"{hits[0]}\n", {"entity_id": hits[0], "candidates": hits}
    if len(hits) == 0:
        return 2, f"No entity found matching {name!r}\n", {"entity_id": None, "candidates": []}
    return 2, f"Ambiguous entity name {name!r}: {', '.join(hits)}\n", {"entity_id": None, "candidates": hits}


def query_by_id(root: Path, record_id: str) -> tuple[int, str, dict[str, Any]]:
    for plane in ("knowledge", "factory/signals", "factory/proposals", "factory/reviews", "factory/receipts"):
        for path, fm, _ in scan_records(root, plane):
            if fm.get("id") == record_id:
                r = rel_path(path, root)
                return 0, f"{r}: {fm.get('type')}\n", {"record": dict(fm, path=r)}
    return 1, f"No record found with id {record_id!r}\n", {"record": None}


def query_why(
    root: Path,
    *,
    kind: str,
    target: str,
    predicate: str | None = None,
) -> tuple[str, dict[str, Any]]:
    if kind == "fact":
        if not predicate:
            raise ValueError("`query why fact` requires <entity> <predicate>")
        rel = f"knowledge/facts/{target}/{predicate}.md"
    elif kind == "skill":
        rel = f"knowledge/skills/{target}.md"
    elif kind == "guidance":
        rel = f"knowledge/guidance/{target}.md"
    elif kind == "decision":
        rel = f"knowledge/decisions/{target}.md"
    else:
        raise ValueError(f"unsupported `why` kind {kind!r}; choose from fact, skill, guidance, decision")

    path = safe_path(root, rel)
    if not path.is_file():
        raise ValueError(f"canonical record not found: {rel}")

    fm, _ = split_frontmatter(path)
    cur_hash = file_sha256(path)

    # 1. Supersedes history chain
    history_chain: list[dict[str, Any]] = []
    sup_cursor = fm.get("supersedes")
    while sup_cursor:
        sp = safe_path(root, str(sup_cursor))
        if not sp.is_file():
            break
        sfm, _ = split_frontmatter(sp)
        history_chain.append(dict(sfm, path=str(sup_cursor)))
        sup_cursor = sfm.get("supersedes")

    # 2. Primary evidence (`derived_from`)
    evidence_items: list[dict[str, Any]] = []
    for ref in fm.get("derived_from") or []:
        ep = safe_path(root, str(ref))
        if ep.is_file():
            efm, ebody = split_frontmatter(ep)
            heading = next((ln.lstrip("# ").strip() for ln in ebody.splitlines() if ln.startswith("# ")), ep.stem)
            title = efm.get("title") or efm.get("summary") or heading
            date = efm.get("occurred_at") or efm.get("created_at") or efm.get("decided_at") or "undated"
            evidence_items.append({"path": str(ref), "type": efm.get("type", "source"), "title": title, "date": date})

    # 3. Authoring receipt -> proposal -> reviews -> signals
    matching_receipt: dict[str, Any] | None = None
    for rp, rfm, _ in reversed(scan_records(root, "factory/receipts", "receipt")):
        for tf in rfm.get("touched_files") or []:
            if isinstance(tf, dict) and tf.get("path") == rel:
                if tf.get("after_hash") == cur_hash or matching_receipt is None:
                    matching_receipt = dict(rfm, path=rel_path(rp, root))
                if tf.get("after_hash") == cur_hash:
                    break
        if matching_receipt and any(
            tf.get("path") == rel and tf.get("after_hash") == cur_hash
            for tf in (matching_receipt.get("touched_files") or [])
        ):
            break

    proposal_data: dict[str, Any] | None = None
    review_items: list[dict[str, Any]] = []
    signal_items: list[dict[str, Any]] = []

    if matching_receipt:
        prop_id = matching_receipt.get("proposal_id")
        if prop_id:
            pp = root / f"factory/proposals/{prop_id}.md"
            if pp.is_file():
                pfm, _ = split_frontmatter(pp)
                proposal_data = dict(pfm, path=rel_path(pp, root))
        rev_ids = set(matching_receipt.get("review_ids") or [])
        if rev_ids:
            for rvp, rvfm, _ in scan_records(root, "factory/reviews", "review"):
                if rvfm.get("id") in rev_ids:
                    review_items.append(dict(rvfm, path=rel_path(rvp, root)))
        sig_ids = set(matching_receipt.get("resolved_signals") or [])
        if sig_ids:
            for sp, sfm, _ in scan_records(root, "factory/signals", "signal"):
                if sfm.get("id") in sig_ids:
                    signal_items.append(dict(sfm, path=rel_path(sp, root)))

    lines = [
        f"Record: {rel} (id={fm['id']}, type={fm['type']}, status={fm.get('status')})",
        f"  trust={fm.get('trust', 'n/a')} confidence={fm.get('confidence', 'n/a')} assertion={fm.get('assertion', 'n/a')}",
    ]
    if evidence_items:
        for ev in evidence_items:
            lines.append(f"  evidence: {ev['path']} | {ev['title']} | {ev['date']}")
    if matching_receipt:
        lines.append(f"  receipt: {matching_receipt['id']} (mode={matching_receipt['mode']}, actor={matching_receipt['actor_id']})")
    if proposal_data:
        lines.append(f"  proposal: {proposal_data['id']} (proposer={proposal_data['proposer_id']})")
    for rv in review_items:
        lines.append(f"  review: {rv['id']} ({rv['verdict']} by {rv['reviewer_id']})")
    for sg in signal_items:
        lines.append(f"  signal: {sg['id']} ({sg['kind']}: {sg['summary']})")
    if history_chain:
        lines.append(f"  supersedes: {len(history_chain)} prior version(s) -> {history_chain[0]['path']}")

    payload = {
        "path": rel,
        "record": fm,
        "evidence": evidence_items,
        "supersedes_chain": history_chain,
        "receipt": matching_receipt,
        "proposal": proposal_data,
        "reviews": review_items,
        "resolved_signals": signal_items,
    }
    return "\n".join(lines) + "\n", payload


def _warn_if_index_stale(root: Path, index_rel: str) -> list[str]:
    diags: list[str] = []
    idx_path = root / index_rel
    if not idx_path.is_file():
        return diags
    expected = build_all_indexes(root).get(index_rel)
    actual = idx_path.read_text(encoding="utf-8")
    if expected is not None and actual != expected:
        msg = f"WARN: {index_rel} is stale or hand-edited; computing canonical answer from filesystem (run `kf.py rebuild`)"
        diags.append(msg)
    return diags


def query_search(
    root: Path,
    term: str,
    *,
    types: set[str] | None = None,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    diags = _warn_if_index_stale(root, "_generated/indexes/lexical.md")
    allowed_types = types or {"fact", "skill", "guidance", "decision"}
    needle = fold_text(term)
    resolved_entities = set(resolve_entity(root, term))
    entities_map = load_entities(root)

    scored: list[tuple[int, str, dict[str, Any], str]] = []

    if "fact" in allowed_types:
        for p, fm, body in scan_records(root, "knowledge/facts", "fact"):
            if not is_fact_visible(fm):
                continue
            r = rel_path(p, root)
            ent = str(fm.get("entity", ""))
            ent_names = " ".join([ent, str(entities_map.get(ent, {}).get("display", "")), *(entities_map.get(ent, {}).get("aliases") or [])])
            fm_text = f"{ent} {fm.get('predicate')} {render_scalar_inline(fm.get('value'))} {ent_names}"
            rank: int | None = None
            if ent in resolved_entities:
                rank = 0
            elif needle and needle in fold_text(fm_text):
                rank = 1
            elif needle and needle in fold_text(body):
                rank = 2
            if rank is not None:
                line = f"[fact] {ent}/{fm['predicate']} = {render_scalar_inline(fm.get('value'))}  [{r}]"
                scored.append((rank, r, {"type": "fact", "path": r, "entity": ent, "predicate": fm["predicate"], "value": fm.get("value")}, line))

    if "skill" in allowed_types:
        for p, fm, body in scan_records(root, "knowledge/skills", "skill"):
            if not is_active_head(fm):
                continue
            r = rel_path(p, root)
            sk_ents = set(fm.get("entities") or [])
            fm_text = f"{fm.get('slug')} {fm.get('title')} {fm.get('domain')} {' '.join(str(t) for t in (fm.get('triggers') or []))}"
            rank = 0 if (sk_ents & resolved_entities) else (1 if needle in fold_text(fm_text) else (2 if needle in fold_text(body) else None))
            if rank is not None:
                line = f"[skill] {fm['slug']} — {fm['title']}  [{r}]"
                scored.append((rank, r, {"type": "skill", "path": r, "slug": fm["slug"], "title": fm["title"]}, line))

    if "guidance" in allowed_types:
        for p, fm, body in scan_records(root, "knowledge/guidance", "guidance"):
            if not is_active_head(fm):
                continue
            r = rel_path(p, root)
            gd_ents = set(fm.get("entities") or [])
            fm_text = f"{fm.get('slug')} {fm.get('title')} {fm.get('domain')} {fm.get('policy_rule')}"
            rank = 0 if (gd_ents & resolved_entities) else (1 if needle in fold_text(fm_text) else (2 if needle in fold_text(body) else None))
            if rank is not None:
                line = f"[guidance] {fm['slug']} — {fm['policy_rule']}  [{r}]"
                scored.append((rank, r, {"type": "guidance", "path": r, "slug": fm["slug"], "title": fm["title"]}, line))

    if "decision" in allowed_types:
        for p, fm, body in scan_records(root, "knowledge/decisions", "decision"):
            if fm.get("status") != "accepted":
                continue
            r = rel_path(p, root)
            dc_ents = set(fm.get("entities") or [])
            fm_text = f"{fm.get('id')} {fm.get('title')} {fm.get('domain')} {fm.get('summary')}"
            rank = 0 if (dc_ents & resolved_entities) else (1 if needle in fold_text(fm_text) else (2 if needle in fold_text(body) else None))
            if rank is not None:
                line = f"[decision] {fm['id']} — {fm['title']}  [{r}]"
                scored.append((rank, r, {"type": "decision", "path": r, "id": fm["id"], "title": fm["title"]}, line))

    scored.sort(key=lambda item: (item[0], item[1]))
    if not scored:
        return f"No records found matching {term!r}\n", [], diags
    return "\n".join(item[3] for item in scored) + "\n", [item[2] for item in scored], diags


def query_graph(root: Path, node: str) -> tuple[str, list[dict[str, str]], list[str]]:
    diags = _warn_if_index_stale(root, "_generated/indexes/graph.md")
    resolved = resolve_entity(root, node)
    canonical_node = resolved[0] if len(resolved) == 1 else node
    edges = compute_graph_edges(root)
    neighbors: list[dict[str, str]] = []
    lines: list[str] = []
    for src, rel_name, dst, ev in edges:
        if src == canonical_node:
            neighbors.append({"direction": "out", "relation": rel_name, "neighbor": dst, "evidence": ev})
            lines.append(f"{src} --[{rel_name}]--> {dst}  [{ev}]")
        elif dst == canonical_node:
            neighbors.append({"direction": "in", "relation": rel_name, "neighbor": src, "evidence": ev})
            lines.append(f"{src} --[{rel_name}]--> {dst}  [{ev}]")
    if not lines:
        return f"No graph relationships found for {canonical_node!r}\n", [], diags
    return "\n".join(lines) + "\n", neighbors, diags
