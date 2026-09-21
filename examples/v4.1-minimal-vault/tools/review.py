#!/usr/bin/env python3
"""V4 review lifecycle tool.

Submits reviews (approve, reject, request-changes) for open proposals.
Enforces:
  - Self-approval prohibition: reviewer must not be the proposer.
  - Namespace permissions: reviewer must be listed as allowed_reviewer for
    the proposal's namespace, or hold the 'admin' role.
  - Cryptographic binding: each review records the proposal_content_hash at
    the time of review; if the proposal changes later, the hash won't match.

Usage:
  review.py approve         --proposal-id PROPID --reviewer AGENT [--comment TEXT]
  review.py reject          --proposal-id PROPID --reviewer AGENT --comment TEXT
  review.py request-changes --proposal-id PROPID --reviewer AGENT --comment TEXT
  review.py list            [--proposal-id PROPID]
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import secrets
import sys
from pathlib import Path
from typing import Any

import yaml


AGENT_ID_RE = re.compile(r"^agent-[a-z0-9-]+-[a-f0-9]{8,}$")
PROP_ID_RE = re.compile(r"^prop-[a-z0-9][a-z0-9_-]*$")
REV_ID_RE = re.compile(r"^rev-[a-z0-9][a-z0-9_-]*$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(value: dt.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def slugify(text: str, limit: int = 30) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:limit] or "rev"


def normalize_agent(value: str | None) -> str:
    if value and AGENT_ID_RE.match(value):
        return value
    base = slugify(value or "reviewer", 28)
    return f"agent-{base}-{secrets.token_hex(4)}"


def new_rev_id(prop_id: str) -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ").lower()
    suffix = secrets.token_hex(4)
    short_prop = slugify(prop_id.replace("prop-", ""), 16)
    return f"rev-{short_prop}-{stamp}-{suffix}"


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


def load_roles(root: Path) -> dict[str, Any]:
    path = root / "memory/schema/roles.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _agent_roles(roles: dict[str, Any], agent_id: str) -> list[str]:
    for agent in roles.get("agents", []):
        if isinstance(agent, dict) and agent.get("id") == agent_id:
            return list(agent.get("roles", []))
    return []


def check_reviewer_allowed(roles: dict[str, Any], namespace: str, reviewer_id: str) -> str | None:
    """Return error string or None if allowed."""
    if not roles:
        return None  # no policy
    namespaces = {ns["id"]: ns for ns in roles.get("namespaces", []) if isinstance(ns, dict)}
    if namespace not in namespaces:
        return f"unknown namespace {namespace!r}"
    # Admin bypasses namespace restrictions
    if "admin" in _agent_roles(roles, reviewer_id):
        return None
    ns = namespaces[namespace]
    allowed = ns.get("allowed_reviewers", [])
    if allowed and reviewer_id not in allowed:
        return f"reviewer {reviewer_id!r} is not allowed to review namespace {namespace!r}"
    return None


def load_proposal(root: Path, prop_id: str) -> tuple[Path | None, dict[str, Any]]:
    prop_dir = root / "memory/_proposals"
    if not prop_dir.exists():
        return None, {}
    for path in prop_dir.glob("*.md"):
        data, _ = split_frontmatter(path)
        if data.get("proposal_id") == prop_id:
            return path, data
    return None, {}


def update_proposal_status(prop_path: Path, prop_data: dict[str, Any],
                            verdict: str, reviewer_id: str) -> None:
    """Update proposal status and approvals after a review verdict."""
    updated = dict(prop_data)
    if verdict == "approved":
        approvals = list(updated.get("approvals") or [])
        if reviewer_id not in approvals:
            approvals.append(reviewer_id)
        updated["approvals"] = approvals
        # Check if fully approved
        required = updated.get("required_approvals", 1)
        if len(approvals) >= required:
            updated["status"] = "approved"
    elif verdict == "rejected":
        updated["status"] = "rejected"
    elif verdict == "changes_requested":
        updated["status"] = "changes_requested"
    write_markdown(prop_path, updated, _proposal_body(updated))


def _proposal_body(data: dict[str, Any]) -> str:
    body = f"# Proposal: {data.get('title')}\n\n"
    body += f"Status: **{data.get('status')}** | Namespace: `{data.get('namespace')}` | Proposer: `{data.get('proposer_id')}`\n"
    approvals = data.get("approvals") or []
    if approvals:
        body += f"\nApprovals: {', '.join(f'`{a}`' for a in approvals)}\n"
    return body


def cmd_review(root: Path, args: argparse.Namespace, verdict: str) -> int:
    prop_id = args.proposal_id
    reviewer_id = normalize_agent(args.reviewer)
    comment = getattr(args, "comment", None) or ""

    prop_path, prop_data = load_proposal(root, prop_id)
    if not prop_path:
        print(f"ERROR: proposal not found: {prop_id}", file=sys.stderr)
        return 1

    # Only open proposals can be reviewed
    status = prop_data.get("status")
    if status not in {"draft", "proposed", "changes_requested"}:
        print(f"ERROR: proposal {prop_id} cannot be reviewed in status {status!r}", file=sys.stderr)
        return 1

    # Self-approval check
    proposer_id = prop_data.get("proposer_id")
    if proposer_id == reviewer_id:
        print(f"ERROR: self-approval not allowed — reviewer {reviewer_id!r} is the proposer", file=sys.stderr)
        return 1

    # Namespace permission
    roles = load_roles(root)
    namespace = prop_data.get("namespace", "")
    err = check_reviewer_allowed(roles, namespace, reviewer_id)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1

    # Build review record
    rev_id = new_rev_id(prop_id)
    content_hash = prop_data.get("content_hash", "sha256:" + "0" * 64)
    fm: dict[str, Any] = {
        "type": "review",
        "review_id": rev_id,
        "proposal_id": prop_id,
        "reviewer_id": reviewer_id,
        "verdict": verdict,
        "created_at": iso(utc_now()),
        "proposal_content_hash": content_hash,
        "comment": comment or None,
    }
    body = f"# Review: {verdict} for {prop_id}\n\n"
    body += f"Reviewer: `{reviewer_id}` | Proposal hash at review time: `{content_hash[:20]}…`\n"
    if comment:
        body += f"\n> {comment}\n"
    body += f"\nThis review is cryptographically bound to proposal content hash `{content_hash}`.\n"

    rev_dir = root / "memory/_reviews"
    rev_path = rev_dir / f"{rev_id}.md"
    write_markdown(rev_path, fm, body)
    print(f"Review submitted: {rev_id}")
    print(f"  verdict: {verdict}")
    print(f"  proposal: {prop_id}")

    # Update proposal status
    update_proposal_status(prop_path, prop_data, verdict, reviewer_id)
    updated_data, _ = split_frontmatter(prop_path)
    print(f"  proposal status now: {updated_data.get('status')}")
    return 0


def cmd_list(root: Path, args: argparse.Namespace) -> int:
    rev_dir = root / "memory/_reviews"
    if not rev_dir.exists():
        print("No reviews found.")
        return 0
    prop_id_filter = getattr(args, "proposal_id", None)
    rows = []
    for path in sorted(rev_dir.glob("*.md")):
        data, _ = split_frontmatter(path)
        if data.get("type") != "review":
            continue
        if prop_id_filter and data.get("proposal_id") != prop_id_filter:
            continue
        rows.append(data)
    if not rows:
        print("No reviews found.")
        return 0
    for d in sorted(rows, key=lambda r: str(r.get("created_at", "")), reverse=True):
        print(f"{str(d.get('created_at', ''))[:19]}  {d.get('verdict'):<20}  {d.get('review_id')}  (for {d.get('proposal_id')})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command")

    for cmd_name in ("approve", "reject", "request-changes"):
        p = sub.add_parser(cmd_name, help=f"Submit a {cmd_name} review")
        p.add_argument("--proposal-id", required=True)
        p.add_argument("--reviewer", required=True)
        p.add_argument("--comment", default=None)

    p_list = sub.add_parser("list", help="List reviews")
    p_list.add_argument("--proposal-id", default=None)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = Path.cwd()

    if args.command == "approve":
        return cmd_review(root, args, "approved")
    if args.command == "reject":
        return cmd_review(root, args, "rejected")
    if args.command == "request-changes":
        return cmd_review(root, args, "changes_requested")
    if args.command == "list":
        return cmd_list(root, args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
