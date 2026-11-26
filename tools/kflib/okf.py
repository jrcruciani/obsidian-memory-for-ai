"""Google Cloud Open Knowledge Format (OKF v0.2) export & forgiving import.

- Export: materializes living knowledge into a portable OKF v0.2 directory
  with `type`, `title`, `sources`, `generated`, `verified`, `status`,
  `stale_after`, `index.md`, and `log.md`.
- Import: follows OKF's Forgiving Reader Rule — accepts imperfect Markdown
  documents (missing optional keys, unknown types, broken links), stores them
  immutably under `sources/okf-imports/`, and emits curation `signals` so
  external content never directly mutates canonical `knowledge/`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any

from .bootstrap import render_scalar_inline
from .capture import capture_signal
from .locking import vault_write_lock
from .model import (
    atomic_write_text,
    format_markdown,
    is_active_head,
    is_fact_visible,
    iso_utc,
    load_entities,
    load_manifest,
    parse_date,
    rel_path,
    scan_records,
    slugify,
    split_frontmatter_text,
    today,
    utc_now,
)
from .personal import default_personal_actor


def _compute_stale_after(fm: dict[str, Any], stale_days: int) -> str | None:
    if fm.get("review_after"):
        return f"{fm['review_after']}T00:00:00Z"
    base = parse_date(fm.get("last_confirmed"))
    if base:
        return f"{(base + dt.timedelta(days=stale_days)).isoformat()}T00:00:00Z"
    return None


def _verified_block(fm: dict[str, Any]) -> dict[str, str]:
    trust = str(fm.get("trust", "agent"))
    prefix = "human" if trust == "owner" else "agent"
    at = str(fm.get("last_confirmed") or fm.get("observed_at") or iso_utc(utc_now()))
    if len(at) == 10:
        at = f"{at}T00:00:00Z"
    return {"by": f"{prefix}:{trust}", "at": at}


def export_okf_bundle(root: Path, out_dir: Path) -> dict[str, Any]:
    """Export living Knowledge Factory records into a portable OKF v0.2 bundle."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(root)
    stale_days = int((manifest.get("settings") or {}).get("stale_after_days", 180))
    now_iso = iso_utc(utc_now())
    entities = load_entities(root)

    exported: list[tuple[str, str, str]] = []  # (rel_out, okf_type, title)

    # 1. Group active facts by entity into OKF entity pages
    facts_by_entity: dict[str, list[tuple[str, dict[str, Any], str]]] = defaultdict(list)
    for p, fm, body in scan_records(root, "knowledge/facts", "fact"):
        if is_fact_visible(fm):
            facts_by_entity[str(fm["entity"])].append((rel_path(p, root), fm, body))

    for eid, rows in sorted(facts_by_entity.items()):
        ent_info = entities.get(eid, {})
        display = str(ent_info.get("display", eid))
        ekind = str(ent_info.get("kind", "concept"))
        sources_list: list[str] = []
        latest_conf: str | None = None
        trust = "owner"
        lines = [f"# {display}", "", "## Facts", ""]
        for r, fm, _ in sorted(rows, key=lambda item: str(item[1].get("predicate", ""))):
            val = render_scalar_inline(fm.get("value"))
            vf = fm.get("valid_from") or "open"
            lines.append(f"- **{fm['predicate']}**: {val} *(since {vf}, trust: {fm.get('trust')})*")
            sources_list.append(r)
            for df in fm.get("derived_from") or []:
                if str(df) not in sources_list:
                    sources_list.append(str(df))
            if fm.get("trust") != "owner":
                trust = str(fm.get("trust", "agent"))
            lc = fm.get("last_confirmed")
            if isinstance(lc, str) and (latest_conf is None or lc > latest_conf):
                latest_conf = lc

        synth_fm = {"trust": trust, "last_confirmed": latest_conf}
        okf_fm: dict[str, Any] = {
            "type": f"Entity/{ekind}",
            "title": display,
            "status": "stable",
            "sources": sources_list,
            "generated": {"by": "knowledge-factory/v5-personal", "at": now_iso},
            "verified": _verified_block(synth_fm),
            "stale_after": _compute_stale_after(synth_fm, stale_days),
        }
        rel_out = f"entities/{eid}.md"
        atomic_write_text(out_dir / rel_out, format_markdown(okf_fm, "\n".join(lines)))
        exported.append((rel_out, okf_fm["type"], display))

    # 2. Export active skills, guidance, decisions, and notes
    for folder, rtype, out_prefix, okf_type in (
        ("knowledge/skills", "skill", "skills", "Procedure"),
        ("knowledge/guidance", "guidance", "guidance", "Guardrail"),
        ("knowledge/decisions", "decision", "decisions", "Decision"),
        ("knowledge/notes", "note", "notes", "Note"),
    ):
        for p, fm, body in scan_records(root, folder, rtype):
            if rtype in {"skill", "guidance"} and not is_active_head(fm):
                continue
            if rtype == "decision" and fm.get("status") != "accepted":
                continue
            r = rel_path(p, root)
            slug = str(fm.get("slug") or fm.get("id") or p.stem)
            title = str(fm.get("title") or slug)
            srcs = [r, *(str(x) for x in (fm.get("derived_from") or []))]
            okf_fm = {
                "type": okf_type,
                "title": title,
                "status": "draft" if rtype == "note" else "stable",
                "sources": srcs,
                "generated": {"by": "knowledge-factory/v5-personal", "at": now_iso},
                "verified": _verified_block(fm),
                "stale_after": _compute_stale_after(fm, stale_days),
            }
            rel_out = f"{out_prefix}/{slug}.md"
            atomic_write_text(out_dir / rel_out, format_markdown(okf_fm, body.strip() or f"# {title}"))
            exported.append((rel_out, okf_type, title))

    # 3. Write OKF index.md and log.md
    idx_lines = ["# Knowledge Bundle Index (OKF v0.2)", "", f"Exported at `{now_iso}`.", ""]
    for rel_out, okf_type, title in sorted(exported):
        idx_lines.append(f"- [{title}]({rel_out}) — `{okf_type}`")
    atomic_write_text(out_dir / "index.md", "\n".join(idx_lines) + "\n")

    log_lines = [
        "# Knowledge Bundle Log",
        "",
        f"- `{now_iso}`: Exported {len(exported)} OKF v0.2 concept pages from Knowledge Factory vault (`ref_date={today().isoformat()}`).",
    ]
    atomic_write_text(out_dir / "log.md", "\n".join(log_lines) + "\n")

    return {
        "out_dir": str(out_dir),
        "okf_version": "0.2",
        "exported_files": len(exported),
        "files": [x[0] for x in sorted(exported)],
    }


def import_okf_bundle(
    root: Path,
    in_dir: Path,
    *,
    emitted_by: str | None = None,
) -> dict[str, Any]:
    """Forgivingly import an OKF bundle into immutable `sources/okf-imports/` + curation signals.

    Never rejects missing optional keys, unknown types, extra frontmatter fields,
    or broken links (OKF Forgiving Reader Rule), and never bypasses review into `knowledge/`.
    """
    if not in_dir.is_dir():
        raise ValueError(f"OKF bundle directory does not exist: {in_dir}")

    actor = emitted_by or default_personal_actor(root)
    stamp = today().isoformat()
    imported_sources: list[str] = []
    emitted_signals: list[str] = []
    skipped_unparseable: list[str] = []

    with vault_write_lock(root):
        for md_path in sorted(in_dir.rglob("*.md")):
            if md_path.name.lower() in {"index.md", "log.md", "readme.md"}:
                continue
            raw = md_path.read_text(encoding="utf-8", errors="replace")
            try:
                fm, _ = split_frontmatter_text(raw, source=str(md_path))
            except Exception:
                # Forgiving reader still imports raw text as an untyped source if frontmatter is absent/broken
                fm = {}
            rel_in = md_path.relative_to(in_dir).as_posix()
            slug = slugify(rel_in.removesuffix(".md").replace("/", "-"), 48)
            h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
            dst_rel = f"sources/okf-imports/{stamp}-{slug}-{h}.md"
            atomic_write_text(root / dst_rel, raw)
            imported_sources.append(dst_rel)

            title = str(fm.get("title") or md_path.stem)
            okf_type = str(fm.get("type") or "untyped")
            sig = capture_signal(
                root,
                emitted_by=actor,
                kind="observation",
                severity="low",
                target_namespace="facts",
                summary=f"Review imported OKF ({okf_type}) concept: {title}",
                evidence=[dst_rel],
                idempotency_key=f"okf-import-{h}",
            )
            emitted_signals.append(sig["id"])

    return {
        "imported_sources": len(imported_sources),
        "emitted_signals": len(emitted_signals),
        "source_paths": imported_sources,
        "signal_ids": emitted_signals,
        "skipped": skipped_unparseable,
    }
