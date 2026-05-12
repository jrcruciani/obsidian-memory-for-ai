#!/usr/bin/env python3
"""Validate, apply, and archive markdown-native v3 memory operations."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from lint import parse_date, parse_datetime, rel, split_frontmatter


def confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    answer = input(f"{prompt} [y/N] ")
    return answer.lower() in {"y", "yes"}


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(value: dt.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def write_markdown(path: Path, frontmatter: dict[str, Any], body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = f"""---
{yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()}
---
"""
    if body:
        text += f"\n{body.rstrip()}\n"
    else:
        text += "\n"
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def target_for(root: Path, path: Path, data: dict[str, Any]) -> Path | None:
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


def active_claim_conflict(root: Path, data: dict[str, Any]) -> str | None:
    target_id = data.get("target_id")
    if not target_id:
        return None
    claim_path = root / "memory/_claims" / f"{target_id}.yaml"
    if not claim_path.exists():
        return None
    claim = yaml.safe_load(claim_path.read_text(encoding="utf-8")) or {}
    if claim.get("status", "active") != "active":
        return None
    expires_at = parse_datetime(claim["expires_at"])
    if expires_at <= now_utc():
        return f"claim {rel(claim_path, root)} is expired and must be broken explicitly"
    same_agent = claim.get("agent_id") == data.get("agent_id")
    same_operation = claim.get("operation_id") == data.get("operation_id")
    if not (same_agent and same_operation):
        return f"active claim held by {claim.get('agent_id')} for {claim.get('operation_id')}"
    return None


def precondition_conflict(root: Path, data: dict[str, Any]) -> str | None:
    expected = data.get("precondition_hash")
    target_path = data.get("target_path")
    if data.get("op") in {"update_fact", "archive_fact"} and not expected:
        return f"{data.get('op')} requires precondition_hash"
    if not expected or not target_path:
        return None
    target = root / target_path
    if not target.exists():
        return f"target does not exist: {target_path}"
    actual = file_hash(target)
    if actual != expected:
        return f"precondition hash mismatch: expected {expected}, got {actual}"
    return None


def mark_operation(root: Path, path: Path, data: dict[str, Any], body: str, status: str, extra: dict[str, Any] | None = None) -> None:
    updated = dict(data)
    updated["status"] = status
    if extra:
        updated.update(extra)
    if status == "applied":
        updated["applied_at"] = iso(now_utc())
        target = root / "memory/_ops/applied" / f"{updated['operation_id']}.md"
        write_markdown(target, updated, body)
        path.unlink()
    else:
        write_markdown(path, updated, body)


def apply_create_or_update(root: Path, data: dict[str, Any], update: bool) -> str | None:
    target_path = data.get("target_path")
    source_payload = data.get("payload")
    if not target_path or not isinstance(source_payload, dict):
        return "operation requires target_path and payload"
    payload = dict(source_payload)
    target = root / target_path
    if update and not target.exists():
        return f"target does not exist: {target_path}"
    if not update and target.exists():
        return f"target already exists: {target_path}"
    body = payload.pop("body", "") if "body" in payload else ""
    write_markdown(target, payload, body)
    return None


def apply_add_event(root: Path, data: dict[str, Any]) -> str | None:
    return apply_create_or_update(root, data, update=False)


def apply_archive_fact(root: Path, data: dict[str, Any]) -> str | None:
    target_path = data.get("target_path")
    if not target_path:
        return "archive_fact requires target_path"
    target = root / target_path
    if not target.exists():
        return f"target does not exist: {target_path}"
    fact, _ = split_frontmatter(target)
    valid_to = parse_date(fact.get("valid_to"))
    today = dt.date.fromisoformat(__import__("os").environ.get("MEMORY_TODAY", dt.date.today().isoformat()))
    archive_year = str((valid_to or today).year)
    archive_target = root / "memory/_archive" / archive_year / target.relative_to(root / "memory")
    if archive_target.exists():
        return f"archive target already exists: {rel(archive_target, root)}"
    archive_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(target), str(archive_target))
    return None


def apply_operation(root: Path, path: Path, assume_yes: bool) -> tuple[bool, bool]:
    data, body = split_frontmatter(path)
    if data.get("type") != "operation" or data.get("status") != "proposed":
        return False, False

    conflict = active_claim_conflict(root, data) or precondition_conflict(root, data)
    if conflict:
        mark_operation(root, path, data, body, "conflict", {"conflict_reason": conflict})
        print(f"Conflict: {rel(path, root)}: {conflict}")
        return False, True

    op = data.get("op")
    if not confirm(f"Apply {op} {data.get('operation_id')}?", assume_yes):
        return False, False

    if op == "create_fact":
        conflict = apply_create_or_update(root, data, update=False)
    elif op == "update_fact":
        conflict = apply_create_or_update(root, data, update=True)
    elif op == "add_event":
        conflict = apply_add_event(root, data)
    elif op == "archive_fact":
        conflict = apply_archive_fact(root, data)
    elif op in {"review_fact", "rename_entity", "add_entity", "add_predicate"}:
        conflict = f"{op} is proposed-only in this reference implementation"
    else:
        conflict = f"unsupported operation {op!r}"

    if conflict:
        mark_operation(root, path, data, body, "conflict", {"conflict_reason": conflict})
        print(f"Conflict: {rel(path, root)}: {conflict}")
        return False, True

    mark_operation(root, path, data, body, "applied")
    print(f"Applied: {rel(path, root)}")
    return True, False


def apply_operations(root: Path, assume_yes: bool) -> tuple[int, int]:
    applied = 0
    conflicts = 0
    inbox = root / "memory/_inbox"
    for path in sorted(inbox.rglob("*.md")):
        data, _ = split_frontmatter(path)
        if data.get("type") != "operation":
            continue
        did_apply, did_conflict = apply_operation(root, path, assume_yes)
        applied += int(did_apply)
        conflicts += int(did_conflict)
    return applied, conflicts


def move_legacy_inbox(root: Path, assume_yes: bool) -> int:
    moved = 0
    inbox = root / "memory/_inbox"
    for path in sorted(inbox.rglob("*.md")):
        data, _ = split_frontmatter(path)
        if data.get("type") == "operation":
            continue
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
    applied, conflicts = apply_operations(root, args.yes)
    moved = move_legacy_inbox(root, args.yes)
    archived = archive_expired(root, args.yes)
    if applied or moved or archived or conflicts:
        if run([sys.executable, "tools/rebuild_views.py"]) != 0:
            return 1
        if run([sys.executable, "tools/lint.py"]) != 0:
            return 1
    print(f"Applied operations: {applied}")
    print(f"Operation conflicts: {conflicts}")
    print(f"Moved legacy inbox entries: {moved}")
    print(f"Archived expired facts: {archived}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
