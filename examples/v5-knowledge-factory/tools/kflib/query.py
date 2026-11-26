"""Unified query, search, graph, alias resolution, and full Factory lineage (`why`)."""

from __future__ import annotations

import datetime as dt
import hashlib
import math
import re
import sys
from collections import Counter, deque
from pathlib import Path
from typing import Any

from .bootstrap import render_scalar_inline
from .model import (
    canonical_source_digest,
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
from .rebuild import GENERATED_BANNER_RE, build_all_indexes, compute_graph_edges

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_LIGHT_SUFFIXES = (
    "aciones", "iciones", "acion", "icion", "mente", "ation", "ition",
    "izing", "ising", "ingly", "edly", "ness", "ment", "able", "ible",
    "idad", "ando", "iendo", "ing", "ied", "ies", "ed", "es", "s",
)


def _stem_token(tok: str) -> str:
    if len(tok) <= 4:
        return tok
    for suf in _LIGHT_SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= 4:
            return tok[: -len(suf)]
    return tok


def tokenize_text(text: str) -> list[str]:
    return _TOKEN_RE.findall(fold_text(text))


def tokenize_stemmed(text: str) -> list[str]:
    return [_stem_token(t) for t in tokenize_text(text)]


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
    needle_tokens = tokenize_stemmed(trigger) if trigger else []
    scored_rows: list[tuple[float, str, dict[str, Any], str]] = []
    for path, fm, body in scan_records(root, "knowledge/skills", "skill"):
        if not history and not is_active_head(fm):
            continue
        if domain and fm.get("domain") != domain:
            continue
        score = 0.0
        if needle:
            hay_meta = " ".join(
                [
                    str(fm.get("slug", "")),
                    str(fm.get("title", "")),
                    str(fm.get("domain", "")),
                    *(str(t) for t in (fm.get("triggers") or [])),
                    *(str(x) for x in (fm.get("inputs") or [])),
                    *(str(x) for x in (fm.get("outputs") or [])),
                ]
            )
            folded_meta = fold_text(hay_meta)
            folded_all = f"{folded_meta} {fold_text(body)}"
            if needle in folded_meta:
                score += 10.0
            elif needle in folded_all:
                score += 5.0
            if needle_tokens:
                meta_toks = set(tokenize_stemmed(hay_meta))
                all_toks = meta_toks | set(tokenize_stemmed(body))
                matched_meta = sum(1 for t in needle_tokens if t in meta_toks)
                matched_all = sum(1 for t in needle_tokens if t in all_toks)
                if matched_all == len(needle_tokens):
                    score += 6.0 + 2.0 * matched_meta
                elif matched_meta > 0 and len(needle_tokens) == 1:
                    score += 3.0
            if score <= 0.0:
                continue
        r = rel_path(path, root)
        rec = dict(fm, path=r, body=body.strip())
        line = f"{r}: {fm['slug']} (v{fm['version']}, {fm['domain']}) — {fm['title']} | triggers={fm.get('triggers')}"
        scored_rows.append((score, r, rec, line))
    scored_rows.sort(key=lambda item: (-item[0], item[1]))
    matches = [item[2] for item in scored_rows]
    lines = [item[3] for item in scored_rows]
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
    """Fast O(1)-per-index staleness and tamper verification via embedded digests."""
    diags: list[str] = []
    idx_path = root / index_rel
    if not idx_path.is_file():
        return diags
    actual = idx_path.read_text(encoding="utf-8")
    match = GENERATED_BANNER_RE.match(actual)
    stale = False
    if not match:
        stale = True
    else:
        recorded_source, recorded_sha = match.group(1), match.group(2)
        body_after_banner = actual[match.end() :]
        actual_sha = "sha256:" + hashlib.sha256(body_after_banner.encode("utf-8")).hexdigest()
        current_source = canonical_source_digest(root)
        if actual_sha != recorded_sha or recorded_source != current_source:
            stale = True
    if stale:
        msg = f"WARN: {index_rel} is stale or hand-edited; computing canonical answer from filesystem (run `kf.py rebuild`)"
        diags.append(msg)
    return diags


def _bm25_scores(
    query_tokens: list[str],
    docs_tokens: list[list[str]],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[float]:
    n_docs = len(docs_tokens)
    if not n_docs or not query_tokens:
        return [0.0] * n_docs
    unique_q = list(dict.fromkeys(query_tokens))
    avgdl = sum(len(d) for d in docs_tokens) / max(1, n_docs)
    df: dict[str, int] = {t: 0 for t in unique_q}
    doc_counters = [Counter(d) for d in docs_tokens]
    for c in doc_counters:
        for t in unique_q:
            if c.get(t, 0) > 0:
                df[t] += 1
    scores: list[float] = []
    for d, c in zip(docs_tokens, doc_counters):
        dl = len(d)
        s = 0.0
        for t in unique_q:
            tf = c.get(t, 0)
            if tf <= 0:
                continue
            idf = math.log(1.0 + (n_docs - df[t] + 0.5) / (df[t] + 0.5))
            denom = tf + k1 * (1.0 - b + b * (dl / max(1.0, avgdl)))
            s += idf * ((tf * (k1 + 1.0)) / max(1e-9, denom))
        scores.append(s)
    return scores


def query_search(
    root: Path,
    term: str,
    *,
    types: set[str] | None = None,
    include_notes: bool = False,
    include_sources: bool = False,
    limit: int | None = None,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    diags = _warn_if_index_stale(root, "_generated/indexes/lexical.md")
    allowed_types = set(types) if types is not None else {"fact", "skill", "guidance", "decision"}
    if include_notes:
        allowed_types.add("note")
    if include_sources:
        allowed_types.add("source")
    needle = fold_text(term)
    q_tokens = tokenize_stemmed(term)
    if not needle:
        return f"No records found matching {term!r}\n", [], diags

    # Resolve entities both from the full query and from individual query tokens
    resolved_entities = set(resolve_entity(root, term))
    token_resolved_entities: set[str] = set()
    for raw_tok in tokenize_text(term):
        if len(raw_tok) >= 3:
            token_resolved_entities.update(resolve_entity(root, raw_tok))
    entities_map = load_entities(root)

    # Collect candidate corpus entries for BM25 + field-weighted scoring
    corpus: list[dict[str, Any]] = []

    if "fact" in allowed_types:
        for p, fm, body in scan_records(root, "knowledge/facts", "fact"):
            if not is_fact_visible(fm):
                continue
            r = rel_path(p, root)
            ent = str(fm.get("entity", ""))
            ent_names = " ".join([ent, str(entities_map.get(ent, {}).get("display", "")), *(entities_map.get(ent, {}).get("aliases") or [])])
            fm_text = f"{ent} {fm.get('predicate')} {render_scalar_inline(fm.get('value'))} {ent_names}"
            corpus.append({
                "path": r,
                "entity_exact": ent in resolved_entities,
                "entity_partial": ent in token_resolved_entities,
                "fm_text": fm_text,
                "body": body,
                "meta": {"type": "fact", "path": r, "entity": ent, "predicate": fm["predicate"], "value": fm.get("value")},
                "line": f"[fact] {ent}/{fm['predicate']} = {render_scalar_inline(fm.get('value'))}  [{r}]",
            })

    if "skill" in allowed_types:
        for p, fm, body in scan_records(root, "knowledge/skills", "skill"):
            if not is_active_head(fm):
                continue
            r = rel_path(p, root)
            sk_ents = set(fm.get("entities") or [])
            fm_text = f"{fm.get('slug')} {fm.get('title')} {fm.get('domain')} {' '.join(str(t) for t in (fm.get('triggers') or []))} {' '.join(str(x) for x in (fm.get('outputs') or []))}"
            corpus.append({
                "path": r,
                "entity_exact": bool(sk_ents & resolved_entities),
                "entity_partial": bool(sk_ents & token_resolved_entities),
                "fm_text": fm_text,
                "body": body,
                "meta": {"type": "skill", "path": r, "slug": fm["slug"], "title": fm["title"]},
                "line": f"[skill] {fm['slug']} — {fm['title']}  [{r}]",
            })

    if "guidance" in allowed_types:
        for p, fm, body in scan_records(root, "knowledge/guidance", "guidance"):
            if not is_active_head(fm):
                continue
            r = rel_path(p, root)
            gd_ents = set(fm.get("entities") or [])
            fm_text = f"{fm.get('slug')} {fm.get('title')} {fm.get('domain')} {fm.get('policy_rule')}"
            corpus.append({
                "path": r,
                "entity_exact": bool(gd_ents & resolved_entities),
                "entity_partial": bool(gd_ents & token_resolved_entities),
                "fm_text": fm_text,
                "body": body,
                "meta": {"type": "guidance", "path": r, "slug": fm["slug"], "title": fm["title"]},
                "line": f"[guidance] {fm['slug']} — {fm['policy_rule']}  [{r}]",
            })

    if "decision" in allowed_types:
        for p, fm, body in scan_records(root, "knowledge/decisions", "decision"):
            if fm.get("status") != "accepted":
                continue
            r = rel_path(p, root)
            dc_ents = set(fm.get("entities") or [])
            fm_text = f"{fm.get('id')} {fm.get('title')} {fm.get('domain')} {fm.get('summary')}"
            corpus.append({
                "path": r,
                "entity_exact": bool(dc_ents & resolved_entities),
                "entity_partial": bool(dc_ents & token_resolved_entities),
                "fm_text": fm_text,
                "body": body,
                "meta": {"type": "decision", "path": r, "id": fm["id"], "title": fm["title"]},
                "line": f"[decision] {fm['id']} — {fm['title']}  [{r}]",
            })

    if "note" in allowed_types:
        for p, fm, body in scan_records(root, "knowledge/notes", "note"):
            r = rel_path(p, root)
            nt_ents = set(fm.get("entities") or [])
            fm_text = f"{fm.get('id', p.stem)} {fm.get('title', p.stem)} {fm.get('kind', '')} {' '.join(str(t) for t in (fm.get('tags') or []))}"
            corpus.append({
                "path": r,
                "entity_exact": bool(nt_ents & resolved_entities),
                "entity_partial": bool(nt_ents & token_resolved_entities),
                "fm_text": fm_text,
                "body": body,
                "meta": {"type": "note", "path": r, "title": fm.get("title", p.stem)},
                "line": f"[note] {fm.get('title', p.stem)}  [{r}]",
            })

    if "source" in allowed_types:
        src_dir = root / "sources"
        if src_dir.is_dir():
            for p in sorted(src_dir.rglob("*.md")):
                if p.name.lower() == "readme.md":
                    continue
                r = rel_path(p, root)
                body = p.read_text(encoding="utf-8", errors="replace")
                corpus.append({
                    "path": r,
                    "entity_exact": False,
                    "entity_partial": False,
                    "fm_text": p.stem.replace("-", " "),
                    "body": body,
                    "meta": {"type": "source", "path": r, "title": p.stem},
                    "line": f"[source] {p.stem}  [{r}]",
                })

    fm_token_lists = [tokenize_stemmed(c["fm_text"]) for c in corpus]
    body_token_lists = [tokenize_stemmed(c["body"]) for c in corpus]
    fm_bm25 = _bm25_scores(q_tokens, fm_token_lists)
    body_bm25 = _bm25_scores(q_tokens, body_token_lists)

    unique_q = list(dict.fromkeys(q_tokens))
    scored: list[tuple[int, float, str, dict[str, Any], str]] = []
    for idx, c in enumerate(corpus):
        folded_fm = fold_text(c["fm_text"])
        folded_body = fold_text(c["body"])
        doc_tok_set = set(fm_token_lists[idx]) | set(body_token_lists[idx])
        matched_q = sum(1 for t in unique_q if t in doc_tok_set)
        all_matched = bool(unique_q) and matched_q == len(unique_q)

        # Tier preserves deterministic precedence for exact entity & phrase hits while enabling BM25 multi-term ranking
        exact_phrase_fm = needle in folded_fm
        exact_phrase_body = needle in folded_body
        bm25_total = 2.2 * fm_bm25[idx] + 1.0 * body_bm25[idx]

        tier: int | None = None
        if c["entity_exact"]:
            tier = 0
        elif exact_phrase_fm:
            tier = 1
        elif all_matched and c["entity_partial"]:
            tier = 1
            bm25_total += 4.0
        elif all_matched:
            tier = 2
            bm25_total += 3.0
        elif exact_phrase_body:
            tier = 2
        elif len(unique_q) > 1 and matched_q >= max(2, math.ceil(len(unique_q) * 0.6)):
            tier = 3

        if tier is not None:
            meta = dict(c["meta"], score=round(bm25_total, 4))
            scored.append((tier, -bm25_total, c["path"], meta, c["line"]))

    scored.sort(key=lambda item: (item[0], item[1], item[2]))
    if limit is not None and limit > 0:
        scored = scored[:limit]
    if not scored:
        return f"No records found matching {term!r}\n", [], diags
    return "\n".join(item[4] for item in scored) + "\n", [item[3] for item in scored], diags


def query_graph(
    root: Path,
    node: str,
    *,
    depth: int = 1,
    target_node: str | None = None,
    as_of: str | None = None,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    diags = _warn_if_index_stale(root, "_generated/indexes/graph.md")
    resolved = resolve_entity(root, node)
    canonical_node = resolved[0] if len(resolved) == 1 else node
    as_of_date = parse_date(as_of) if as_of else None
    edges = compute_graph_edges(root, as_of=as_of_date)
    max_depth = max(1, int(depth))

    if target_node:
        t_res = resolve_entity(root, target_node)
        canonical_target = t_res[0] if len(t_res) == 1 else target_node
        adj: dict[str, list[tuple[str, str, str, str, str]]] = {}
        for src, rel_name, dst, ev in edges:
            adj.setdefault(src, []).append((dst, src, rel_name, dst, ev))
            adj.setdefault(dst, []).append((src, src, rel_name, dst, ev))
        queue: deque[tuple[str, list[tuple[str, str, str, str]]]] = deque([(canonical_node, [])])
        visited = {canonical_node}
        found_path: list[tuple[str, str, str, str]] | None = None
        while queue:
            curr, path = queue.popleft()
            if curr == canonical_target and path:
                found_path = path
                break
            if len(path) >= max_depth:
                continue
            for nxt, esrc, erel, edst, eev in adj.get(curr, []):
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, [*path, (esrc, erel, edst, eev)]))
        if not found_path:
            return f"No path found between {canonical_node!r} and {canonical_target!r} within depth {max_depth}\n", [], diags
        out_edges: list[dict[str, Any]] = []
        lines: list[str] = []
        for hop, (src, rel_name, dst, ev) in enumerate(found_path, 1):
            out_edges.append({"hop": hop, "from": src, "relation": rel_name, "to": dst, "evidence": ev})
            lines.append(f"[hop {hop}] {src} --[{rel_name}]--> {dst}  [{ev}]")
        return "\n".join(lines) + "\n", out_edges, diags

    # Single-hop or multi-hop BFS neighborhood
    if max_depth == 1:
        neighbors: list[dict[str, Any]] = []
        lines = []
        for src, rel_name, dst, ev in edges:
            if src == canonical_node:
                neighbors.append({"direction": "out", "relation": rel_name, "neighbor": dst, "evidence": ev, "hop": 1, "from": src, "to": dst})
                lines.append(f"{src} --[{rel_name}]--> {dst}  [{ev}]")
            elif dst == canonical_node:
                neighbors.append({"direction": "in", "relation": rel_name, "neighbor": src, "evidence": ev, "hop": 1, "from": src, "to": dst})
                lines.append(f"{src} --[{rel_name}]--> {dst}  [{ev}]")
        if not lines:
            return f"No graph relationships found for {canonical_node!r}\n", [], diags
        return "\n".join(lines) + "\n", neighbors, diags

    adj_multi: dict[str, list[tuple[str, str, str, str, str]]] = {}
    for src, rel_name, dst, ev in edges:
        adj_multi.setdefault(src, []).append((dst, src, rel_name, dst, ev))
        adj_multi.setdefault(dst, []).append((src, src, rel_name, dst, ev))
    frontier = {canonical_node}
    seen_nodes = {canonical_node}
    seen_edges: set[tuple[str, str, str, str]] = set()
    collected: list[dict[str, Any]] = []
    lines = []
    for hop in range(1, max_depth + 1):
        next_frontier: set[str] = set()
        for curr in sorted(frontier):
            for nxt, src, rel_name, dst, ev in adj_multi.get(curr, []):
                ekey = (src, rel_name, dst, ev)
                if ekey not in seen_edges:
                    seen_edges.add(ekey)
                    direction = "out" if src == curr else "in"
                    collected.append({
                        "hop": hop,
                        "direction": direction,
                        "relation": rel_name,
                        "neighbor": nxt,
                        "from": src,
                        "to": dst,
                        "evidence": ev,
                    })
                    lines.append(f"[hop {hop}] {src} --[{rel_name}]--> {dst}  [{ev}]")
                if nxt not in seen_nodes:
                    seen_nodes.add(nxt)
                    next_frontier.add(nxt)
        frontier = next_frontier
        if not frontier:
            break
    if not lines:
        return f"No graph relationships found for {canonical_node!r}\n", [], diags
    return "\n".join(lines) + "\n", collected, diags
