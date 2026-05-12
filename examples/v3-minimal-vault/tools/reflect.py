#!/usr/bin/env python3
"""Write a conservative reflection event operation to memory/_inbox."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

import yaml

from ops import agent_id, operation_id


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:64] or "reflection"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", default="agent", help="Agent id for memory/_inbox/{agent}")
    parser.add_argument("--summary", required=True, help="Session summary to propose as an event")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing")
    args = parser.parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    date = now.date().isoformat()
    slug = slugify(args.summary)
    op_id = operation_id(now)
    normalized_agent = agent_id(args.agent)
    event_id = f"event-{date}-{slug}"
    relative = Path("memory/_inbox") / normalized_agent / "ops" / f"{op_id}.md"
    payload = {
        "type": "event",
        "id": event_id,
        "occurred_at": now.isoformat().replace("+00:00", "Z"),
        "summary": args.summary,
        "entities": [],
        "kind": "observation",
        "sources": [],
        "derived_facts": [],
    }
    frontmatter = {
        "type": "operation",
        "operation_id": op_id,
        "op": "add_event",
        "agent_id": normalized_agent,
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "target_id": event_id,
        "target_path": f"memory/events/{date}/{slug}.md",
        "precondition_hash": None,
        "status": "proposed",
        "reason": args.summary,
        "sources": [],
        "payload": payload,
    }
    content = f"""---
{yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()}
---

# Reflection operation

{args.summary}
"""
    if args.dry_run:
        print(content)
        return 0
    relative.parent.mkdir(parents=True, exist_ok=True)
    relative.write_text(content, encoding="utf-8")
    print(relative)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
