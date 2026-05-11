#!/usr/bin/env python3
"""Review inbox entries, move safe records into canon, and archive expired facts."""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path

from lint import parse_date, parse_datetime, rel, split_frontmatter


def confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    answer = input(f"{prompt} [y/N] ")
    return answer.lower() in {"y", "yes"}


def target_for(root: Path, path: Path, data: dict) -> Path | None:
    typ = data.get("type")
    if typ == "event":
        occurred = parse_datetime(data["occurred_at"])
        day = occurred.astimezone(dt.timezone.utc).date().isoformat()
        return root / "memory/events" / day / path.name
    if typ == "fact":
        entity = data["entity"]
        predicate = data["predicate"]
        return root / "memory/facts" / entity / f"{predicate}.md"
    if typ == "decision":
        return root / "memory/decisions" / path.name
    if typ == "insight":
        return root / "memory/insights" / path.name
    return None


def move_inbox(root: Path, assume_yes: bool) -> int:
    moved = 0
    inbox = root / "memory/_inbox"
    for path in sorted(inbox.rglob("*.md")):
        data, _ = split_frontmatter(path)
        target = target_for(root, path, data)
        if target is None:
            print(f"Skipping {rel(path, root)}: unsupported type {data.get('type')!r}")
            continue
        if target.exists():
            print(f"Conflict: {rel(target, root)} already exists; leaving {rel(path, root)} in inbox")
            continue
        if confirm(f"Move {rel(path, root)} -> {rel(target, root)}?", assume_yes):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(target))
            moved += 1
    return moved


def archive_expired(root: Path, assume_yes: bool) -> int:
    archived = 0
    today = dt.date.fromisoformat(__import__("os").environ.get("MEMORY_TODAY", dt.date.today().isoformat()))
    for path in sorted((root / "memory/facts").rglob("*.md")):
        data, _ = split_frontmatter(path)
        valid_to = parse_date(data.get("valid_to"))
        if not valid_to or valid_to >= today:
            continue
        year = str(valid_to.year)
        target = root / "memory/_archive" / year / path.relative_to(root / "memory")
        if target.exists():
            print(f"Archive conflict: {rel(target, root)} already exists")
            continue
        if confirm(f"Archive expired fact {rel(path, root)} -> {rel(target, root)}?", assume_yes):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(target))
            archived += 1
    return archived


def run(command: list[str]) -> int:
    return subprocess.run(command, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="Apply safe moves without prompting")
    args = parser.parse_args()
    root = Path.cwd()

    if run([sys.executable, "tools/lint.py"]) != 0:
        return 1
    moved = move_inbox(root, args.yes)
    archived = archive_expired(root, args.yes)
    if moved or archived:
        if run([sys.executable, "tools/rebuild_views.py"]) != 0:
            return 1
        if run([sys.executable, "tools/lint.py"]) != 0:
            return 1
    print(f"Moved inbox entries: {moved}")
    print(f"Archived expired facts: {archived}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

