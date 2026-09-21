#!/usr/bin/env python3
"""V4 Git-native transaction manager.

Transactions provide:
  - Stable transaction IDs and caller-supplied idempotency keys
  - Optional expected-revision (Git SHA) check before commit
  - Isolated staging under memory/_staging/<txn-id>/ before publication
  - Markdown journal/receipt in memory/_transactions/<txn-id>.md
  - Deterministic recovery from interrupted or failed transactions
  - Idempotent replay: a committed key is a no-op

Usage:
  transact.py begin   --idempotency-key KEY [--expected-revision SHA] [--agent AGENT]
  transact.py add     --txn-id TXNID --op OP --entity E --predicate P --value V
                      [--source S] [--confidence C] [--reason TEXT]
  transact.py commit  --txn-id TXNID [--yes]
  transact.py rollback --txn-id TXNID
  transact.py recover [--yes]
  transact.py list
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AGENT_ID_RE = re.compile(r"^agent-[a-z0-9-]+-[a-f0-9]{8,}$")
TXN_ID_RE = re.compile(r"^txn-[a-z0-9][a-z0-9_-]*$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(value: dt.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def slugify(text: str, limit: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:limit] or "txn"


def new_txn_id(key: str) -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ").lower()
    suffix = secrets.token_hex(4)
    slug = slugify(key, 24)
    return f"txn-{slug}-{stamp}-{suffix}"


def normalize_agent(value: str | None) -> str:
    if value and AGENT_ID_RE.match(value):
        return value
    base = slugify(value or "local", 30)
    return f"agent-{base}-{secrets.token_hex(4)}"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def split_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    data = yaml.safe_load(match.group(1)) or {}
    if not isinstance(data, dict):
        return {}, text[match.end():]
    return data, text[match.end():]


def write_markdown(path: Path, frontmatter_data: dict[str, Any], body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = f"---\n{yaml.safe_dump(frontmatter_data, sort_keys=False, allow_unicode=True).strip()}\n---\n"
    if body:
        text += f"\n{body.rstrip()}\n"
    else:
        text += "\n"
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    answer = input(f"{prompt} [y/N] ")
    return answer.lower() in {"y", "yes"}


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def git_head(root: Path) -> str | None:
    """Return the current HEAD SHA if Git is available, else None."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def git_is_clean(root: Path) -> tuple[bool, str]:
    """Return (is_clean, status_summary). Checks working tree against HEAD."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return True, ""  # no git info, treat as clean
        lines = [l for l in result.stdout.splitlines() if l.strip() and not l.startswith("??")]
        return (len(lines) == 0), "\n".join(lines)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return True, ""


# ---------------------------------------------------------------------------
# Idempotency check
# ---------------------------------------------------------------------------


def find_committed_journal(root: Path, idempotency_key: str) -> Path | None:
    """Return an existing committed journal with this key, or None."""
    txn_dir = root / "memory/_transactions"
    if not txn_dir.exists():
        return None
    for path in txn_dir.glob("*.md"):
        data, _ = split_frontmatter(path)
        if (data.get("type") == "transaction"
                and data.get("idempotency_key") == idempotency_key
                and data.get("status") == "committed"):
            return path
    return None


# ---------------------------------------------------------------------------
# Staging helpers
# ---------------------------------------------------------------------------


def staging_dir(root: Path, txn_id: str) -> Path:
    return root / "memory/_staging" / txn_id


def pending_marker(root: Path, txn_id: str) -> Path:
    return staging_dir(root, txn_id) / ".pending"


def load_staging_meta(root: Path, txn_id: str) -> dict[str, Any]:
    meta_path = staging_dir(root, txn_id) / "_meta.yaml"
    if not meta_path.exists():
        return {}
    return yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}


def save_staging_meta(root: Path, txn_id: str, meta: dict[str, Any]) -> None:
    staging = staging_dir(root, txn_id)
    staging.mkdir(parents=True, exist_ok=True)
    path = staging / "_meta.yaml"
    path.write_text(yaml.safe_dump(meta, sort_keys=False, allow_unicode=True), encoding="utf-8")


def write_journal(root: Path, txn_id: str, meta: dict[str, Any], status: str,
                  failure_reason: str | None = None, committed_revision: str | None = None) -> None:
    fm = {
        "type": "transaction",
        "transaction_id": txn_id,
        "idempotency_key": meta.get("idempotency_key", ""),
        "agent_id": meta.get("agent_id", ""),
        "created_at": meta.get("created_at", iso(utc_now())),
        "status": status,
        "expected_revision": meta.get("expected_revision"),
        "committed_revision": committed_revision,
        "failure_reason": failure_reason,
        "committed_at": iso(utc_now()) if status == "committed" else None,
        "ops": meta.get("ops", []),
    }
    n_ops = len(fm["ops"])
    body = f"# Transaction: {txn_id}\n\n"
    body += f"Status: **{status}**\n\n"
    if status == "committed":
        body += f"Applied {n_ops} operation(s) atomically.\n\n"
        body += f"Idempotency key `{fm['idempotency_key']}` — replaying this key is a no-op while this journal exists.\n"
    elif status == "rolled_back":
        body += "Staging area cleared; no canonical files were modified.\n"
    elif status == "failed":
        body += f"Failure reason: {failure_reason}\n"
    elif status == "idempotent_skip":
        body += f"Skipped — idempotency key `{fm['idempotency_key']}` was already committed.\n"
    journal_path = root / "memory/_transactions" / f"{txn_id}.md"
    write_markdown(journal_path, fm, body)


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


def apply_staged_op(root: Path, staging: Path, op_desc: dict[str, Any]) -> str | None:
    """Apply one staged operation to canonical memory/. Returns error string or None."""
    op = op_desc.get("op")
    target_path = op_desc.get("target_path")
    if not target_path:
        return f"op has no target_path: {op_desc!r}"

    canonical_target = root / target_path

    if op == "create_fact":
        staged_file = staging / target_path
        if not staged_file.exists():
            return f"staged file not found: {staged_file}"
        if canonical_target.exists():
            return f"target already exists: {target_path}"
        canonical_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(staged_file), str(canonical_target))
        return None

    if op == "update_fact":
        staged_file = staging / target_path
        if not staged_file.exists():
            return f"staged file not found: {staged_file}"
        expected_hash = op_desc.get("precondition_hash")
        if expected_hash:
            if not canonical_target.exists():
                return f"target does not exist for update: {target_path}"
            actual = file_hash(canonical_target)
            if actual != expected_hash:
                return f"precondition hash mismatch on {target_path}: expected {expected_hash}, got {actual}"
        canonical_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(staged_file), str(canonical_target))
        return None

    if op == "archive_fact":
        if not canonical_target.exists():
            return f"target does not exist for archive: {target_path}"
        archive_year = str(utc_now().year)
        archive_dest = root / "memory/_archive" / archive_year / Path(target_path).relative_to("memory")
        if archive_dest.exists():
            return f"archive destination already exists: {archive_dest}"
        archive_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(canonical_target), str(archive_dest))
        return None

    return f"unsupported op {op!r}"


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_begin(root: Path, args: argparse.Namespace) -> int:
    key = args.idempotency_key
    existing = find_committed_journal(root, key)
    if existing:
        print(f"Idempotent skip: key '{key}' already committed in {existing}")
        return 0

    txn_id = new_txn_id(key)
    meta: dict[str, Any] = {
        "transaction_id": txn_id,
        "idempotency_key": key,
        "agent_id": normalize_agent(getattr(args, "agent", None)),
        "created_at": iso(utc_now()),
        "expected_revision": getattr(args, "expected_revision", None),
        "status": "pending",
        "ops": [],
    }
    staging = staging_dir(root, txn_id)
    staging.mkdir(parents=True, exist_ok=True)
    pending_marker(root, txn_id).write_text("pending\n", encoding="utf-8")
    save_staging_meta(root, txn_id, meta)
    print(f"Transaction started: {txn_id}")
    print(f"  idempotency_key: {key}")
    print(f"  staging: {staging.relative_to(root)}")
    return 0


def cmd_add(root: Path, args: argparse.Namespace) -> int:
    txn_id = args.txn_id
    meta = load_staging_meta(root, txn_id)
    if not meta:
        print(f"ERROR: transaction not found: {txn_id}", file=sys.stderr)
        return 1
    if meta.get("status") != "pending":
        print(f"ERROR: transaction {txn_id} is not pending (status={meta.get('status')})", file=sys.stderr)
        return 1

    op = args.op
    entity = getattr(args, "entity", None)
    predicate = getattr(args, "predicate", None)
    value = getattr(args, "value", None)
    source = getattr(args, "source", None)
    confidence = getattr(args, "confidence", "medium")
    reason = getattr(args, "reason", "")

    if op in {"create_fact", "update_fact"}:
        if not all([entity, predicate, value]):
            print("ERROR: --entity, --predicate, and --value are required for fact ops", file=sys.stderr)
            return 1
        target_path = f"memory/facts/{entity}/{predicate}.md"
        now_str = iso(utc_now())
        payload_fm: dict[str, Any] = {
            "type": "fact",
            "id": f"fact-{entity}-{predicate}",
            "entity": entity,
            "predicate": predicate,
            "value": value,
            "valid_from": None,
            "valid_to": None,
            "recorded_at": now_str,
            "confidence": confidence,
            "sources": [source] if source else [],
            "last_reviewed": now_str[:10],
        }
        precondition_hash = None
        if op == "update_fact":
            canonical = root / target_path
            if canonical.exists():
                precondition_hash = file_hash(canonical)
        # Write staged file
        staged_path = staging_dir(root, txn_id) / target_path
        write_markdown(staged_path, payload_fm)
        op_desc: dict[str, Any] = {
            "op": op,
            "entity": entity,
            "predicate": predicate,
            "value": value,
            "target_path": target_path,
        }
        if precondition_hash:
            op_desc["precondition_hash"] = precondition_hash
        meta["ops"].append(op_desc)
        save_staging_meta(root, txn_id, meta)
        print(f"Added {op}: {target_path}")
        return 0

    print(f"ERROR: unsupported op {op!r} for 'add'", file=sys.stderr)
    return 1


def cmd_commit(root: Path, args: argparse.Namespace) -> int:
    txn_id = args.txn_id
    meta = load_staging_meta(root, txn_id)
    if not meta:
        print(f"ERROR: transaction not found: {txn_id}", file=sys.stderr)
        return 1
    if meta.get("status") != "pending":
        print(f"ERROR: transaction {txn_id} is not pending (status={meta.get('status')})", file=sys.stderr)
        return 1

    # Idempotency guard
    existing = find_committed_journal(root, meta["idempotency_key"])
    if existing:
        print(f"Idempotent skip: key '{meta['idempotency_key']}' already committed in {existing}")
        # clean up staging
        shutil.rmtree(str(staging_dir(root, txn_id)), ignore_errors=True)
        return 0

    # Expected revision check
    expected_revision = meta.get("expected_revision")
    committed_revision: str | None = None
    if expected_revision:
        current = git_head(root)
        if current is None:
            print("ERROR: expected_revision provided but Git is not available", file=sys.stderr)
            write_journal(root, txn_id, meta, "failed",
                          failure_reason="expected_revision provided but Git unavailable")
            shutil.rmtree(str(staging_dir(root, txn_id)), ignore_errors=True)
            return 1
        if current != expected_revision:
            msg = f"Git revision mismatch: expected {expected_revision}, current HEAD is {current}"
            print(f"ERROR: {msg}", file=sys.stderr)
            write_journal(root, txn_id, meta, "failed", failure_reason=msg)
            shutil.rmtree(str(staging_dir(root, txn_id)), ignore_errors=True)
            return 1
        committed_revision = current
    else:
        committed_revision = git_head(root)  # record current rev even if not checked

    ops = meta.get("ops", [])
    if not ops:
        print("WARNING: no operations in transaction — committing empty transaction")

    assume_yes = getattr(args, "yes", False)
    if not confirm(f"Commit transaction {txn_id} ({len(ops)} op(s))?", assume_yes):
        return 0

    staging = staging_dir(root, txn_id)

    # Apply all operations atomically (best-effort: on first error, roll back applied)
    applied: list[str] = []
    error: str | None = None
    for op_desc in ops:
        err = apply_staged_op(root, staging, op_desc)
        if err:
            error = err
            break
        applied.append(op_desc.get("target_path", "?"))

    if error:
        # Rollback what we applied
        print(f"ERROR during commit: {error}", file=sys.stderr)
        print("Rolling back applied operations...", file=sys.stderr)
        for target_path in reversed(applied):
            target = root / target_path
            if target.exists():
                target.unlink()
                print(f"  Rolled back: {target_path}", file=sys.stderr)
        write_journal(root, txn_id, meta, "failed", failure_reason=error)
        shutil.rmtree(str(staging_dir(root, txn_id)), ignore_errors=True)
        return 1

    write_journal(root, txn_id, meta, "committed", committed_revision=committed_revision)
    shutil.rmtree(str(staging_dir(root, txn_id)), ignore_errors=True)
    print(f"Transaction {txn_id} committed ({len(ops)} op(s))")
    for target_path in [op_desc.get("target_path", "?") for op_desc in ops]:
        print(f"  Applied: {target_path}")
    return 0


def cmd_rollback(root: Path, args: argparse.Namespace) -> int:
    txn_id = args.txn_id
    meta = load_staging_meta(root, txn_id)
    if not meta:
        # Check if there's a staging directory without meta
        staging = staging_dir(root, txn_id)
        if staging.exists():
            shutil.rmtree(str(staging))
            print(f"Cleared staging directory for {txn_id} (no meta found)")
            return 0
        print(f"ERROR: transaction not found: {txn_id}", file=sys.stderr)
        return 1
    write_journal(root, txn_id, meta, "rolled_back")
    shutil.rmtree(str(staging_dir(root, txn_id)), ignore_errors=True)
    print(f"Transaction {txn_id} rolled back")
    return 0


def cmd_recover(root: Path, args: argparse.Namespace) -> int:
    """Find any pending staging transactions and roll them back (safe recovery)."""
    staging_base = root / "memory/_staging"
    if not staging_base.exists():
        print("No pending transactions found.")
        return 0
    assume_yes = getattr(args, "yes", False)
    found = False
    for txn_dir in sorted(staging_base.iterdir()):
        if not txn_dir.is_dir():
            continue
        marker = txn_dir / ".pending"
        if not marker.exists():
            continue
        txn_id = txn_dir.name
        found = True
        print(f"Found pending transaction: {txn_id}")
        meta = load_staging_meta(root, txn_id)
        if confirm(f"  Roll back {txn_id}?", assume_yes):
            write_journal(root, txn_id, meta or {"transaction_id": txn_id}, "rolled_back",
                          failure_reason="recovered from interrupted state")
            shutil.rmtree(str(txn_dir), ignore_errors=True)
            print(f"  Rolled back: {txn_id}")
        else:
            print(f"  Skipped: {txn_id}")
    if not found:
        print("No pending transactions found.")
    return 0


def cmd_list(root: Path, args: argparse.Namespace) -> int:
    txn_dir = root / "memory/_transactions"
    staging_base = root / "memory/_staging"
    rows: list[tuple[str, str, str, str]] = []

    if txn_dir.exists():
        for path in sorted(txn_dir.glob("*.md")):
            data, _ = split_frontmatter(path)
            if data.get("type") == "transaction":
                rows.append((
                    str(data.get("created_at", "")),
                    str(data.get("transaction_id", path.stem)),
                    str(data.get("status", "?")),
                    str(data.get("idempotency_key", "")),
                ))
    if staging_base.exists():
        for d in sorted(staging_base.iterdir()):
            if d.is_dir() and (d / ".pending").exists():
                meta = load_staging_meta(root, d.name)
                rows.append((
                    str(meta.get("created_at", "")),
                    d.name,
                    "PENDING (staging)",
                    str(meta.get("idempotency_key", "")),
                ))

    if not rows:
        print("No transactions found.")
        return 0
    rows.sort(key=lambda r: r[0], reverse=True)
    for created_at, txn_id, status, key in rows:
        print(f"{created_at[:19]}  {status:<22}  {txn_id}  [{key}]")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command")

    p_begin = sub.add_parser("begin", help="Start a new transaction")
    p_begin.add_argument("--idempotency-key", required=True, help="Stable caller-supplied deduplication key")
    p_begin.add_argument("--expected-revision", default=None, help="Git SHA that HEAD must match before commit")
    p_begin.add_argument("--agent", default=None, help="Agent ID (agent-name-<8hex>)")

    p_add = sub.add_parser("add", help="Add an operation to a pending transaction")
    p_add.add_argument("--txn-id", required=True)
    p_add.add_argument("--op", required=True, choices=["create_fact", "update_fact", "archive_fact"])
    p_add.add_argument("--entity", default=None)
    p_add.add_argument("--predicate", default=None)
    p_add.add_argument("--value", default=None)
    p_add.add_argument("--source", default=None)
    p_add.add_argument("--confidence", default="medium", choices=["high", "medium", "low"])
    p_add.add_argument("--reason", default="")

    p_commit = sub.add_parser("commit", help="Commit a pending transaction")
    p_commit.add_argument("--txn-id", required=True)
    p_commit.add_argument("--yes", action="store_true")

    p_rollback = sub.add_parser("rollback", help="Roll back a pending transaction")
    p_rollback.add_argument("--txn-id", required=True)

    p_recover = sub.add_parser("recover", help="Roll back any pending staged transactions")
    p_recover.add_argument("--yes", action="store_true")

    sub.add_parser("list", help="List all transactions")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = Path.cwd()

    if args.command == "begin":
        return cmd_begin(root, args)
    if args.command == "add":
        return cmd_add(root, args)
    if args.command == "commit":
        return cmd_commit(root, args)
    if args.command == "rollback":
        return cmd_rollback(root, args)
    if args.command == "recover":
        return cmd_recover(root, args)
    if args.command == "list":
        return cmd_list(root, args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
