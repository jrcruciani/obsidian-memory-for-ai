#!/usr/bin/env python3
"""Zero-dependency stdio MCP (Model Context Protocol) server for Knowledge Factory v5 Personal Memory.

Exposes personal memory tools and views over JSON-RPC 2.0 stdio so Hermes,
Claude Desktop, Cursor, or any MCP host can read/search/remember against a
plain-Markdown Obsidian vault without external packages or background daemons.

Usage:
    python3 tools/kf_mcp.py --vault /path/to/my-memory-vault
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kflib import SPEC_VERSION  # noqa: E402
from kflib.bootstrap import build_bootstrap_with_meta  # noqa: E402
from kflib.capture import capture_event, capture_signal  # noqa: E402
from kflib.curate import build_sleep_curation_pack  # noqa: E402
from kflib.hybrid_index import hybrid_search  # noqa: E402
from kflib.personal import default_personal_actor, forget_fact, remember_fact, write_note  # noqa: E402
from kflib.query import (  # noqa: E402
    query_facts,
    query_graph,
    query_guidance,
    query_search,
    query_skills,
    query_why,
)

SERVER_NAME = "obsidian-memory-kf-personal"
SERVER_VERSION = f"{SPEC_VERSION}-personal"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "kf_bootstrap",
        "description": "Load role/token-budgeted memory context for the current session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string", "description": "Bootstrap profile: personal, default, executor, curator"},
                "max_tokens": {"type": "integer", "description": "Optional token cap"},
                "budget_chars": {"type": "integer", "description": "Optional exact character cap"},
            },
        },
    },
    {
        "name": "kf_search",
        "description": "Search personal memory using BM25 or disposable SQLite FTS5 (+ optional embeddings) RRF hybrid search.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "hybrid": {"type": "boolean", "default": True},
                "embeddings": {"type": "boolean", "default": False},
                "include_notes": {"type": "boolean", "default": True},
                "include_sources": {"type": "boolean", "default": False},
                "types": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "kf_remember",
        "description": "Create, confirm, or bitemporally supersede a personal fact (blocks trust='external' for prompt-injection safety).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity": {"type": "string"},
                "predicate": {"type": "string"},
                "value": {},
                "valid_from": {"type": "string"},
                "pinned": {"type": "boolean", "default": False},
                "trust": {"type": "string", "enum": ["owner", "agent"], "default": "owner"},
                "entity_kind": {"type": "string", "default": "concept"},
                "entity_display": {"type": "string"},
                "body": {"type": "string", "default": ""},
            },
            "required": ["entity", "predicate", "value"],
        },
    },
    {
        "name": "kf_forget",
        "description": "Non-destructively retract a personal fact with an audit receipt.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity": {"type": "string"},
                "predicate": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["entity", "predicate", "reason"],
        },
    },
    {
        "name": "kf_note",
        "description": "Create or append a non-authoritative Obsidian note under knowledge/notes/.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string"},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "kind": {"type": "string", "default": "general"},
                "entities": {"type": "array", "items": {"type": "string"}},
                "tags": {"type": "array", "items": {"type": "string"}},
                "append": {"type": "boolean", "default": False},
            },
            "required": ["slug", "title", "body"],
        },
    },
    {
        "name": "kf_capture_signal",
        "description": "Emit a low-friction append-only gap, friction, contradiction, or external observation signal for curation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["gap", "contradiction", "friction", "stale", "observation", "broken_reference", "uncurated_claim"]},
                "summary": {"type": "string"},
                "severity": {"type": "string", "enum": ["low", "medium", "high"], "default": "medium"},
                "target_namespace": {"type": "string", "default": "facts"},
                "entities": {"type": "array", "items": {"type": "string"}},
                "evidence": {"type": "array", "items": {"type": "string"}},
                "emitted_by": {"type": "string"},
            },
            "required": ["kind", "summary"],
        },
    },
    {
        "name": "kf_query_facts",
        "description": "Query current, historical (--as-of), or full supersession chains of facts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity": {"type": "string"},
                "predicate": {"type": "string"},
                "as_of": {"type": "string"},
                "history": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "kf_query_skills",
        "description": "Lookup active procedural skills by domain or multi-term trigger.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string"},
                "trigger": {"type": "string"},
            },
        },
    },
    {
        "name": "kf_query_guidance",
        "description": "Lookup active normative guardrails by domain, scope, or priority.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string"},
                "scope": {"type": "string"},
                "priority": {"type": "string"},
            },
        },
    },
    {
        "name": "kf_query_why",
        "description": "Trace full end-to-end provenance (sources, signals, proposals, reviews, receipts, supersedes) for a record.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["fact", "skill", "guidance", "decision"]},
                "target": {"type": "string"},
                "predicate": {"type": "string"},
            },
            "required": ["kind", "target"],
        },
    },
    {
        "name": "kf_query_graph",
        "description": "Explore multi-hop entity relationships or shortest path between two entities (optionally --as-of a date).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node": {"type": "string"},
                "depth": {"type": "integer", "default": 1},
                "target_node": {"type": "string"},
                "as_of": {"type": "string"},
            },
            "required": ["node"],
        },
    },
    {
        "name": "kf_sleep_pack",
        "description": "Build a prompt-injection-hardened Sleep-Time Curation packet of drift, open signals, and recent events.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "emit_signals": {"type": "boolean", "default": False},
                "max_sources": {"type": "integer", "default": 8},
            },
        },
    },
]

RESOURCES: list[dict[str, str]] = [
    {"uri": "kf://dashboard", "name": "Personal Memory Dashboard", "mimeType": "text/markdown"},
    {"uri": "kf://bootstrap/personal", "name": "Personal Bootstrap Context", "mimeType": "text/markdown"},
    {"uri": "kf://catalog", "name": "Knowledge Catalog", "mimeType": "text/markdown"},
    {"uri": "kf://factory-queue", "name": "Factory Review Queue", "mimeType": "text/markdown"},
]


def _call_tool(root: Path, name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "kf_bootstrap":
        text, meta = build_bootstrap_with_meta(
            root,
            profile=args.get("profile"),
            budget_override=args.get("budget_chars"),
            max_tokens=args.get("max_tokens"),
        )
        return {"text": text, "meta": meta}

    if name == "kf_search":
        tset = set(args["types"]) if args.get("types") else None
        limit = int(args.get("limit", 10))
        if args.get("hybrid", True):
            text, rows, diags = hybrid_search(
                root,
                args["query"],
                types=tset,
                use_embeddings=bool(args.get("embeddings", False)),
                limit=limit,
            )
        else:
            text, rows, diags = query_search(
                root,
                args["query"],
                types=tset,
                include_notes=bool(args.get("include_notes", True)),
                include_sources=bool(args.get("include_sources", False)),
                limit=limit,
            )
        return {"text": text, "results": rows, "diagnostics": diags}

    if name == "kf_remember":
        return remember_fact(
            root,
            entity=args["entity"],
            predicate=args["predicate"],
            value=args["value"],
            valid_from=args.get("valid_from"),
            pinned=bool(args.get("pinned", False)),
            trust=str(args.get("trust", "owner")),
            entity_kind=str(args.get("entity_kind", "concept")),
            entity_display=args.get("entity_display"),
            body=str(args.get("body", "")),
            rebuild=True,
        )

    if name == "kf_forget":
        return forget_fact(
            root,
            entity=args["entity"],
            predicate=args["predicate"],
            reason=args["reason"],
            rebuild=True,
        )

    if name == "kf_note":
        return write_note(
            root,
            slug=args["slug"],
            title=args["title"],
            body=args["body"],
            kind=str(args.get("kind", "general")),
            entities=args.get("entities"),
            tags=args.get("tags"),
            append=bool(args.get("append", False)),
        )

    if name == "kf_capture_signal":
        return capture_signal(
            root,
            emitted_by=args.get("emitted_by") or default_personal_actor(root),
            kind=args["kind"],
            summary=args["summary"],
            severity=str(args.get("severity", "medium")),
            target_namespace=str(args.get("target_namespace", "facts")),
            entities=args.get("entities"),
            evidence=args.get("evidence"),
        )

    if name == "kf_query_facts":
        text, rows = query_facts(
            root,
            entity=args.get("entity"),
            predicate=args.get("predicate"),
            as_of=args.get("as_of"),
            history=bool(args.get("history", False)),
        )
        return {"text": text, "facts": rows}

    if name == "kf_query_skills":
        text, rows = query_skills(root, domain=args.get("domain"), trigger=args.get("trigger"))
        return {"text": text, "skills": rows}

    if name == "kf_query_guidance":
        text, rows = query_guidance(
            root,
            domain=args.get("domain"),
            scope=args.get("scope"),
            priority=args.get("priority"),
        )
        return {"text": text, "guidance": rows}

    if name == "kf_query_why":
        text, payload = query_why(root, kind=args["kind"], target=args["target"], predicate=args.get("predicate"))
        return {"text": text, "lineage": payload}

    if name == "kf_query_graph":
        text, rows, diags = query_graph(
            root,
            args["node"],
            depth=int(args.get("depth", 1)),
            target_node=args.get("target_node"),
            as_of=args.get("as_of"),
        )
        return {"text": text, "relationships": rows, "diagnostics": diags}

    if name == "kf_sleep_pack":
        return build_sleep_curation_pack(
            root,
            emit_signals=bool(args.get("emit_signals", False)),
            max_sources=int(args.get("max_sources", 8)),
        )

    raise ValueError(f"unknown MCP tool: {name}")


def _read_resource(root: Path, uri: str) -> str:
    if uri == "kf://dashboard":
        p = root / "_generated/views/dashboard.md"
        if p.is_file():
            return p.read_text(encoding="utf-8")
        return build_bootstrap_with_meta(root)[0]
    if uri == "kf://bootstrap/personal":
        text, _ = build_bootstrap_with_meta(root, profile=None)
        return text
    if uri == "kf://catalog":
        p = root / "_generated/views/catalog.md"
        return p.read_text(encoding="utf-8") if p.is_file() else ""
    if uri == "kf://factory-queue":
        p = root / "_generated/views/factory-queue.md"
        return p.read_text(encoding="utf-8") if p.is_file() else ""
    raise ValueError(f"unknown resource URI: {uri}")


def handle_request(root: Path, req: dict[str, Any]) -> dict[str, Any] | None:
    method = req.get("method")
    req_id = req.get("id")
    params = req.get("params") or {}

    if method == "notifications/initialized" or req_id is None:
        return None

    try:
        if method == "initialize":
            result = {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            tname = str(params.get("name", ""))
            targs = params.get("arguments") or {}
            payload = _call_tool(root, tname, targs)
            result = {
                "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
                "isError": False,
            }
        elif method == "resources/list":
            result = {"resources": RESOURCES}
        elif method == "resources/read":
            uri = str(params.get("uri", ""))
            content = _read_resource(root, uri)
            result = {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": content}]}
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    except Exception as exc:
        if method == "tools/call":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": str(exc)}, ensure_ascii=False)}],
                    "isError": True,
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32000, "message": str(exc)},
        }


def serve_stdio(root: Path) -> int:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {exc}"}}
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            continue
        resp = handle_request(root, req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Knowledge Factory v5 Personal Memory stdio MCP Server")
    parser.add_argument("--vault", type=Path, default=Path.cwd(), help="Path to the Knowledge Factory vault")
    args = parser.parse_args(argv)
    return serve_stdio(args.vault.resolve())


if __name__ == "__main__":
    sys.exit(main())
