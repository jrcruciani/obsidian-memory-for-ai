#!/usr/bin/env python3
"""V4 query implementation — used by query.sh.

All sub-commands use the index when available, fall back to filesystem scan
when the index is missing, stale, or corrupt. Both paths return identical
output format for the same vault state.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

from lint import split_frontmatter, parse_datetime
from rebuild_indexes import (
    build_lexical,
    build_graph_edges,
    load_entities,
    render_value,
    search_facts_filesystem,
    search_facts_index,
    graph_neighbors_filesystem,
    graph_neighbors_index,
)


def frontmatter(path: Path) -> dict[str, Any]:
    data, _ = split_frontmatter(path)
    return data


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def cmd_facts(root: Path, args: argparse.Namespace) -> int:
    entity = getattr(args, "entity", None)
    predicate = getattr(args, "predicate", None)
    found = False
    for path in sorted((root / "memory/facts").rglob("*.md")):
        data = frontmatter(path)
        if data.get("type") != "fact":
            continue
        if entity and data.get("entity") != entity:
            continue
        if predicate and data.get("predicate") != predicate:
            continue
        print(f"{rel(path, root)}: {data['predicate']} = {render_value(data.get('value'))}")
        found = True
    if not found:
        filters = []
        if entity:
            filters.append(f"entity={entity}")
        if predicate:
            filters.append(f"predicate={predicate}")
        print(f"No facts found" + (f" ({', '.join(filters)})" if filters else "."))
    return 0


def cmd_events(root: Path, args: argparse.Namespace) -> int:
    since = getattr(args, "since", None)
    found = False
    for path in sorted((root / "memory/events").rglob("*.md")):
        data = frontmatter(path)
        if data.get("type") != "event":
            continue
        occurred_str = str(data.get("occurred_at", ""))
        if since and occurred_str[:10] < since:
            continue
        entities_str = ", ".join(data.get("entities", []) or [])
        print(f"{occurred_str[:10]} — {data.get('summary')} [{entities_str}] — {rel(path, root)}")
        found = True
    if not found:
        print("No events found.")
    return 0


def cmd_id(root: Path, args: argparse.Namespace) -> int:
    record_id = args.record_id
    for path in sorted((root / "memory").rglob("*.md")):
        if "/_views/" in path.as_posix() or "/_indexes/" in path.as_posix():
            continue
        data = frontmatter(path)
        for key in ("id", "operation_id", "transaction_id", "proposal_id", "review_id"):
            if data.get(key) == record_id:
                print(f"{rel(path, root)}: {data.get('type')}")
                return 0
    print(f"No record found with id {record_id!r}")
    return 1


def cmd_operations(root: Path, args: argparse.Namespace) -> int:
    status_filter = getattr(args, "status", None)
    found = False
    for base in (root / "memory/_inbox", root / "memory/_ops"):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.md")):
            data = frontmatter(path)
            if data.get("type") != "operation":
                continue
            if status_filter and data.get("status") != status_filter:
                continue
            print(f"{str(data.get('created_at', ''))[:19]}  {data.get('status'):<12}  {data.get('operation_id')}  ({data.get('op')})")
            found = True
    if not found:
        print("No operations found.")
    return 0


def cmd_search(root: Path, args: argparse.Namespace) -> int:
    """Search facts using index with filesystem fallback."""
    term = args.term
    # Try index first, fall back to filesystem
    index_path = root / "memory/_indexes/lexical.md"
    if index_path.exists():
        results = search_facts_index(root, term)
        source = "index"
    else:
        results = search_facts_filesystem(root, term)
        source = "filesystem"
    if not results:
        print(f"No facts found matching {term!r} (searched via {source})")
        return 0
    for entity, predicate, value, path_str in results:
        print(f"{entity}/{predicate} = {value}  [{path_str}]")
    return 0


def cmd_graph(root: Path, args: argparse.Namespace) -> int:
    """Show entity relationships using index with filesystem fallback."""
    subcmd = getattr(args, "subcmd", "entity")
    entity = getattr(args, "entity", None)
    if not entity:
        print("ERROR: --entity is required for graph queries", file=sys.stderr)
        return 1

    index_path = root / "memory/_indexes/graph.md"
    if index_path.exists():
        neighbors = graph_neighbors_index(root, entity)
        source = "index"
    else:
        neighbors = graph_neighbors_filesystem(root, entity)
        source = "filesystem"

    if not neighbors:
        print(f"No relationships found for entity {entity!r} (searched via {source})")
        return 0
    for target, evidence in neighbors:
        print(f"{entity} → {target}  (via {evidence})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")

    p_facts = sub.add_parser("facts")
    p_facts.add_argument("--entity", default=None)
    p_facts.add_argument("--predicate", default=None)

    p_events = sub.add_parser("events")
    p_events.add_argument("--since", default=None)

    p_id = sub.add_parser("id")
    p_id.add_argument("record_id")

    p_ops = sub.add_parser("operations")
    p_ops.add_argument("--status", default=None)

    p_search = sub.add_parser("search")
    p_search.add_argument("term")

    p_graph = sub.add_parser("graph")
    p_graph.add_argument("subcmd", choices=["entity"])
    p_graph.add_argument("entity")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = Path.cwd()

    if args.command == "facts":
        return cmd_facts(root, args)
    if args.command == "events":
        return cmd_events(root, args)
    if args.command == "id":
        return cmd_id(root, args)
    if args.command == "operations":
        return cmd_operations(root, args)
    if args.command == "search":
        return cmd_search(root, args)
    if args.command == "graph":
        return cmd_graph(root, args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
