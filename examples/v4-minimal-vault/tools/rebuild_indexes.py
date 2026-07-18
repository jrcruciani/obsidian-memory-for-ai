#!/usr/bin/env python3
"""Build deterministic lexical and graph indexes from canonical Markdown sources.

Both indexes are derived entirely from memory/facts/, memory/events/, and
memory/people/ (for graph edges via wikilinks). Deleting the indexes and
running this script again produces byte-identical output for the same
canonical input.

The indexes are non-canonical: removing them does not affect vault validity.
Query tools must fall back to direct filesystem scanning when indexes are
missing, stale, or corrupt, and must return identical results in both modes.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

from lint import FRONTMATTER_RE, WIKILINK_RE, markdown_files, rel, split_frontmatter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def frontmatter(path: Path) -> dict[str, Any]:
    data, _ = split_frontmatter(path)
    return data


def render_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return "`" + yaml.safe_dump(value, sort_keys=True).strip().replace("\n", " ") + "`"
    return str(value)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Lexical index
#
# Format: alphabetically sorted list of every fact entry, each line:
#   - `entity/predicate` = VALUE  [`path`]
#
# The sort key is (entity, predicate, path) — stable and deterministic.
# ---------------------------------------------------------------------------


def build_lexical(root: Path) -> list[str]:
    """Return sorted lexical index lines for all canonical facts."""
    rows: list[tuple[str, str, str, str]] = []
    for path in sorted((root / "memory/facts").rglob("*.md")):
        data = frontmatter(path)
        if data.get("type") != "fact":
            continue
        entity = str(data.get("entity", ""))
        predicate = str(data.get("predicate", ""))
        value = render_value(data.get("value"))
        path_str = rel(path, root)
        rows.append((entity, predicate, value, path_str))
    rows.sort(key=lambda r: (r[0], r[1], r[3]))
    return [f"- `{e}/{p}` = {v}  [`{ps}`]" for e, p, v, ps in rows]


def build_lexical_index(root: Path) -> str:
    lines = ["# Lexical index", "",
             "Alphabetically sorted list of all canonical facts. "
             "Generated from `memory/facts/`. Do not edit — regenerate with `tools/rebuild-indexes.sh`.",
             ""]
    entries = build_lexical(root)
    if not entries:
        lines.append("No facts indexed.")
    else:
        lines.extend(entries)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Graph index
#
# Format: entity → related entities derived from:
#   1. Fact values where the value looks like a known entity slug
#   2. Wikilinks from people/ and projects/ pages that reference facts/
#
# The sort key is (source_entity, target_entity, evidence_path) — deterministic.
# ---------------------------------------------------------------------------


def load_entities(root: Path) -> set[str]:
    path = root / "memory/entities.md"
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        return set()
    data = yaml.safe_load(match.group(1)) or {}
    return {item["id"] for item in data.get("entities", []) if isinstance(item, dict) and "id" in item}


def slug_re(entities: set[str]) -> re.Pattern[str] | None:
    if not entities:
        return None
    escaped = [re.escape(e) for e in sorted(entities, key=len, reverse=True)]
    return re.compile(r"\b(" + "|".join(escaped) + r")\b")


def build_graph_edges(root: Path, entities: set[str]) -> list[tuple[str, str, str]]:
    """Return sorted list of (source_entity, target_entity, evidence_path) triples."""
    edges: set[tuple[str, str, str]] = set()
    pattern = slug_re(entities)

    # Edges from fact values referencing known entity slugs
    for path in sorted((root / "memory/facts").rglob("*.md")):
        data = frontmatter(path)
        if data.get("type") != "fact":
            continue
        source_entity = str(data.get("entity", ""))
        value = str(data.get("value", ""))
        if pattern:
            for match in pattern.finditer(value):
                target = match.group(1)
                if target != source_entity and target in entities:
                    edges.add((source_entity, target, rel(path, root)))

    # Edges from wikilinks in people/ and projects/ pages
    for path in sorted((root / "memory").rglob("*.md")):
        if "/_views/" in path.as_posix() or "/_indexes/" in path.as_posix():
            continue
        if "facts/" in path.as_posix():
            continue
        data, body = split_frontmatter(path)
        # Infer source entity from page type and wikilinks pointing at fact files
        source_entity: str | None = None
        if data.get("type") == "person":
            source_entity = data.get("id") or path.stem
        elif "people/" in path.as_posix():
            source_entity = path.stem

        if source_entity and source_entity in entities:
            for link in WIKILINK_RE.findall(body):
                link = link.strip()
                # Extract entity slug from fact paths like memory/facts/{entity}/...
                m = re.match(r"(?:memory/)?facts/([a-z0-9-]+)/", link)
                if m:
                    target = m.group(1)
                    if target != source_entity and target in entities:
                        edges.add((source_entity, target, rel(path, root)))

    return sorted(edges)


def build_graph_index(root: Path) -> str:
    entities = load_entities(root)
    lines = ["# Graph index", "",
             "Entity relationship graph derived from fact values and wikilinks. "
             "Generated from `memory/facts/` and `memory/people/`. "
             "Do not edit — regenerate with `tools/rebuild-indexes.sh`.",
             ""]
    edges = build_graph_edges(root, entities)
    if not edges:
        lines.append("No entity relationships detected.")
    else:
        # Group by source entity for readability
        current_source: str | None = None
        for source, target, evidence in edges:
            if source != current_source:
                if current_source is not None:
                    lines.append("")
                lines.append(f"## {source}")
                lines.append("")
                current_source = source
            lines.append(f"- → `{target}`  (via `{evidence}`)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Filesystem fallback search (used when index is missing/stale/corrupt)
# ---------------------------------------------------------------------------


def search_facts_filesystem(root: Path, term: str) -> list[tuple[str, str, str, str]]:
    """Scan facts directly and return (entity, predicate, value, path) for matches."""
    results: list[tuple[str, str, str, str]] = []
    term_lower = term.lower()
    for path in sorted((root / "memory/facts").rglob("*.md")):
        data = frontmatter(path)
        if data.get("type") != "fact":
            continue
        entity = str(data.get("entity", ""))
        predicate = str(data.get("predicate", ""))
        value = render_value(data.get("value"))
        if (term_lower in entity.lower()
                or term_lower in predicate.lower()
                or term_lower in value.lower()):
            results.append((entity, predicate, value, rel(path, root)))
    return results


def search_facts_index(root: Path, term: str) -> list[tuple[str, str, str, str]]:
    """Search the lexical index file and return same format as filesystem scan."""
    index_path = root / "memory/_indexes/lexical.md"
    if not index_path.exists():
        return search_facts_filesystem(root, term)
    results: list[tuple[str, str, str, str]] = []
    term_lower = term.lower()
    line_re = re.compile(r"^- `([^/]+)/([^`]+)` = (.+?)  \[`([^`]+)`\]$")
    for line in index_path.read_text(encoding="utf-8").splitlines():
        m = line_re.match(line)
        if not m:
            continue
        entity, predicate, value, path_str = m.group(1), m.group(2), m.group(3), m.group(4)
        if (term_lower in entity.lower()
                or term_lower in predicate.lower()
                or term_lower in value.lower()):
            results.append((entity, predicate, value, path_str))
    return results


def graph_neighbors_filesystem(root: Path, entity: str) -> list[tuple[str, str]]:
    """Scan directly for neighbors of entity; returns (target, evidence_path) pairs."""
    entities = load_entities(root)
    edges = build_graph_edges(root, entities)
    return [(target, ev) for source, target, ev in edges if source == entity]


def graph_neighbors_index(root: Path, entity: str) -> list[tuple[str, str]]:
    """Read neighbors from graph index; fall back to filesystem scan if unavailable."""
    index_path = root / "memory/_indexes/graph.md"
    if not index_path.exists():
        return graph_neighbors_filesystem(root, entity)
    results: list[tuple[str, str]] = []
    in_section = False
    line_re = re.compile(r"^- → `([^`]+)`  \(via `([^`]+)`\)$")
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if line == f"## {entity}":
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            m = line_re.match(line)
            if m:
                results.append((m.group(1), m.group(2)))
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    root = Path.cwd()
    indexes_dir = root / "memory/_indexes"
    if indexes_dir.exists():
        shutil.rmtree(indexes_dir)
    indexes_dir.mkdir(parents=True)

    write(root / "memory/_indexes/lexical.md", build_lexical_index(root))
    write(root / "memory/_indexes/graph.md", build_graph_index(root))
    print("Indexes rebuilt: memory/_indexes/lexical.md  memory/_indexes/graph.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
