#!/usr/bin/env python3
"""Write a conservative reflection proposal to memory/_inbox."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

import yaml


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
    relative = Path("memory/_inbox") / args.agent / date / f"{slug}.md"
    frontmatter = {
        "type": "event",
        "occurred_at": now.isoformat().replace("+00:00", "Z"),
        "summary": args.summary,
        "entities": [],
        "kind": "observation",
        "sources": [],
        "derived_facts": [],
    }
    content = f"""---
{yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()}
---

# Reflection proposal

{args.summary}
"""
    if args.dry_run:
        print(content)
        return 0
    relative.parent.mkdir(parents=True, exist_ok=True)
    relative.write_text(content, encoding="utf-8")
    result = subprocess.run([sys.executable, "tools/lint.py"], check=False)
    if result.returncode != 0:
        return result.returncode
    print(relative)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
