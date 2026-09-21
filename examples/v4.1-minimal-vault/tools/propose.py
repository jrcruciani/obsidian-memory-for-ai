#!/usr/bin/env python3
"""V4 proposal management tool.

Creates and manages formal proposals for changes to vault facts. Each proposal
goes through the review lifecycle before being applied via a transaction.

Usage:
  propose.py create  --title TITLE --namespace NS --proposer AGENT
                     --op OP --entity E --predicate P --value V
                     [--source S] [--confidence C]
  propose.py list    [--status STATUS]
  propose.py show    --proposal-id PROPID
  propose.py apply   --proposal-id PROPID [--yes]
"""

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


AGENT_ID_RE = re.compile(r"^agent-[a-z0-9-]+-[a-f0-9]{8,}$")
PROP_ID_RE = re.compile(r"^prop-[a-z0-9][a-z0-9_-]*$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)

VALID_STATUSES = {"draft", "proposed", "changes_requested", "approved", "rejected", "conflict", "applied"}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(value: dt.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def slugify(text: str, limit: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:limit] or "prop"


def normalize_agent(value: str | None) -> str:
    if value and AGENT_ID_RE.match(value):
        return value
    base = slugify(value or "local", 30)
    return f"agent-{base}-{secrets.token_hex(4)}"


def new_prop_id(title: str) -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ").lower()
    slug = slugify(title, 20)
    suffix = secrets.token_hex(4)
    return f"prop-{slug}-{stamp}-{suffix}"


def split_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    data = yaml.safe_load(match.group(1)) or {}
    if not isinstance(data, dict):
        return {}, text[match.end():]
    return data, text[match.end():]


def write_markdown(path: Path, fm: dict[str, Any], body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = f"---\n{yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()}\n---\n"
    if body:
        text += f"\n{body.rstrip()}\n"
    else:
        text += "\n"
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def content_hash_of(fm: dict[str, Any]) -> str:
    """Stable hash of proposal ops and title for cryptographic binding."""
    canonical = yaml.safe_dump({
        "title": fm.get("title", ""),
        "namespace": fm.get("namespace", ""),
        "ops": fm.get("ops", []),
    }, sort_keys=True, allow_unicode=True)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_roles(root: Path) -> dict[str, Any]:
    path = root / "memory/schema/roles.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def check_proposer_allowed(roles: dict[str, Any], namespace: str, proposer_id: str) -> str | None:
    """Return error string or None."""
    namespaces = {ns["id"]: ns for ns in roles.get("namespaces", []) if isinstance(ns, dict)}
    if not namespaces:
        return None  # no policy configured
    if namespace not in namespaces:
        return f"unknown namespace {namespace!r}"
    ns = namespaces[namespace]
    allowed = ns.get("allowed_proposers", [])
    if not allowed:
        return None
    # Check admin role
    for agent in roles.get("agents", []):
        if isinstance(agent, dict) and agent.get("id") == proposer_id:
            if "admin" in agent.get("roles", []):
                return None
    if proposer_id not in allowed:
        return f"proposer {proposer_id!r} is not allowed in namespace {namespace!r}"
    return None


def cmd_create(root: Path, args: argparse.Namespace) -> int:
    roles = load_roles(root)
    proposer_id = normalize_agent(args.proposer)
    namespace = args.namespace

    # Policy check
    err = check_proposer_allowed(roles, namespace, proposer_id)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1

    op = args.op
    entity = getattr(args, "entity", None)
    predicate = getattr(args, "predicate", None)
    value = getattr(args, "value", None)
    source = getattr(args, "source", None)
    confidence = getattr(args, "confidence", "medium")

    if op in {"create_fact", "update_fact"} and not all([entity, predicate, value]):
        print("ERROR: --entity, --predicate, and --value are required for fact ops", file=sys.stderr)
        return 1

    op_desc: dict[str, Any] = {"op": op}
    if entity:
        op_desc["entity"] = entity
    if predicate:
        op_desc["predicate"] = predicate
    if value:
        op_desc["value"] = value
    if entity and predicate:
        op_desc["target_path"] = f"memory/facts/{entity}/{predicate}.md"
    if source:
        op_desc["sources"] = [source]
    if confidence:
        op_desc["confidence"] = confidence

    prop_id = new_prop_id(args.title)
    fm: dict[str, Any] = {
        "type": "proposal",
        "proposal_id": prop_id,
        "namespace": namespace,
        "proposer_id": proposer_id,
        "title": args.title,
        "status": "proposed",
        "created_at": iso(utc_now()),
        "ops": [op_desc],
        "required_approvals": _required_approvals(roles, namespace),
        "approvals": [],
        "applied_at": None,
        "transaction_id": None,
        "rejection_reason": None,
    }
    fm["content_hash"] = content_hash_of(fm)

    body = f"# Proposal: {args.title}\n\nNamespace: `{namespace}` | Proposer: `{proposer_id}`\n\n"
    body += f"Operations:\n"
    for od in fm["ops"]:
        body += f"  - `{od.get('op')}` → `{od.get('target_path', 'n/a')}`\n"
    body += "\nThis proposal requires review before it can be applied.\n"

    prop_path = root / "memory/_proposals" / f"{prop_id}.md"
    write_markdown(prop_path, fm, body)
    print(f"Proposal created: {prop_id}")
    print(f"  title: {args.title}")
    print(f"  namespace: {namespace}")
    print(f"  path: {prop_path.relative_to(root)}")
    print(f"  required_approvals: {fm['required_approvals']}")
    return 0


def _required_approvals(roles: dict[str, Any], namespace: str) -> int:
    for ns in roles.get("namespaces", []):
        if isinstance(ns, dict) and ns.get("id") == namespace:
            return int(ns.get("required_approvals", 1))
    return 1


def cmd_list(root: Path, args: argparse.Namespace) -> int:
    prop_dir = root / "memory/_proposals"
    if not prop_dir.exists():
        print("No proposals found.")
        return 0
    status_filter = getattr(args, "status", None)
    rows = []
    for path in sorted(prop_dir.glob("*.md")):
        data, _ = split_frontmatter(path)
        if data.get("type") != "proposal":
            continue
        if status_filter and data.get("status") != status_filter:
            continue
        rows.append(data)
    if not rows:
        print("No proposals found.")
        return 0
    for d in sorted(rows, key=lambda r: str(r.get("created_at", "")), reverse=True):
        print(f"{str(d.get('created_at', ''))[:19]}  {d.get('status'):<20}  {d.get('proposal_id')}  \"{d.get('title')}\"")
    return 0


def cmd_show(root: Path, args: argparse.Namespace) -> int:
    prop_dir = root / "memory/_proposals"
    prop_id = args.proposal_id
    for path in prop_dir.glob("*.md"):
        data, body = split_frontmatter(path)
        if data.get("proposal_id") == prop_id:
            print(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
            if body.strip():
                print(body)
            return 0
    print(f"ERROR: proposal not found: {prop_id}", file=sys.stderr)
    return 1


def cmd_apply(root: Path, args: argparse.Namespace) -> int:
    """Apply an approved proposal using the transaction tool."""
    import transact  # type: ignore[import]

    prop_dir = root / "memory/_proposals"
    prop_id = args.proposal_id
    prop_path: Path | None = None
    prop_data: dict[str, Any] = {}

    for path in prop_dir.glob("*.md"):
        data, _ = split_frontmatter(path)
        if data.get("proposal_id") == prop_id:
            prop_path = path
            prop_data = data
            break

    if not prop_path:
        print(f"ERROR: proposal not found: {prop_id}", file=sys.stderr)
        return 1

    status = prop_data.get("status")
    if status != "approved":
        print(f"ERROR: proposal {prop_id} is not approved (status={status!r})", file=sys.stderr)
        return 1

    roles = load_roles(root)
    namespace = prop_data.get("namespace", "")
    required = _required_approvals(roles, namespace)
    approvals = prop_data.get("approvals") or []
    if len(approvals) < required:
        print(f"ERROR: proposal needs {required} approval(s), has {len(approvals)}", file=sys.stderr)
        return 1

    assume_yes = getattr(args, "yes", False)

    # Build and commit a transaction for this proposal
    idempotency_key = f"apply-proposal-{prop_id}"

    # Use transact module directly
    class FakeArgs:
        pass

    fa = FakeArgs()
    fa.idempotency_key = idempotency_key
    fa.expected_revision = None
    fa.agent = prop_data.get("proposer_id")
    ret = transact.cmd_begin(root, fa)
    if ret != 0:
        return ret

    # Reload to get txn_id
    from transact import load_staging_meta as lsm, staging_dir
    txn_id: str | None = None
    staging_base = root / "memory/_staging"
    for d in staging_base.iterdir():
        if d.is_dir() and (d / ".pending").exists():
            m = lsm(root, d.name)
            if m.get("idempotency_key") == idempotency_key and m.get("status") == "pending":
                txn_id = d.name
                break
    if not txn_id:
        # Already idempotent skip
        print(f"Proposal {prop_id} was already applied (idempotent skip).")
        _mark_proposal_applied(prop_path, prop_data, "idempotent")
        return 0

    # Add operations
    for op_desc in prop_data.get("ops", []):
        fa2 = FakeArgs()
        fa2.txn_id = txn_id
        fa2.op = op_desc.get("op", "create_fact")
        fa2.entity = op_desc.get("entity")
        fa2.predicate = op_desc.get("predicate")
        fa2.value = op_desc.get("value")
        fa2.source = (op_desc.get("sources") or [None])[0]
        fa2.confidence = op_desc.get("confidence", "medium")
        fa2.reason = f"Applied from proposal {prop_id}"
        ret = transact.cmd_add(root, fa2)
        if ret != 0:
            return ret

    # Commit
    fa3 = FakeArgs()
    fa3.txn_id = txn_id
    fa3.yes = assume_yes
    ret = transact.cmd_commit(root, fa3)
    if ret != 0:
        return ret

    # Load committed txn journal to get the txn_id for the proposal record
    _mark_proposal_applied(prop_path, prop_data, txn_id)
    print(f"Proposal {prop_id} applied.")
    return 0


def _mark_proposal_applied(prop_path: Path, prop_data: dict[str, Any], txn_id: str) -> None:
    updated = dict(prop_data)
    updated["status"] = "applied"
    updated["applied_at"] = iso(utc_now())
    updated["transaction_id"] = txn_id
    body = f"# Proposal: {prop_data.get('title')}\n\nStatus: **applied** via transaction `{txn_id}`.\n"
    write_markdown(prop_path, updated, body)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command")

    p_create = sub.add_parser("create", help="Create a new proposal")
    p_create.add_argument("--title", required=True)
    p_create.add_argument("--namespace", required=True)
    p_create.add_argument("--proposer", required=True)
    p_create.add_argument("--op", required=True, choices=["create_fact", "update_fact", "archive_fact"])
    p_create.add_argument("--entity", default=None)
    p_create.add_argument("--predicate", default=None)
    p_create.add_argument("--value", default=None)
    p_create.add_argument("--source", default=None)
    p_create.add_argument("--confidence", default="medium", choices=["high", "medium", "low"])

    p_list = sub.add_parser("list", help="List proposals")
    p_list.add_argument("--status", default=None, choices=list(VALID_STATUSES))

    p_show = sub.add_parser("show", help="Show a proposal")
    p_show.add_argument("--proposal-id", required=True)

    p_apply = sub.add_parser("apply", help="Apply an approved proposal")
    p_apply.add_argument("--proposal-id", required=True)
    p_apply.add_argument("--yes", action="store_true")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = Path.cwd()

    if args.command == "create":
        return cmd_create(root, args)
    if args.command == "list":
        return cmd_list(root, args)
    if args.command == "show":
        return cmd_show(root, args)
    if args.command == "apply":
        return cmd_apply(root, args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
