#!/usr/bin/env python3
"""Offline transactions: begin/add/commit/rollback/recover/list."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

from lint import AGENT_ID_RE, SLUG_RE, file_hash, parse_date, parse_datetime, split_frontmatter, validate
from memory_model import FACT_FIELDS, confidence, current, enabled, enforce_trust, observed, parse_confidence, safe_path


OPS = ("create_fact", "update_fact", "supersede_fact", "create_event", "archive_fact")


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(value: dt.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def slugify(value: str, limit: int = 24) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:limit] or "change"


def markdown(data: dict[str, Any], body: str = "") -> str:
    return f"---\n{yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip()}\n---\n\n{body.rstrip()}\n"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write_markdown(path: Path, data: dict[str, Any], body: str = "") -> None:
    write_text(path, markdown(data, body))


def normalize_agent(value: str | None) -> str:
    if value is None:
        return "agent-local-1234abcd"
    if not AGENT_ID_RE.fullmatch(value):
        raise ValueError("agent must be a stable agent-name-<8hex> ID declared in roles.yaml")
    return value


def staging_dir(root: Path, txn_id: str) -> Path:
    if not re.fullmatch(r"txn-[a-z0-9][a-z0-9_-]*", txn_id):
        raise ValueError(f"invalid transaction ID: {txn_id!r}")
    return safe_path(root, f"memory/_staging/{txn_id}")


def load_staging_meta(root: Path, txn_id: str) -> dict[str, Any]:
    path = staging_dir(root, txn_id) / "_meta.yaml"
    if not path.exists():
        raise ValueError(f"transaction not found: {txn_id}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid transaction metadata: {txn_id}")
    return data


def save_staging_meta(root: Path, txn_id: str, meta: dict[str, Any]) -> None:
    write_text(staging_dir(root, txn_id) / "_meta.yaml", yaml.safe_dump(meta, sort_keys=False))


def find_committed_journal(root: Path, key: str) -> Path | None:
    for path in sorted((root / "memory/_transactions").glob("*.md")):
        data, _ = split_frontmatter(path)
        if data.get("idempotency_key") == key and data.get("status") == "committed":
            return path
    return None


def git_head(root: Path) -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def begin(root: Path, key: str, agent: str, expected_revision: str | None = None) -> dict[str, Any]:
    if not key.strip():
        raise ValueError("idempotency key must not be empty")
    prior = find_committed_journal(root, key)
    if prior:
        data, _ = split_frontmatter(prior)
        return data
    for path in sorted((root / "memory/_staging").glob("*/_meta.yaml")):
        data = load_staging_meta(root, path.parent.name)
        if data.get("idempotency_key") == key:
            if data.get("agent_id") != agent or data.get("expected_revision") != expected_revision:
                raise ValueError("pending idempotency key belongs to a different agent/revision")
            return data
    suffix = hashlib.sha256(key.encode()).hexdigest()[:8]
    txn_id = f"txn-{slugify(key)}-{utc_now().strftime('%Y%m%dt%H%M%Sz')}-{suffix}"
    meta = {
        "transaction_id": txn_id, "idempotency_key": key, "agent_id": normalize_agent(agent),
        "created_at": iso(utc_now()), "expected_revision": expected_revision,
        "status": "pending", "ops": [],
    }
    save_staging_meta(root, txn_id, meta)
    write_text(staging_dir(root, txn_id) / ".pending", "pending\n")
    return meta


def operation_arguments(parser: argparse.ArgumentParser, required: bool = True) -> None:
    parser.add_argument("--op", required=required, choices=OPS)
    for name in ("entity", "predicate", "value", "source", "valid-from", "valid-until",
                 "valid-until-previous", "observed-at", "last-confirmed", "review-after",
                 "event-id", "summary", "occurred-at", "body"):
        parser.add_argument(f"--{name}")
    parser.add_argument("--confidence", type=parse_confidence)
    parser.add_argument("--assertion", choices=["stated", "inferred", "observed"])
    parser.add_argument("--trust", choices=["owner", "agent", "external"])
    parser.add_argument("--derived-from", action="append")
    parser.add_argument("--entities", nargs="+")
    parser.add_argument("--asserts", help="YAML list of structured event assertions")
    parser.add_argument("--pinned", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--reason", default="")


def operation_from_args(args: argparse.Namespace) -> dict[str, Any]:
    keys = ("op", "entity", "predicate", "value", "valid_until_previous", "event_id",
            "summary", "occurred_at", "body", "entities", "reason", *FACT_FIELDS)
    op = {key: getattr(args, key) for key in keys if getattr(args, key, None) is not None}
    if getattr(args, "source", None):
        op["sources"] = [args.source]
    if getattr(args, "asserts", None):
        op["asserts"] = yaml.safe_load(args.asserts)
    return op


def prepare_operations(root: Path, meta: dict[str, Any], reviewed: bool = False) -> dict[str, str | None]:
    writes: dict[str, str | None] = {}
    for index, op in enumerate(meta["ops"]):
        kind = op.get("op")
        if kind not in OPS:
            raise ValueError(f"unsupported op: {kind!r}")
        if kind == "create_event":
            event_id = op.get("event_id")
            if not event_id or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", event_id):
                raise ValueError("create_event requires --event-id with a stable slug")
            occurred = parse_datetime(op.get("occurred_at")).astimezone(dt.timezone.utc)
            if not op.get("summary"):
                raise ValueError("create_event requires --summary")
            target = f"memory/events/{occurred.date()}/{event_id}.md"
            if safe_path(root, target).exists() or target in writes:
                raise ValueError(f"append-only event already exists: {target}")
            data = {"type": "event", "id": event_id, "summary": op["summary"],
                    "occurred_at": iso(occurred), "entities": op.get("entities", []),
                    "sources": op.get("sources", [])}
            if "asserts" in op:
                data["asserts"] = op["asserts"]
            writes[target] = markdown(data, op.get("body", ""))
            continue
        entity, predicate = op.get("entity"), op.get("predicate")
        if not all(isinstance(v, str) and SLUG_RE.fullmatch(v) for v in (entity, predicate)):
            raise ValueError("fact ops require slug --entity and --predicate")
        target = f"memory/facts/{entity}/{predicate}.md"
        canonical = safe_path(root, target)
        if target in writes:
            raise ValueError("one operation per fact slot per transaction; use consecutive transactions")
        exists = canonical.exists()
        if kind == "create_fact" and exists:
            raise ValueError(f"target already exists: {target}; use supersede_fact")
        if kind != "create_fact" and not exists:
            raise ValueError(f"target does not exist: {target}")
        if op.get("precondition_hash") and (not exists or file_hash(canonical) != op["precondition_hash"]):
            raise ValueError(f"precondition hash mismatch on {target}")
        old, body = split_frontmatter(canonical) if exists else ({}, "")
        if kind == "archive_fact":
            if enabled(root):
                raise ValueError("v4.1 retains history; use supersede_fact, not archive_fact")
            destination = f"memory/_archive/{utc_now().year}/facts/{entity}/{predicate}.md"
            if safe_path(root, destination).exists():
                raise ValueError(f"archive destination already exists: {destination}")
            writes[destination], writes[target] = canonical.read_text(encoding="utf-8"), None
            continue
        if "value" not in op:
            raise ValueError("fact ops require --value")
        if kind == "update_fact" and enabled(root) and op["value"] != old.get("value"):
            raise ValueError("changing a fact value requires supersede_fact to preserve history")
        data = dict(old) if kind == "update_fact" else {
            "type": "fact", "id": f"fact-{entity}-{predicate}",
            "entity": entity, "predicate": predicate, "value": op["value"],
            "valid_from": None, "valid_to": None, "recorded_at": meta["created_at"],
            "sources": op.get("sources", []), "last_reviewed": str(meta["created_at"])[:10],
        }
        if kind == "supersede_fact":
            if not enabled(root):
                raise ValueError("supersede_fact requires spec_version: '4.1'")
            start = parse_date(op.get("valid_from"))
            if start is None or not current(old):
                raise ValueError("supersede_fact requires --valid-from and a current fact")
            end = parse_date(op.get("valid_until_previous")) or start
            if abs((end - start).days) > 1:
                raise ValueError("previous valid_until must equal valid_from (one-day tolerance)")
            old_start = parse_date(old.get("valid_from"))
            if old_start and (start < old_start or end < old_start):
                raise ValueError("supersession cannot precede the previous valid_from")
            date = old_start or observed(old).date()
            base = f"memory/facts/{entity}/{predicate}/{date}"
            history, collision = f"{base}.md", 1
            while safe_path(root, history).exists() or history in writes:
                collision += 1
                history = f"{base}-{collision}.md"
            previous = dict(old, valid_until=end.isoformat())
            previous["valid_to"] = None
            writes[history] = markdown(previous, body)
            data["valid_until"] = None
            data["supersedes"] = history
            data["id"] = f"fact-{entity}-{predicate}-{start}-{hashlib.sha256((meta['transaction_id'] + str(index)).encode()).hexdigest()[:8]}"
        for field in (*FACT_FIELDS, "sources", "recorded_at", "created_at", "last_reviewed", "tags", "decay"):
            if field in op:
                data[field] = op[field]
        if "id" in op and kind == "create_fact":
            data["id"] = op["id"]
        if enabled(root):
            data["agent_id"] = meta["agent_id"]
            confidence(data.get("confidence"))
            enforce_trust(root, data, meta["agent_id"], reviewed)
        else:
            data.setdefault("confidence", "medium")
        writes[target] = markdown(data, op.get("body", body if kind == "update_fact" else ""))
    return writes


def validate_candidate(root: Path, writes: dict[str, str | None]) -> None:
    with tempfile.TemporaryDirectory(prefix="memory-candidate-") as tmp:
        candidate = Path(tmp)
        for folder in ("memory", "sources"):
            if (root / folder).exists():
                shutil.copytree(root / folder, candidate / folder,
                                ignore=shutil.ignore_patterns("_staging", "_views", "_indexes"))
        for relative, content in writes.items():
            path = candidate / relative
            if content is None:
                path.unlink()
            else:
                write_text(path, content)
        errors = [str(f) for f in validate(candidate) if f.level == "ERROR"]
        if errors:
            raise ValueError("candidate vault failed lint:\n" + "\n".join(errors))


def write_journal(root: Path, meta: dict[str, Any], status: str, reason: str | None = None) -> None:
    data = {key: meta.get(key) for key in ("transaction_id", "idempotency_key", "agent_id", "created_at",
                                          "expected_revision", "ops")}
    data.update(type="transaction", status=status, failure_reason=reason,
                committed_revision=git_head(root), committed_at=iso(utc_now()) if status == "committed" else None)
    write_markdown(root / "memory/_transactions" / f"{meta['transaction_id']}.md", data,
                   f"# Transaction: {meta['transaction_id']}\n\nStatus: **{status}**")


def restore(root: Path, meta: dict[str, Any]) -> None:
    staging = staging_dir(root, meta["transaction_id"])
    paths = list(dict.fromkeys([*meta.get("applied", []), *([meta["inflight"]] if meta.get("inflight") else [])]))
    for relative in reversed(paths):
        target = safe_path(root, relative)
        before = staging / "_before" / relative
        expected_before = meta["before"][relative]
        actual = file_hash(target) if target.exists() else None
        if actual not in (expected_before, meta["after"][relative]):
            raise ValueError(f"recovery refuses to overwrite a later edit: {relative}; staging retained")
        if actual == expected_before:
            continue
        if before.exists():
            write_text(target, before.read_text(encoding="utf-8"))
        elif target.exists():
            target.unlink()


def publish(root: Path, meta: dict[str, Any], writes: dict[str, str | None]) -> None:
    """Durable preimages and progress make partial publication recoverable."""
    staging = staging_dir(root, meta["transaction_id"])
    meta.update(status="prepared", before={}, after={}, applied=[], inflight=None)
    for relative, content in writes.items():
        target = safe_path(root, relative, ("memory/",))
        meta["before"][relative] = file_hash(target) if target.exists() else None
        if target.exists():
            backup = staging / "_before" / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target, backup)
        if content is not None:
            write_text(staging / relative, content)
            meta["after"][relative] = file_hash(staging / relative)
        else:
            meta["after"][relative] = None
    save_staging_meta(root, meta["transaction_id"], meta)
    try:
        for relative, content in writes.items():
            target = safe_path(root, relative)
            actual = file_hash(target) if target.exists() else None
            if actual != meta["before"][relative]:
                raise ValueError(f"concurrent edit before publication: {relative}")
            meta["inflight"] = relative
            save_staging_meta(root, meta["transaction_id"], meta)
            if content is None:
                target.unlink()
            else:
                write_text(target, content)
            meta["applied"].append(relative)
            meta["inflight"] = None
            save_staging_meta(root, meta["transaction_id"], meta)
        write_journal(root, meta, "committed")
    except (OSError, ValueError) as exc:
        restore(root, meta)
        write_journal(root, meta, "failed", str(exc))
        shutil.rmtree(staging)
        raise
    shutil.rmtree(staging)


def commit_records(root: Path, key: str, agent: str, writes: dict[str, str]) -> str:
    """Proposal/review metadata uses the same journal and recovery path."""
    for relative in writes:
        safe_path(root, relative, ("memory/_proposals/", "memory/_reviews/"))
    meta = begin(root, key, agent)
    if meta["status"] != "committed":
        meta["ops"] = [{"op": "record_review_state", "target_path": path} for path in sorted(writes)]
        publish(root, meta, writes)
    return meta["transaction_id"]


def cmd_begin(root: Path, args: argparse.Namespace) -> int:
    meta = begin(root, args.idempotency_key, normalize_agent(args.agent), args.expected_revision)
    label = "Idempotent skip" if meta["status"] == "committed" else "Transaction started"
    print(f"{label}: {meta['transaction_id']}")
    return 0


def cmd_add(root: Path, args: argparse.Namespace) -> int:
    meta = load_staging_meta(root, args.txn_id)
    if meta["status"] != "pending":
        raise ValueError("transaction is not pending; recover before retrying")
    op = operation_from_args(args)
    if op["op"] in {"update_fact", "supersede_fact", "archive_fact"}:
        target = safe_path(root, f"memory/facts/{op.get('entity')}/{op.get('predicate')}.md")
        if target.exists():
            op["precondition_hash"] = file_hash(target)
    meta["ops"].append(op)
    # Trust is enforced at commit too, using the current policy.
    prepare_operations(root, meta, reviewed=True)
    save_staging_meta(root, args.txn_id, meta)
    print(f"Added {op['op']}: {op.get('entity', op.get('event_id', ''))}/{op.get('predicate', '')}")
    return 0


def commit(root: Path, meta: dict[str, Any], reviewed: bool = False) -> None:
    if meta["status"] != "pending":
        raise ValueError("transaction is not pending")
    if find_committed_journal(root, meta["idempotency_key"]):
        shutil.rmtree(staging_dir(root, meta["transaction_id"]))
        return
    expected = meta.get("expected_revision")
    if expected and git_head(root) != expected:
        raise ValueError("Git revision mismatch or Git unavailable")
    if not meta["ops"]:
        raise ValueError("cannot commit an empty transaction")
    writes = prepare_operations(root, meta, reviewed)
    validate_candidate(root, writes)
    publish(root, meta, writes)


def cmd_commit(root: Path, args: argparse.Namespace) -> int:
    meta = load_staging_meta(root, args.txn_id)
    if not args.yes and input(f"Commit {args.txn_id}? [y/N] ").lower() not in {"y", "yes"}:
        print("Cancelled.", file=sys.stderr)
        return 1
    commit(root, meta)
    print(f"Transaction {args.txn_id} committed ({len(meta['ops'])} op(s))")
    return 0


def rollback(root: Path, txn_id: str) -> None:
    meta = load_staging_meta(root, txn_id)
    journal = root / "memory/_transactions" / f"{txn_id}.md"
    if journal.exists() and split_frontmatter(journal)[0].get("status") == "committed":
        shutil.rmtree(staging_dir(root, txn_id))
        return
    restore(root, meta)
    write_journal(root, meta, "rolled_back")
    shutil.rmtree(staging_dir(root, txn_id))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("begin")
    p.add_argument("--idempotency-key", required=True)
    p.add_argument("--agent", default=None)
    p.add_argument("--expected-revision")
    p = sub.add_parser("add")
    p.add_argument("--txn-id", required=True)
    operation_arguments(p)
    p = sub.add_parser("commit")
    p.add_argument("--txn-id", required=True)
    p.add_argument("--yes", action="store_true")
    p = sub.add_parser("rollback")
    p.add_argument("--txn-id", required=True)
    p = sub.add_parser("recover")
    p.add_argument("--yes", action="store_true")
    sub.add_parser("list")
    args = parser.parse_args()
    root = Path.cwd()
    try:
        if args.command in {"begin", "add", "commit"}:
            return {"begin": cmd_begin, "add": cmd_add, "commit": cmd_commit}[args.command](root, args)
        if args.command == "rollback":
            rollback(root, args.txn_id)
            print(f"Transaction {args.txn_id} rolled back")
        elif args.command == "recover":
            for path in sorted((root / "memory/_staging").glob("*/.pending")):
                if args.yes or input(f"Roll back {path.parent.name}? [y/N] ").lower() in {"y", "yes"}:
                    rollback(root, path.parent.name)
                    print(f"Recovered: {path.parent.name}")
        else:
            for path in sorted((root / "memory/_transactions").glob("*.md")):
                data, _ = split_frontmatter(path)
                print(f"{data.get('status')}  {data.get('transaction_id')}  [{data.get('idempotency_key')}]")
            for path in sorted((root / "memory/_staging").glob("*/_meta.yaml")):
                print(f"pending  {path.parent.name}")
        return 0
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
