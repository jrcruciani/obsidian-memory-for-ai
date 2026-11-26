"""Disposable hybrid search index (SQLite FTS5 + optional local embeddings + RRF).

The SQLite index lives under ``_generated/indexes/search.sqlite`` as a purely
derived, regenerable read model. Plain Markdown + Git remain the sole truth
source; deleting ``search.sqlite`` loses zero canonical data.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import struct
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .bootstrap import render_scalar_inline
from .locking import vault_write_lock
from .model import (
    fold_text,
    is_active_head,
    is_fact_visible,
    load_entities,
    rel_path,
    resolve_entity,
    scan_records,
    today,
)
from .query import _stem_token, query_search, tokenize_text

EmbedFn = Callable[[str], list[float]]
INDEX_REL = "_generated/indexes/search.sqlite"


def ollama_embed_fn(
    *,
    model: str | None = None,
    base_url: str | None = None,
    timeout_s: float = 10.0,
) -> EmbedFn:
    """Create a local Ollama embedding callable using stdlib HTTP only."""
    emb_model = model or os.environ.get("KF_EMBED_MODEL", "nomic-embed-text")
    url_base = (base_url or os.environ.get("KF_OLLAMA_URL", "http://127.0.0.1:11434")).rstrip("/")

    def _embed(text: str) -> list[float]:
        payload = json.dumps({"model": emb_model, "input": text[:4000]}).encode("utf-8")
        req = urllib.request.Request(
            f"{url_base}/api/embed",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                embs = data.get("embeddings")
                if isinstance(embs, list) and embs and isinstance(embs[0], list):
                    return [float(x) for x in embs[0]]
                emb = data.get("embedding")
                if isinstance(emb, list):
                    return [float(x) for x in emb]
        except Exception:
            # Fallback to legacy Ollama /api/embeddings endpoint
            legacy_payload = json.dumps({"model": emb_model, "prompt": text[:4000]}).encode("utf-8")
            legacy_req = urllib.request.Request(
                f"{url_base}/api/embeddings",
                data=legacy_payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(legacy_req, timeout=timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                emb = data.get("embedding")
                if isinstance(emb, list):
                    return [float(x) for x in emb]
        return []

    return _embed


def _pack_vector(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def _unpack_vector(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 1e-12 or nb <= 1e-12:
        return 0.0
    return dot / (na * nb)


def _collect_indexable_documents(
    root: Path,
    *,
    include_notes: bool = True,
    include_sources: bool = True,
    include_events: bool = True,
) -> list[dict[str, Any]]:
    entities_map = load_entities(root)
    docs: list[dict[str, Any]] = []

    for p, fm, body in scan_records(root, "knowledge/facts", "fact"):
        if not is_fact_visible(fm):
            continue
        r = rel_path(p, root)
        ent = str(fm.get("entity", ""))
        ent_info = entities_map.get(ent, {})
        aliases = " ".join([ent, str(ent_info.get("display", "")), *(ent_info.get("aliases") or [])])
        val = render_scalar_inline(fm.get("value"))
        docs.append({
            "path": r,
            "record_type": "fact",
            "title": f"{ent}/{fm['predicate']} = {val}",
            "entities": [ent],
            "metadata_text": f"{ent} {fm.get('predicate')} {val} {aliases}",
            "body_text": body.strip(),
        })

    for p, fm, body in scan_records(root, "knowledge/skills", "skill"):
        if not is_active_head(fm):
            continue
        r = rel_path(p, root)
        meta = " ".join([
            str(fm.get("slug", "")),
            str(fm.get("title", "")),
            str(fm.get("domain", "")),
            *(str(t) for t in (fm.get("triggers") or [])),
            *(str(x) for x in (fm.get("outputs") or [])),
        ])
        docs.append({
            "path": r,
            "record_type": "skill",
            "title": f"{fm['slug']} — {fm['title']}",
            "entities": list(fm.get("entities") or []),
            "metadata_text": meta,
            "body_text": body.strip(),
        })

    for p, fm, body in scan_records(root, "knowledge/guidance", "guidance"):
        if not is_active_head(fm):
            continue
        r = rel_path(p, root)
        meta = f"{fm.get('slug')} {fm.get('title')} {fm.get('domain')} {fm.get('scope')} {fm.get('policy_rule')}"
        docs.append({
            "path": r,
            "record_type": "guidance",
            "title": f"{fm['slug']} — {fm['policy_rule']}",
            "entities": list(fm.get("entities") or []),
            "metadata_text": meta,
            "body_text": body.strip(),
        })

    for p, fm, body in scan_records(root, "knowledge/decisions", "decision"):
        if fm.get("status") != "accepted":
            continue
        r = rel_path(p, root)
        meta = f"{fm.get('id')} {fm.get('title')} {fm.get('domain')} {fm.get('summary')}"
        docs.append({
            "path": r,
            "record_type": "decision",
            "title": f"{fm['id']} — {fm['title']}",
            "entities": list(fm.get("entities") or []),
            "metadata_text": meta,
            "body_text": body.strip(),
        })

    if include_events:
        for p, fm, body in scan_records(root, "knowledge/events", "event"):
            r = rel_path(p, root)
            meta = f"{fm.get('id')} {fm.get('occurred_at')} {fm.get('summary')} {' '.join(str(t) for t in (fm.get('tags') or []))}"
            docs.append({
                "path": r,
                "record_type": "event",
                "title": f"{fm.get('occurred_at', '')[:10]} — {fm.get('summary', p.stem)}",
                "entities": list(fm.get("entities") or []),
                "metadata_text": meta,
                "body_text": body.strip(),
            })

    if include_notes:
        for p, fm, body in scan_records(root, "knowledge/notes", "note"):
            r = rel_path(p, root)
            meta = f"{fm.get('id', p.stem)} {fm.get('title', p.stem)} {fm.get('kind', '')} {' '.join(str(t) for t in (fm.get('tags') or []))}"
            docs.append({
                "path": r,
                "record_type": "note",
                "title": str(fm.get("title", p.stem)),
                "entities": list(fm.get("entities") or []),
                "metadata_text": meta,
                "body_text": body.strip(),
            })

    if include_sources:
        src_dir = root / "sources"
        if src_dir.is_dir():
            for p in sorted(src_dir.rglob("*.md")):
                if p.name.lower() == "readme.md":
                    continue
                r = rel_path(p, root)
                body = p.read_text(encoding="utf-8", errors="replace").strip()
                docs.append({
                    "path": r,
                    "record_type": "source",
                    "title": p.stem,
                    "entities": [],
                    "metadata_text": p.stem.replace("-", " "),
                    "body_text": body,
                })

    return docs


def hybrid_index_digest(
    root: Path,
    *,
    include_notes: bool = True,
    include_sources: bool = True,
    include_events: bool = True,
) -> str:
    """Compute a fast, date-independent digest for `search.sqlite` staleness detection.

    Uses file metadata ``(rel_path, size, mtime_ns)`` on indexable Markdown files
    only (never reading binary files in ``sources/``) plus active temporal fact
    visibility, avoiding unnecessary midnight rebuilds when no fact boundary changed.
    """
    hasher = hashlib.sha256()
    hasher.update(f"kf-hybrid-v5.1.1:{int(include_notes)}:{int(include_sources)}:{int(include_events)}\n".encode("utf-8"))
    ref = today()

    # Entities registry + living Markdown planes
    ent_path = root / "knowledge/entities.md"
    if ent_path.is_file():
        st = ent_path.stat()
        hasher.update(f"knowledge/entities.md:{st.st_size}:{st.st_mtime_ns}\n".encode("utf-8"))

    folders = ["knowledge/facts", "knowledge/skills", "knowledge/guidance", "knowledge/decisions"]
    if include_events:
        folders.append("knowledge/events")
    if include_notes:
        folders.append("knowledge/notes")

    for folder in folders:
        base = root / folder
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.md")):
            if p.name.startswith("."):
                continue
            st = p.stat()
            hasher.update(f"{rel_path(p, root)}:{st.st_size}:{st.st_mtime_ns}\n".encode("utf-8"))

    # Capture active fact visibility set so expiring/activating facts invalidate the index on boundary dates
    for p, fm, _ in scan_records(root, "knowledge/facts", "fact"):
        if is_fact_visible(fm, ref):
            hasher.update(f"visible-fact:{rel_path(p, root)}\n".encode("utf-8"))

    if include_sources:
        src_dir = root / "sources"
        if src_dir.is_dir():
            for p in sorted(src_dir.rglob("*.md")):
                if p.name.startswith(".") or p.name.lower() == "readme.md":
                    continue
                st = p.stat()
                hasher.update(f"{rel_path(p, root)}:{st.st_size}:{st.st_mtime_ns}\n".encode("utf-8"))

    return "sha256:" + hasher.hexdigest()


def build_hybrid_index(
    root: Path,
    *,
    use_embeddings: bool = False,
    embed_fn: EmbedFn | None = None,
    include_notes: bool = True,
    include_sources: bool = True,
    include_events: bool = True,
) -> dict[str, Any]:
    """Build disposable SQLite FTS5 (+ optional embedding) index under `_generated/indexes/`."""
    with vault_write_lock(root):
        ref = today()
        digest = hybrid_index_digest(
            root,
            include_notes=include_notes,
            include_sources=include_sources,
            include_events=include_events,
        )
        docs = _collect_indexable_documents(
            root,
            include_notes=include_notes,
            include_sources=include_sources,
            include_events=include_events,
        )
        db_path = root / INDEX_REL
        db_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = db_path.with_suffix(".sqlite.tmp")
        if tmp_path.exists():
            tmp_path.unlink()

        resolved_embed: EmbedFn | None = embed_fn
        if use_embeddings and resolved_embed is None:
            resolved_embed = ollama_embed_fn()

        embedded_count = 0
        embed_warnings: list[str] = []

        conn = sqlite3.connect(str(tmp_path))
        try:
            conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute(
                """
                CREATE TABLE docs (
                    doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    record_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    entities TEXT NOT NULL,
                    metadata_text TEXT NOT NULL,
                    body_text TEXT NOT NULL,
                    embedding BLOB
                )
                """
            )
            conn.execute(
                """
                CREATE VIRTUAL TABLE docs_fts USING fts5(
                    title,
                    metadata_text,
                    body_text,
                    content='docs',
                    content_rowid='doc_id',
                    tokenize='unicode61 remove_diacritics 2'
                )
                """
            )

            embed_active = bool(use_embeddings and resolved_embed is not None)
            for doc in docs:
                emb_blob: bytes | None = None
                if embed_active and resolved_embed is not None:
                    try:
                        vec = resolved_embed(f"{doc['title']}\n{doc['metadata_text']}\n{doc['body_text']}")
                        if vec:
                            emb_blob = _pack_vector(vec)
                            embedded_count += 1
                    except Exception as exc:
                        embed_warnings.append(f"embeddings unavailable ({exc}); indexed FTS5 only")
                        embed_active = False

                cur = conn.execute(
                    """
                    INSERT INTO docs (path, record_type, title, entities, metadata_text, body_text, embedding)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        doc["path"],
                        doc["record_type"],
                        doc["title"],
                        json.dumps(doc["entities"]),
                        doc["metadata_text"],
                        doc["body_text"],
                        emb_blob,
                    ),
                )
                conn.execute(
                    "INSERT INTO docs_fts(rowid, title, metadata_text, body_text) VALUES (?, ?, ?, ?)",
                    (cur.lastrowid, doc["title"], doc["metadata_text"], doc["body_text"]),
                )

            conn.execute("INSERT INTO meta(key, value) VALUES (?, ?)", ("source_digest", digest))
            conn.execute("INSERT INTO meta(key, value) VALUES (?, ?)", ("ref_date", ref.isoformat()))
            conn.execute("INSERT INTO meta(key, value) VALUES (?, ?)", ("embedded", str(embedded_count)))
            conn.commit()
        finally:
            conn.close()

        os.replace(tmp_path, db_path)
        return {
            "path": INDEX_REL,
            "source_digest": digest,
            "documents": len(docs),
            "embedded": embedded_count,
            "warnings": embed_warnings,
        }


def _build_fts_queries(term: str) -> list[str]:
    raw_tokens = [t for t in tokenize_text(term) if t]
    if not raw_tokens:
        return []
    expanded = []
    for tok in raw_tokens:
        stem = _stem_token(tok)
        if len(stem) >= 4:
            expanded.append(f"{stem}*")
        else:
            expanded.append(tok)
    queries: list[str] = []
    if len(expanded) > 1:
        queries.append(" AND ".join(expanded))
    queries.append(" OR ".join(expanded))
    return queries


def hybrid_search(
    root: Path,
    term: str,
    *,
    types: set[str] | None = None,
    include_notes: bool = True,
    include_sources: bool = True,
    use_embeddings: bool = False,
    embed_fn: EmbedFn | None = None,
    auto_build: bool = True,
    fallback_bm25: bool = False,
    limit: int = 10,
    rrf_k: int = 60,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Query the disposable SQLite FTS5 + embedding index using Reciprocal Rank Fusion."""
    diags: list[str] = []
    db_path = root / INDEX_REL
    current_digest = hybrid_index_digest(root)

    needs_build = not db_path.is_file()
    if not needs_build:
        try:
            conn_chk = sqlite3.connect(str(db_path))
            row = conn_chk.execute("SELECT value FROM meta WHERE key='source_digest'").fetchone()
            conn_chk.close()
            if not row or row[0] != current_digest:
                if auto_build or fallback_bm25:
                    needs_build = True
                else:
                    diags.append(f"WARN: {INDEX_REL} is stale (run `kf.py index build`)")
        except sqlite3.Error:
            needs_build = True

    if needs_build:
        if auto_build:
            info = build_hybrid_index(root, use_embeddings=use_embeddings, embed_fn=embed_fn)
            diags.extend(info.get("warnings") or [])
        elif fallback_bm25:
            txt, rows, bm25_diags = query_search(
                root,
                term,
                types=types,
                include_notes=include_notes,
                include_sources=include_sources,
                limit=limit,
            )
            diags.extend(bm25_diags)
            return txt, rows, diags
        else:
            return f"Hybrid index missing at {INDEX_REL}; run `kf.py index build`.\n", [], diags

    if types is not None:
        allowed_types: set[str] = set(types)
    else:
        allowed_types = {"fact", "skill", "guidance", "decision", "event"}
        if include_notes:
            allowed_types.add("note")
        if include_sources:
            allowed_types.add("source")
    if not include_notes:
        allowed_types.discard("note")
    if not include_sources:
        allowed_types.discard("source")
    resolved_entities = set(resolve_entity(root, term))
    for tok in tokenize_text(term):
        if len(tok) >= 3:
            resolved_entities.update(resolve_entity(root, tok))

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # 1. FTS5 BM25 ranking
        fts_ranks: dict[int, int] = {}
        fts_bm25: dict[int, float] = {}
        rank_counter = 1
        for fts_q in _build_fts_queries(term):
            try:
                rows = conn.execute(
                    """
                    SELECT d.doc_id, d.record_type, bm25(docs_fts, 4.0, 2.5, 1.0) AS score
                    FROM docs_fts
                    JOIN docs d ON d.doc_id = docs_fts.rowid
                    WHERE docs_fts MATCH ?
                    ORDER BY score ASC
                    LIMIT ?
                    """,
                    (fts_q, max(limit * 4, 40)),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            for row in rows:
                if allowed_types and row["record_type"] not in allowed_types:
                    continue
                did = int(row["doc_id"])
                if did not in fts_ranks:
                    fts_ranks[did] = rank_counter
                    fts_bm25[did] = -float(row["score"])
                    rank_counter += 1

        # 2. Optional semantic embedding cosine ranking
        sem_ranks: dict[int, int] = {}
        sem_scores: dict[int, float] = {}
        if use_embeddings:
            q_embed_fn = embed_fn or ollama_embed_fn()
            q_vec: list[float] = []
            try:
                q_vec = q_embed_fn(term)
            except Exception as exc:
                diags.append(f"WARN: semantic query embedding skipped ({exc}); using FTS5 only")
            if q_vec:
                emb_rows = conn.execute(
                    "SELECT doc_id, record_type, embedding FROM docs WHERE embedding IS NOT NULL"
                ).fetchall()
                scored_sem: list[tuple[float, int]] = []
                for row in emb_rows:
                    if allowed_types and row["record_type"] not in allowed_types:
                        continue
                    sim = _cosine_similarity(q_vec, _unpack_vector(row["embedding"]))
                    if sim > 0.2:
                        scored_sem.append((sim, int(row["doc_id"])))
                scored_sem.sort(key=lambda x: (-x[0], x[1]))
                for idx, (sim, did) in enumerate(scored_sem[: max(limit * 4, 40)], 1):
                    sem_ranks[did] = idx
                    sem_scores[did] = sim

        # 3. Entity boost ranking
        ent_ranks: dict[int, int] = {}
        if resolved_entities:
            all_docs = conn.execute("SELECT doc_id, record_type, entities FROM docs").fetchall()
            e_rank = 1
            for row in all_docs:
                if allowed_types and row["record_type"] not in allowed_types:
                    continue
                doc_ents = set(json.loads(row["entities"] or "[]"))
                if doc_ents & resolved_entities:
                    ent_ranks[int(row["doc_id"])] = e_rank
                    e_rank += 1

        candidate_ids = set(fts_ranks) | set(sem_ranks) | set(ent_ranks)
        if not candidate_ids:
            return f"No records found matching {term!r}\n", [], diags

        # 4. Reciprocal Rank Fusion
        fused: list[tuple[float, str, dict[str, Any], str]] = []
        placeholders = ",".join("?" for _ in candidate_ids)
        doc_rows = conn.execute(
            f"SELECT doc_id, path, record_type, title, entities FROM docs WHERE doc_id IN ({placeholders})",
            tuple(candidate_ids),
        ).fetchall()
        for row in doc_rows:
            did = int(row["doc_id"])
            rrf = 0.0
            if did in fts_ranks:
                rrf += 1.0 / (rrf_k + fts_ranks[did])
            if did in sem_ranks:
                rrf += 1.0 / (rrf_k + sem_ranks[did])
            if did in ent_ranks:
                rrf += 0.8 / (rrf_k + ent_ranks[did])
            item = {
                "type": row["record_type"],
                "path": row["path"],
                "title": row["title"],
                "entities": json.loads(row["entities"] or "[]"),
                "rrf_score": round(rrf, 6),
                "fts_score": round(fts_bm25.get(did, 0.0), 4),
                "semantic_score": round(sem_scores.get(did, 0.0), 4),
            }
            line = f"[{row['record_type']}] {row['title']}  [{row['path']}] (rrf={rrf:.4f})"
            fused.append((rrf, row["path"], item, line))

        fused.sort(key=lambda x: (-x[0], x[1]))
        fused = fused[: max(1, limit)]
        return "\n".join(x[3] for x in fused) + "\n", [x[2] for x in fused], diags
    finally:
        conn.close()
