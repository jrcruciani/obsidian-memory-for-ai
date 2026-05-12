#!/usr/bin/env python3
"""Create markdown-native v3.1 operation envelopes and advisory claims."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import re
import secrets
import sys
from pathlib import Path
from typing import Any

import yaml


AGENT_ID_RE = re.compile(r"^agent-[a-z0-9-]+-[a-f0-9]{8}$")


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(value: dt.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def slugify(text: str, limit: int = 64) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:limit] or "operation"


def agent_id(value: str | None) -> str:
    if value and AGENT_ID_RE.match(value):
        return value
    base = slugify(value or "local", 40)
    return f"agent-{base}-{secrets.token_hex(4)}"


def operation_id(now: dt.datetime | None = None) -> str:
    current = now or utc_now()
    stamp = current.strftime("%Y%m%dT%H%M%SZ")
    return f"op-{stamp.lower()}-{secrets.token_hex(4)}"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def read_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    _, frontmatter, _ = text.split("---", 2)
    return yaml.safe_load(frontmatter) or {}


def write_operation(
    *,
    op: str,
    agent: str,
    target_id: str | None,
    target_path: str | None,
    reason: str,
    sources: list[str],
    payload: dict[str, Any] | None,
    precondition_hash: str | None,
    dry_run: bool,
) -> Path:
    now = utc_now()
    op_id = operation_id(now)
    normalized_agent = agent_id(agent)
    frontmatter = {
        "type": "operation",
        "operation_id": op_id,
        "op": op,
        "agent_id": normalized_agent,
        "created_at": iso(now),
        "target_id": target_id,
        "target_path": target_path,
        "precondition_hash": precondition_hash,
        "status": "proposed",
        "reason": reason,
        "sources": sources,
        "payload": payload or {},
    }
    text = f"""---
{yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()}
---

# Operation proposal

{reason}
"""
    relative = Path("memory/_inbox") / normalized_agent / "ops" / f"{op_id}.md"
    if dry_run:
        print(text)
        return relative
    relative.parent.mkdir(parents=True, exist_ok=True)
    relative.write_text(text, encoding="utf-8")
    print(relative)
    return relative


def cmd_new_agent_id(args: argparse.Namespace) -> int:
    print(agent_id(args.name))
    return 0


def cmd_add_event(args: argparse.Namespace) -> int:
    now = utc_now()
    day = now.date().isoformat()
    slug = slugify(args.summary)
    event_id = f"event-{day}-{slug}"
    target_path = f"memory/events/{day}/{slug}.md"
    payload = {
        "type": "event",
        "id": event_id,
        "occurred_at": iso(now),
        "summary": args.summary,
        "entities": args.entity,
        "kind": args.kind,
        "sources": args.source,
        "derived_facts": [],
    }
    write_operation(
        op="add_event",
        agent=args.agent,
        target_id=event_id,
        target_path=target_path,
        reason=args.reason or args.summary,
        sources=args.source,
        payload=payload,
        precondition_hash=None,
        dry_run=args.dry_run,
    )
    return 0


def cmd_create_fact(args: argparse.Namespace) -> int:
    now = utc_now()
    fact_id = args.id or f"fact-{args.entity}-{args.predicate}"
    target_path = args.target or f"memory/facts/{args.entity}/{args.predicate}.md"
    payload = {
        "type": "fact",
        "id": fact_id,
        "entity": args.entity,
        "predicate": args.predicate,
        "value": args.value,
        "valid_from": args.valid_from,
        "valid_to": args.valid_to,
        "recorded_at": iso(now),
        "confidence": args.confidence,
        "sources": args.source,
        "last_reviewed": now.date().isoformat(),
        "tags": args.tag,
        "decay": {
            "review_after_days": args.review_after_days,
            "archive_after_valid_to": True,
            "pin": args.pin,
        },
    }
    write_operation(
        op="create_fact",
        agent=args.agent,
        target_id=fact_id,
        target_path=target_path,
        reason=args.reason,
        sources=args.source,
        payload=payload,
        precondition_hash=None,
        dry_run=args.dry_run,
    )
    return 0


def cmd_archive_fact(args: argparse.Namespace) -> int:
    target = Path(args.target)
    if not target.exists():
        print(f"target not found: {args.target}", file=sys.stderr)
        return 2
    data = read_frontmatter(target)
    write_operation(
        op="archive_fact",
        agent=args.agent,
        target_id=data.get("id"),
        target_path=args.target,
        reason=args.reason,
        sources=[],
        payload={"archive_reason": args.reason},
        precondition_hash=file_hash(target),
        dry_run=args.dry_run,
    )
    return 0


def cmd_claim(args: argparse.Namespace) -> int:
    now = utc_now()
    expires = now + dt.timedelta(minutes=args.ttl_minutes)
    data = {
        "type": "claim",
        "target_id": args.target_id,
        "operation_id": args.operation_id,
        "agent_id": agent_id(args.agent),
        "created_at": iso(now),
        "expires_at": iso(expires),
        "heartbeat_at": iso(now),
        "status": "active",
    }
    path = Path("memory/_claims") / f"{args.target_id}.yaml"
    if args.dry_run:
        print(yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip())
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)
    except FileExistsError:
        print(f"claim already exists: {path}", file=sys.stderr)
        return 1
    print(path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    new_agent = sub.add_parser("new-agent-id", help="Generate a collision-resistant agent id")
    new_agent.add_argument("name", nargs="?", default="local")
    new_agent.set_defaults(func=cmd_new_agent_id)

    add_event = sub.add_parser("add-event", help="Propose an append-only event")
    add_event.add_argument("--agent", default="local")
    add_event.add_argument("--summary", required=True)
    add_event.add_argument("--kind", default="observation", choices=["conversation", "decision", "ingest", "action", "observation"])
    add_event.add_argument("--entity", action="append", default=[])
    add_event.add_argument("--source", action="append", default=[])
    add_event.add_argument("--reason")
    add_event.add_argument("--dry-run", action="store_true")
    add_event.set_defaults(func=cmd_add_event)

    create_fact = sub.add_parser("create-fact", help="Propose a new atomic fact")
    create_fact.add_argument("--agent", default="local")
    create_fact.add_argument("--id")
    create_fact.add_argument("--entity", required=True)
    create_fact.add_argument("--predicate", required=True)
    create_fact.add_argument("--value", required=True)
    create_fact.add_argument("--valid-from")
    create_fact.add_argument("--valid-to")
    create_fact.add_argument("--confidence", default="medium", choices=["high", "medium", "low"])
    create_fact.add_argument("--source", action="append", default=[])
    create_fact.add_argument("--tag", action="append", default=[])
    create_fact.add_argument("--target")
    create_fact.add_argument("--review-after-days", type=int, default=180)
    create_fact.add_argument("--pin", action="store_true")
    create_fact.add_argument("--reason", required=True)
    create_fact.add_argument("--dry-run", action="store_true")
    create_fact.set_defaults(func=cmd_create_fact)

    archive_fact = sub.add_parser("archive-fact", help="Propose archiving a fact")
    archive_fact.add_argument("--agent", default="local")
    archive_fact.add_argument("--target", required=True)
    archive_fact.add_argument("--reason", required=True)
    archive_fact.add_argument("--dry-run", action="store_true")
    archive_fact.set_defaults(func=cmd_archive_fact)

    claim = sub.add_parser("claim", help="Create an advisory claim for a target id")
    claim.add_argument("--agent", default="local")
    claim.add_argument("--target-id", required=True)
    claim.add_argument("--operation-id", required=True)
    claim.add_argument("--ttl-minutes", type=int, default=30)
    claim.add_argument("--dry-run", action="store_true")
    claim.set_defaults(func=cmd_claim)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
