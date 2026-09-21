#!/usr/bin/env python3
"""Create/list/show/apply review-gated proposals. Application uses transact.py."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

import yaml

import transact
from lint import file_hash, split_frontmatter
from memory_model import config, enforce_trust, safe_path
from transact import iso, normalize_agent, utc_now, write_markdown


VALID_STATUSES = ("draft", "proposed", "changes_requested", "approved", "rejected", "conflict", "applied")
CONSOLIDATOR = "agent-consolidate-00000001"


def content_hash_of(data: dict[str, Any]) -> str:
    fields = ("title", "namespace", "ops")
    if data.get("hash_version") == "4.1":
        fields += ("proposer_id",)
    text = yaml.safe_dump({key: data.get(key, "") for key in fields}, sort_keys=True, allow_unicode=True)
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def load_roles(root: Path) -> dict[str, Any]:
    return config(root, "roles.yaml")


def check_proposer_allowed(roles: dict[str, Any], namespace: str, proposer: str) -> str | None:
    if not roles:
        return None
    ns = next((entry for entry in roles.get("namespaces", []) if entry.get("id") == namespace), None)
    if ns is None:
        return f"unknown namespace {namespace!r}"
    admin = any(a.get("id") == proposer and "admin" in a.get("roles", []) for a in roles.get("agents", []))
    if ns.get("allowed_proposers") and proposer not in ns["allowed_proposers"] and not admin:
        return f"proposer {proposer!r} is not allowed in namespace {namespace!r}"
    return None


def _required_approvals(roles: dict[str, Any], namespace: str) -> int:
    ns = next((entry for entry in roles.get("namespaces", []) if entry.get("id") == namespace), {})
    value = ns.get("required_approvals", 1)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("required_approvals must be an integer >= 1")
    return value


def load_proposal(root: Path, prop_id: str) -> tuple[Path, dict[str, Any]]:
    path = safe_path(root, f"memory/_proposals/{prop_id}.md")
    if not path.is_file():
        raise ValueError(f"proposal not found: {prop_id}")
    data, _ = split_frontmatter(path)
    if data.get("proposal_id") != prop_id:
        raise ValueError("proposal ID does not match filename")
    return path, data


def valid_approvals(root: Path, data: dict[str, Any]) -> list[str]:
    from review import check_reviewer_allowed

    if data.get("content_hash") != content_hash_of(data):
        raise ValueError("proposal content_hash does not match its contents; review again")
    latest: dict[str, dict[str, Any]] = {}
    records = []
    for path in sorted((root / "memory/_reviews").glob("*.md")):
        review, _ = split_frontmatter(path)
        if review.get("proposal_id") == data["proposal_id"]:
            records.append((path, review))
    for _, review in sorted(records, key=lambda row: (str(row[1].get("created_at", "")), row[0].name)):
        if review.get("proposal_content_hash") == data["content_hash"]:
            latest[review.get("reviewer_id", "")] = review
    allowed = []
    roles = load_roles(root)
    for reviewer, review in latest.items():
        if reviewer == data.get("proposer_id"):
            raise ValueError("self-approval not allowed")
        if check_reviewer_allowed(roles, data["namespace"], reviewer):
            continue
        if review.get("verdict") == "approved":
            allowed.append(reviewer)
        elif review.get("verdict") in {"rejected", "changes_requested"}:
            raise ValueError("proposal has an unresolved rejection or change request")
    return sorted(allowed)


def create_proposal(root: Path, title: str, namespace: str, proposer: str,
                    ops: list[dict[str, Any]], status: str = "proposed",
                    key: str | None = None, diagnosis: dict[str, Any] | None = None) -> dict[str, Any]:
    roles = load_roles(root)
    diagnostic = proposer == CONSOLIDATOR and status == "draft" and not ops and diagnosis is not None
    error = check_proposer_allowed(roles, namespace, proposer)
    if error and not diagnostic:
        raise ValueError(error)
    if not diagnostic and not ops:
        raise ValueError("proposal requires at least one operation")
    if not isinstance(ops, list) or any(not isinstance(op, dict) or op.get("op") not in transact.OPS for op in ops):
        raise ValueError("ops must be a list of supported operation objects")
    if any(op["op"] != "create_event" for op in ops) and namespace != "facts":
        raise ValueError("fact operations must use namespace facts")
    if key:
        for path in sorted((root / "memory/_proposals").glob("*.md")):
            data, _ = split_frontmatter(path)
            if data.get("idempotency_key") == key:
                return data
    stamp = utc_now().strftime("%Y%m%dt%H%M%Sz")
    suffix = hashlib.sha256((key or title + iso(utc_now())).encode()).hexdigest()[:8]
    prop_id = f"prop-{transact.slugify(title, 20)}-{stamp}-{suffix}"
    for op in ops:
        if op["op"] in {"update_fact", "supersede_fact", "archive_fact"}:
            target = safe_path(root, f"memory/facts/{op.get('entity')}/{op.get('predicate')}.md")
            if not target.is_file():
                raise ValueError(f"target does not exist: {target.relative_to(root)}")
            op.setdefault("precondition_hash", file_hash(target))
    data = {
        "type": "proposal", "proposal_id": prop_id, "namespace": namespace,
        "proposer_id": normalize_agent(proposer), "title": title, "status": status,
        "created_at": iso(utc_now()), "hash_version": "4.1", "ops": ops,
        "required_approvals": _required_approvals(roles, namespace), "approvals": [],
        "applied_at": None, "transaction_id": None,
    }
    if key:
        data["idempotency_key"] = key
    if diagnosis:
        data["diagnosis"] = diagnosis
    data["content_hash"] = content_hash_of(data)
    body = f"# Proposal: {title}\n\nReview required; no canonical changes have been applied.\n"
    if diagnostic:
        body += "\nDiagnostic draft only. Supply a repair in a new proposal before review/application.\n"
    write_markdown(root / "memory/_proposals" / f"{prop_id}.md", data, body)
    return data


def cmd_create(root: Path, args: argparse.Namespace) -> int:
    if args.ops_file:
        if args.op:
            raise ValueError("use --op or --ops-file, not both")
        ops = yaml.safe_load(Path(args.ops_file).read_text(encoding="utf-8"))
    else:
        ops = [transact.operation_from_args(args)]
    data = create_proposal(root, args.title, args.namespace, args.proposer, ops, args.status, args.idempotency_key)
    print(f"Proposal created: {data['proposal_id']}")
    return 0


def cmd_apply(root: Path, args: argparse.Namespace) -> int:
    path, data = load_proposal(root, args.proposal_id)
    if data.get("status") == "applied":
        print(f"Proposal {args.proposal_id} already applied (idempotent skip).")
        return 0
    if data.get("status") != "approved":
        raise ValueError(f"proposal is not approved (status={data.get('status')!r})")
    roles = load_roles(root)
    error = check_proposer_allowed(roles, data["namespace"], data["proposer_id"])
    if error:
        raise ValueError(error)
    approvals = valid_approvals(root, data)
    if len(approvals) < _required_approvals(roles, data["namespace"]):
        raise ValueError("proposal does not have enough current, authorized, hash-bound approvals")
    if not data.get("ops"):
        raise ValueError("diagnostic draft has no executable repair operations")
    for op in data["ops"]:
        if op.get("op") != "create_event":
            if data["namespace"] != "facts":
                raise ValueError("fact operations must use namespace facts")
            enforce_trust(root, op, data["proposer_id"], reviewed=True)
    if not args.yes and input(f"Apply {args.proposal_id}? [y/N] ").lower() not in {"y", "yes"}:
        print("Cancelled.", file=sys.stderr)
        return 1
    meta = transact.begin(root, f"apply-proposal-{args.proposal_id}", data["proposer_id"])
    updated = dict(data, status="applied", applied_at=iso(utc_now()), transaction_id=meta["transaction_id"])
    if meta["status"] != "committed":
        meta["ops"] = data["ops"]
        transact.save_staging_meta(root, meta["transaction_id"], meta)
        writes = transact.prepare_operations(root, meta, reviewed=True)
        writes[path.relative_to(root).as_posix()] = transact.markdown(updated, f"# Proposal: {data['title']}\n\nStatus: **applied**")
        transact.validate_candidate(root, writes)
        transact.publish(root, meta, writes)
    print(f"Proposal {args.proposal_id} applied.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create")
    p.add_argument("--title", required=True)
    p.add_argument("--namespace", required=True)
    p.add_argument("--proposer", required=True)
    transact.operation_arguments(p, required=False)
    p.add_argument("--ops-file", help="YAML/JSON operation list")
    p.add_argument("--status", choices=["draft", "proposed"], default="proposed")
    p.add_argument("--idempotency-key")
    p = sub.add_parser("list")
    p.add_argument("--status", choices=VALID_STATUSES)
    p = sub.add_parser("show")
    p.add_argument("--proposal-id", required=True)
    p = sub.add_parser("apply")
    p.add_argument("--proposal-id", required=True)
    p.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    root = Path.cwd()
    try:
        if args.command == "create":
            return cmd_create(root, args)
        if args.command == "apply":
            return cmd_apply(root, args)
        if args.command == "show":
            path, _ = load_proposal(root, args.proposal_id)
            print(path.read_text(encoding="utf-8"), end="")
        else:
            for path in sorted((root / "memory/_proposals").glob("*.md")):
                data, _ = split_frontmatter(path)
                if not args.status or args.status == data.get("status"):
                    print(f"{data.get('status')}  {data.get('proposal_id')}  {data.get('title')}")
        return 0
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
