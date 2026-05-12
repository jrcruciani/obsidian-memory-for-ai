#!/usr/bin/env python3
"""Regenerate deterministic v3 materialized views."""

from __future__ import annotations

import datetime as dt
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from lint import FRONTMATTER_RE, WIKILINK_RE, fact_interval, markdown_files, rel, split_frontmatter


def today() -> dt.date:
    import os

    return dt.date.fromisoformat(os.environ.get("MEMORY_TODAY", dt.date.today().isoformat()))


def frontmatter(path: Path) -> dict[str, Any]:
    data, _ = split_frontmatter(path)
    return data


def facts(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    rows = []
    for path in sorted((root / "memory/facts").rglob("*.md")):
        data = frontmatter(path)
        if data.get("type") == "fact":
            rows.append((path, data))
    return rows


def events(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    rows = []
    for path in sorted((root / "memory/events").rglob("*.md")):
        data = frontmatter(path)
        if data.get("type") == "event":
            rows.append((path, data))
    return rows


def records(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    rows = []
    for path in markdown_files(root):
        if "/_views/" in path.as_posix():
            continue
        data = frontmatter(path)
        if data.get("type"):
            rows.append((path, data))
    return rows


def operations(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    rows = []
    for base in (root / "memory/_inbox", root / "memory/_ops"):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.md")):
            data = frontmatter(path)
            if data.get("type") == "operation":
                rows.append((path, data))
    return rows


def claims(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    rows = []
    base = root / "memory/_claims"
    if not base.exists():
        return rows
    for path in sorted(base.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if data.get("type") == "claim":
            rows.append((path, data))
    return rows


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def render_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return "`" + yaml.safe_dump(value, sort_keys=True).strip().replace("\n", " ") + "`"
    return str(value)


def build_by_entity(root: Path, rows: list[tuple[Path, dict[str, Any]]]) -> None:
    grouped: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    for path, data in rows:
        grouped.setdefault(data["entity"], []).append((path, data))
    for entity, items in sorted(grouped.items()):
        lines = [f"# Facts — {entity}", ""]
        for path, data in sorted(items, key=lambda item: (item[1]["predicate"], rel(item[0], root))):
            valid = f"{data.get('valid_from') or 'unknown'} → {data.get('valid_to') or 'present'}"
            lines.append(f"- **{data['predicate']}**: {render_value(data.get('value'))} ({valid}) — `{rel(path, root)}`")
        write(root / "memory/_views/by-entity" / f"{entity}.md", "\n".join(lines))


def build_timeline(root: Path, rows: list[tuple[Path, dict[str, Any]]]) -> None:
    lines = ["# Timeline", ""]
    for path, data in sorted(rows, key=lambda item: (str(item[1]["occurred_at"]), rel(item[0], root)), reverse=True):
        entities = ", ".join(data.get("entities", []) or [])
        lines.append(f"- **{data['occurred_at']}** — {data['summary']} ({entities}) — `{rel(path, root)}`")
    write(root / "memory/_views/timeline.md", "\n".join(lines))


def build_contradictions(root: Path, rows: list[tuple[Path, dict[str, Any]]]) -> None:
    lines = ["# Contradictions", ""]
    found = False
    for i, (path_a, data_a) in enumerate(rows):
        for path_b, data_b in rows[i + 1 :]:
            if data_a.get("entity") != data_b.get("entity") or data_a.get("predicate") != data_b.get("predicate"):
                continue
            if data_a.get("value") == data_b.get("value"):
                continue
            if not fact_interval(data_a)[0] <= fact_interval(data_b)[1] or not fact_interval(data_b)[0] <= fact_interval(data_a)[1]:
                continue
            rel_a = rel(path_a, root)
            rel_b = rel(path_b, root)
            if data_a.get("superseded_by") == rel_b or data_b.get("superseded_by") == rel_a:
                continue
            found = True
            lines.append(f"- `{rel_a}` conflicts with `{rel_b}` for `{data_a['entity']}.{data_a['predicate']}`")
    if not found:
        lines.append("No contradictions detected.")
    write(root / "memory/_views/contradictions.md", "\n".join(lines))


def build_stale(root: Path, rows: list[tuple[Path, dict[str, Any]]], threshold_days: int = 180) -> None:
    cutoff = today() - dt.timedelta(days=threshold_days)
    lines = ["# Stale facts", "", f"Policy: last_reviewed before {cutoff.isoformat()} ({threshold_days}+ days old).", ""]
    found = False
    for path, data in sorted(rows, key=lambda item: (str(item[1].get("last_reviewed")), rel(item[0], root))):
        reviewed = data.get("last_reviewed")
        if not reviewed:
            continue
        if isinstance(reviewed, dt.datetime):
            reviewed_date = reviewed.date()
        elif isinstance(reviewed, dt.date):
            reviewed_date = reviewed
        else:
            reviewed_date = dt.date.fromisoformat(str(reviewed))
        if reviewed_date < cutoff:
            found = True
            lines.append(f"- `{rel(path, root)}` — last reviewed {reviewed_date.isoformat()}")
    if not found:
        lines.append("No stale facts detected.")
    write(root / "memory/_views/stale.md", "\n".join(lines))


def build_graph(root: Path) -> None:
    lines = ["# Graph", ""]
    edges: set[tuple[str, str]] = set()
    for path in markdown_files(root):
        if "/_views/" in path.as_posix():
            continue
        _, body = split_frontmatter(path)
        source = rel(path, root)
        for link in WIKILINK_RE.findall(body):
            edges.add((source, link.strip()))
    if not edges:
        lines.append("No wikilinks detected.")
    else:
        for source, target in sorted(edges):
            lines.append(f"- `{source}` → `[[{target}]]`")
    write(root / "memory/_views/graph.md", "\n".join(lines))


def build_by_id(root: Path, rows: list[tuple[Path, dict[str, Any]]]) -> None:
    lines = ["# Records by id", ""]
    found = False
    for path, data in sorted(rows, key=lambda item: (str(item[1].get("id") or item[1].get("operation_id") or ""), rel(item[0], root))):
        record_id = data.get("id") or data.get("operation_id")
        if not record_id:
            continue
        found = True
        lines.append(f"- `{record_id}` — {data.get('type')} — `{rel(path, root)}`")
    if not found:
        lines.append("No stable ids detected.")
    write(root / "memory/_views/by-id.md", "\n".join(lines))


def build_by_predicate(root: Path, rows: list[tuple[Path, dict[str, Any]]]) -> None:
    lines = ["# Facts by predicate", ""]
    found = False
    for path, data in sorted(rows, key=lambda item: (item[1]["predicate"], item[1]["entity"], rel(item[0], root))):
        found = True
        lines.append(f"- **{data['predicate']}** — `{data['entity']}` = {render_value(data.get('value'))} — `{rel(path, root)}`")
    if not found:
        lines.append("No facts detected.")
    write(root / "memory/_views/by-predicate.md", "\n".join(lines))


def build_inbox(root: Path, rows: list[tuple[Path, dict[str, Any]]]) -> None:
    lines = ["# Inbox operations", ""]
    pending = [(path, data) for path, data in rows if "/_inbox/" in path.as_posix()]
    if not pending:
        lines.append("No inbox operations detected.")
    for path, data in sorted(pending, key=lambda item: (item[1].get("status", ""), str(item[1].get("created_at", "")), rel(item[0], root))):
        lines.append(
            f"- **{data.get('status')}** `{data.get('operation_id')}` "
            f"{data.get('op')} → `{data.get('target_id') or data.get('target_path') or 'n/a'}` — `{rel(path, root)}`"
        )
    write(root / "memory/_views/inbox.md", "\n".join(lines))


def build_operations(root: Path, rows: list[tuple[Path, dict[str, Any]]]) -> None:
    lines = ["# Operations", ""]
    if not rows:
        lines.append("No operations detected.")
    for path, data in sorted(rows, key=lambda item: (str(item[1].get("created_at", "")), rel(item[0], root)), reverse=True):
        lines.append(
            f"- **{data.get('created_at')}** — {data.get('status')} `{data.get('operation_id')}` "
            f"({data.get('op')}) by `{data.get('agent_id')}` — `{rel(path, root)}`"
        )
    write(root / "memory/_views/operations.md", "\n".join(lines))


def build_claims(root: Path, rows: list[tuple[Path, dict[str, Any]]]) -> None:
    lines = ["# Claims", ""]
    if not rows:
        lines.append("No active claims detected.")
    for path, data in sorted(rows, key=lambda item: (item[1].get("target_id", ""), rel(item[0], root))):
        lines.append(
            f"- `{data.get('target_id')}` claimed by `{data.get('agent_id')}` "
            f"for `{data.get('operation_id')}` until {data.get('expires_at')} — `{rel(path, root)}`"
        )
    write(root / "memory/_views/claims.md", "\n".join(lines))


def build_conflicts(root: Path, rows: list[tuple[Path, dict[str, Any]]]) -> None:
    lines = ["# Operation conflicts", ""]
    conflicts = [(path, data) for path, data in rows if data.get("status") == "conflict"]
    if not conflicts:
        lines.append("No operation conflicts detected.")
    for path, data in sorted(conflicts, key=lambda item: rel(item[0], root)):
        reason = data.get("conflict_reason") or "unspecified"
        lines.append(f"- `{data.get('operation_id')}` — {reason} — `{rel(path, root)}`")
    write(root / "memory/_views/conflicts.md", "\n".join(lines))


def main() -> int:
    root = Path.cwd()
    views = root / "memory/_views"
    if views.exists():
        shutil.rmtree(views)
    rows = facts(root)
    operation_rows = operations(root)
    build_by_entity(root, rows)
    build_timeline(root, events(root))
    build_contradictions(root, rows)
    build_stale(root, rows)
    build_graph(root)
    build_by_id(root, records(root))
    build_by_predicate(root, rows)
    build_inbox(root, operation_rows)
    build_operations(root, operation_rows)
    build_claims(root, claims(root))
    build_conflicts(root, operation_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
