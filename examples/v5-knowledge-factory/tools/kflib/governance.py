"""Knowledge Factory governance: executable proposals, hash-bound reviews, and atomic publication."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .model import (
    NAMESPACES,
    PROPOSAL_STATUSES,
    REVIEW_VERDICTS,
    atomic_write_text,
    file_sha256,
    format_markdown,
    iso_utc,
    load_policy,
    rel_path,
    safe_path,
    scan_records,
    slugify,
    split_frontmatter,
    utc_now,
)
from .transact import (
    SUPPORTED_OPS,
    _op_namespace,
    compile_operations,
    enforce_op_trust_policy,
    execute_atomic_publication,
    get_agent_roles,
    validate_candidate_writes,
)


def compute_proposal_hash(data: dict[str, Any]) -> str:
    payload = {
        "title": data.get("title", ""),
        "namespace": data.get("namespace", ""),
        "proposer_id": data.get("proposer_id", ""),
        "ops": data.get("ops", []),
        "resolves_signals": sorted(data.get("resolves_signals") or []),
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _namespace_policy(root: Path, namespace: str) -> dict[str, Any]:
    if namespace not in NAMESPACES:
        raise ValueError(f"unknown namespace {namespace!r}; allowed: {NAMESPACES}")
    policy = load_policy(root)
    for ns in policy.get("namespaces", []):
        if isinstance(ns, dict) and ns.get("id") == namespace:
            return ns
    raise ValueError(f"namespace {namespace!r} is missing from factory/schema/policy.yaml")


def _enforce_proposer_allowed(root: Path, namespace: str, proposer_id: str) -> int:
    ns_cfg = _namespace_policy(root, namespace)
    roles = set(get_agent_roles(root, proposer_id))
    allowed = set(ns_cfg.get("allowed_proposers") or [])
    if allowed and not (roles & allowed) and "owner" not in roles:
        raise ValueError(
            f"proposer {proposer_id!r} (roles={sorted(roles)}) is not allowed to propose in namespace {namespace!r} (allowed={sorted(allowed)})"
        )
    req = int(ns_cfg.get("required_approvals", 1))
    if req < 1:
        raise ValueError("required_approvals must be >= 1")
    return req


def _enforce_reviewer_allowed(root: Path, namespace: str, reviewer_id: str) -> None:
    ns_cfg = _namespace_policy(root, namespace)
    roles = set(get_agent_roles(root, reviewer_id))
    allowed = set(ns_cfg.get("allowed_reviewers") or [])
    if allowed and not (roles & allowed) and "owner" not in roles:
        raise ValueError(
            f"reviewer {reviewer_id!r} (roles={sorted(roles)}) is not allowed to review namespace {namespace!r} (allowed={sorted(allowed)})"
        )


def _find_signal(root: Path, signal_id: str) -> tuple[Path, dict[str, Any], str]:
    for p, fm, body in scan_records(root, "factory/signals", "signal"):
        if fm.get("id") == signal_id:
            return p, fm, body
    raise ValueError(f"referenced signal not found: {signal_id}")


def load_proposal(root: Path, proposal_id: str) -> tuple[Path, dict[str, Any], str]:
    path = safe_path(root, f"factory/proposals/{proposal_id}.md")
    if not path.is_file():
        raise ValueError(f"proposal not found: {proposal_id}")
    fm, body = split_frontmatter(path)
    if fm.get("id") != proposal_id:
        raise ValueError(f"proposal file {proposal_id}.md has mismatched id {fm.get('id')!r}")
    return path, fm, body


def create_proposal(
    root: Path,
    *,
    title: str,
    namespace: str,
    proposer_id: str,
    ops: list[dict[str, Any]],
    rationale: str | None = None,
    resolves_signals: list[str] | None = None,
    derived_from: list[str] | None = None,
    status: str = "proposed",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    if status not in {"draft", "proposed"}:
        raise ValueError("initial proposal status must be 'draft' or 'proposed'")
    req_approvals = _enforce_proposer_allowed(root, namespace, proposer_id)

    if not isinstance(ops, list) or len(ops) == 0:
        raise ValueError("proposal requires at least one executable operation (use `kf.py capture signal` for diagnostics)")

    if idempotency_key:
        for p, fm, _ in scan_records(root, "factory/proposals", "proposal"):
            if fm.get("idempotency_key") == idempotency_key:
                return dict(fm, path=rel_path(p, root), idempotent_replay=True)

    enriched_ops: list[dict[str, Any]] = []
    for raw_op in ops:
        if not isinstance(raw_op, dict) or raw_op.get("op") not in SUPPORTED_OPS:
            raise ValueError(f"unsupported proposal op {raw_op!r}")
        op = dict(raw_op)
        op_ns = _op_namespace(str(op["op"]))
        if namespace != "mixed" and op_ns != namespace:
            raise ValueError(
                f"operation {op['op']!r} targets namespace {op_ns!r}, but proposal namespace is {namespace!r} (use namespace='mixed' for cross-namespace bundles)"
            )
        enforce_op_trust_policy(root, op, proposer_id, reviewed=True)
        # Capture optimistic precondition_hash on existing target records
        if op["op"] in {"supersede_fact", "confirm_fact", "retract_fact"}:
            slot = safe_path(root, f"knowledge/facts/{op.get('entity')}/{op.get('predicate')}.md")
            if not slot.is_file():
                raise ValueError(f"target fact does not exist: {rel_path(slot, root)}")
            op.setdefault("precondition_hash", file_sha256(slot))
        elif op["op"] in {"supersede_skill", "retract_skill"}:
            slot = safe_path(root, f"knowledge/skills/{op.get('slug')}.md")
            if not slot.is_file():
                raise ValueError(f"target skill does not exist: {rel_path(slot, root)}")
        elif op["op"] in {"supersede_guidance", "retract_guidance"}:
            slot = safe_path(root, f"knowledge/guidance/{op.get('slug')}.md")
            if not slot.is_file():
                raise ValueError(f"target guidance does not exist: {rel_path(slot, root)}")
        elif op["op"] == "supersede_decision":
            slot = safe_path(root, f"knowledge/decisions/{op.get('decision_id') or op.get('id')}.md")
            if not slot.is_file():
                raise ValueError(f"target decision does not exist: {rel_path(slot, root)}")
        enriched_ops.append(op)

    sig_ids = sorted(set(resolves_signals or []))
    signal_updates: dict[str, str | None] = {}
    now = utc_now()
    stamp = now.strftime("%Y%m%dt%H%M%Sz")
    seed = idempotency_key or f"{proposer_id}:{title}:{iso_utc(now)}"
    suffix = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]
    prop_id = f"prop-{slugify(title, 20)}-{stamp}-{suffix}"
    prop_rel = f"factory/proposals/{prop_id}.md"

    for sid in sig_ids:
        sp, sfm, sbody = _find_signal(root, sid)
        srel = rel_path(sp, root)
        if sfm.get("status") == "open":
            signal_updates[srel] = format_markdown(dict(sfm, status="proposed", proposal_id=prop_id), sbody)

    fm: dict[str, Any] = {
        "type": "proposal",
        "id": prop_id,
        "title": title.strip(),
        "namespace": namespace,
        "proposer_id": proposer_id,
        "status": status,
        "created_at": iso_utc(now),
        "rationale": rationale,
        "resolves_signals": sig_ids,
        "derived_from": list(derived_from or []),
        "ops": enriched_ops,
        "required_approvals": req_approvals,
        "content_hash": "",
        "idempotency_key": idempotency_key,
        "published_at": None,
        "receipt_id": None,
    }
    fm["content_hash"] = compute_proposal_hash(fm)

    body_lines = [
        f"# Proposal: {title.strip()}",
        "",
        f"- **Status:** `{status}`",
        f"- **Namespace:** `{namespace}`",
        f"- **Proposer:** `{proposer_id}`",
        f"- **Content hash:** `{fm['content_hash']}`",
    ]
    if rationale:
        body_lines.extend(["", "## Rationale", "", rationale.strip()])

    candidate_writes: dict[str, str | None] = {prop_rel: format_markdown(fm, "\n".join(body_lines)), **signal_updates}
    validate_candidate_writes(root, candidate_writes)
    for rel, content in candidate_writes.items():
        if content is not None:
            atomic_write_text(root / rel, content)
    return dict(fm, path=prop_rel, idempotent_replay=False)


def list_proposals(root: Path, *, status: str | None = None, namespace: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p, fm, _ in scan_records(root, "factory/proposals", "proposal"):
        if status and fm.get("status") != status:
            continue
        if namespace and fm.get("namespace") != namespace:
            continue
        rows.append(dict(fm, path=rel_path(p, root)))
    return rows


def show_proposal(root: Path, proposal_id: str) -> dict[str, Any]:
    p, fm, body = load_proposal(root, proposal_id)
    reviews = list_reviews(root, proposal_id=proposal_id)
    return dict(fm, path=rel_path(p, root), body=body, reviews=reviews)


def list_reviews(root: Path, *, proposal_id: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p, fm, _ in scan_records(root, "factory/reviews", "review"):
        if proposal_id and fm.get("proposal_id") != proposal_id:
            continue
        rows.append(dict(fm, path=rel_path(p, root)))
    return rows


def current_valid_reviews(root: Path, prop_fm: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (approved_reviews, blocking_reviews) bound to current content_hash."""
    expected_hash = compute_proposal_hash(prop_fm)
    if prop_fm.get("content_hash") != expected_hash:
        raise ValueError(
            f"proposal {prop_fm.get('id')} content_hash mismatch (expected {expected_hash}, file has {prop_fm.get('content_hash')}); proposal was edited after creation/review"
        )
    latest_by_reviewer: dict[str, dict[str, Any]] = {}
    all_revs = sorted(
        list_reviews(root, proposal_id=str(prop_fm["id"])),
        key=lambda r: (str(r.get("created_at", "")), str(r.get("id", ""))),
    )
    for rev in all_revs:
        if rev.get("proposal_content_hash") != expected_hash:
            continue
        reviewer = str(rev["reviewer_id"])
        if reviewer == prop_fm.get("proposer_id"):
            raise ValueError(f"self-approval not allowed: reviewer {reviewer!r} is the proposer")
        _enforce_reviewer_allowed(root, str(prop_fm["namespace"]), reviewer)
        latest_by_reviewer[reviewer] = rev

    approved = [r for r in latest_by_reviewer.values() if r.get("verdict") == "approved"]
    blocking = [r for r in latest_by_reviewer.values() if r.get("verdict") in {"rejected", "changes_requested"}]
    return approved, blocking


def submit_review(
    root: Path,
    *,
    proposal_id: str,
    reviewer_id: str,
    verdict: str,
    comment: str | None = None,
) -> dict[str, Any]:
    if verdict not in REVIEW_VERDICTS:
        raise ValueError(f"invalid verdict {verdict!r}; allowed: {REVIEW_VERDICTS}")
    if verdict in {"rejected", "changes_requested"} and not (comment and comment.strip()):
        raise ValueError(f"verdict {verdict!r} requires a non-empty --comment")

    prop_path, prop_fm, prop_body = load_proposal(root, proposal_id)
    if prop_fm.get("status") not in {"draft", "proposed", "changes_requested", "approved"}:
        raise ValueError(f"proposal {proposal_id} cannot be reviewed in status {prop_fm.get('status')!r}")
    expected_hash = compute_proposal_hash(prop_fm)
    if prop_fm.get("content_hash") != expected_hash:
        raise ValueError("proposal content_hash does not match its contents; create a clean proposal")

    if reviewer_id == prop_fm.get("proposer_id"):
        raise ValueError(f"self-approval not allowed: reviewer {reviewer_id!r} is the proposer")
    _enforce_reviewer_allowed(root, str(prop_fm["namespace"]), reviewer_id)

    now = utc_now()
    stamp = now.strftime("%Y%m%dt%H%M%Sz")
    suffix = hashlib.sha256(f"{proposal_id}:{reviewer_id}:{verdict}:{iso_utc(now)}".encode("utf-8")).hexdigest()[:8]
    rev_id = f"rev-{slugify(proposal_id.removeprefix('prop-'), 16)}-{stamp}-{suffix}"
    rev_rel = f"factory/reviews/{rev_id}.md"

    rev_fm: dict[str, Any] = {
        "type": "review",
        "id": rev_id,
        "proposal_id": proposal_id,
        "reviewer_id": reviewer_id,
        "verdict": verdict,
        "created_at": iso_utc(now),
        "proposal_content_hash": expected_hash,
        "comment": comment.strip() if comment and comment.strip() else None,
    }
    rev_body = f"# Review ({verdict}) for `{proposal_id}`\n\nReviewer: `{reviewer_id}`\nBound hash: `{expected_hash}`"
    if rev_fm["comment"]:
        rev_body += f"\n\n> {rev_fm['comment']}"

    # Determine updated proposal status
    atomic_write_text(root / rev_rel, format_markdown(rev_fm, rev_body))
    approved, blocking = current_valid_reviews(root, prop_fm)
    req = int(prop_fm.get("required_approvals", 1))
    if any(r.get("verdict") == "rejected" for r in blocking):
        new_status = "rejected"
    elif any(r.get("verdict") == "changes_requested" for r in blocking):
        new_status = "changes_requested"
    elif len(approved) >= req:
        new_status = "approved"
    else:
        new_status = "proposed"

    updated_prop = dict(prop_fm, status=new_status)
    atomic_write_text(prop_path, format_markdown(updated_prop, prop_body))
    return dict(rev_fm, path=rev_rel, proposal_status=new_status)


def publish_proposal(
    root: Path,
    *,
    proposal_id: str,
    publisher_id: str,
    yes: bool,
    rebuild: bool = False,
) -> dict[str, Any]:
    if not yes:
        raise ValueError("publish requires --yes confirmation")
    prop_path, prop_fm, prop_body = load_proposal(root, proposal_id)
    prop_rel = rel_path(prop_path, root)

    if prop_fm.get("status") == "published":
        return {
            "proposal_id": proposal_id,
            "receipt_id": prop_fm.get("receipt_id"),
            "status": "committed",
            "idempotent_replay": True,
        }

    # Verify publisher has reviewer or owner authority for this namespace
    _enforce_reviewer_allowed(root, str(prop_fm["namespace"]), publisher_id)
    # Re-verify proposer eligibility and hash-bound approvals
    req_approvals = _enforce_proposer_allowed(root, str(prop_fm["namespace"]), str(prop_fm["proposer_id"]))
    approved, blocking = current_valid_reviews(root, prop_fm)
    if blocking:
        raise ValueError(f"proposal {proposal_id} has unresolved rejection or change request")
    if len(approved) < req_approvals:
        raise ValueError(
            f"proposal {proposal_id} has {len(approved)}/{req_approvals} valid hash-bound approvals"
        )
    if prop_fm.get("status") != "approved":
        raise ValueError(f"proposal {proposal_id} status must be 'approved', got {prop_fm.get('status')!r}")

    ops = list(prop_fm.get("ops") or [])
    proposer_id = str(prop_fm["proposer_id"])
    writes = compile_operations(root, ops, actor_id=proposer_id, reviewed=True)

    now_iso = iso_utc(utc_now())
    resolved_sig_ids = list(prop_fm.get("resolves_signals") or [])
    review_ids = sorted(str(r["id"]) for r in approved)

    # Pre-compute receipt ID indirectly? Better: execute_atomic_publication generates receipt_id,
    # or we compute deterministic receipt_id / update proposal + signals in the same atomic batch!
    # Let's include proposal & signal resolution in `writes`, then link receipt_id cleanly!
    stamp = utc_now().strftime("%Y%m%dt%H%M%Sz")
    ikey = f"publish-{proposal_id}"
    suffix = hashlib.sha256(f"{ikey}:{now_iso}".encode("utf-8")).hexdigest()[:8]
    planned_rcpt_id = f"rcpt-{slugify(ikey, 20)}-{stamp}-{suffix}"

    updated_prop = dict(prop_fm, status="published", published_at=now_iso, receipt_id=planned_rcpt_id)
    writes[prop_rel] = format_markdown(updated_prop, prop_body)

    for sid in resolved_sig_ids:
        sp, sfm, sbody = _find_signal(root, sid)
        srel = rel_path(sp, root)
        writes[srel] = format_markdown(
            dict(
                sfm,
                status="resolved",
                proposal_id=proposal_id,
                resolved_at=now_iso,
                resolved_by_receipt=planned_rcpt_id,
                resolution_note=f"Resolved by proposal {proposal_id}",
            ),
            sbody,
        )

    pub = _publish_with_fixed_receipt_id(
        root,
        receipt_id=planned_rcpt_id,
        idempotency_key=ikey,
        actor_id=publisher_id,
        proposer_id=proposer_id,
        proposal_id=proposal_id,
        review_ids=review_ids,
        resolved_signals=resolved_sig_ids,
        ops=ops,
        writes=writes,
        rebuild=rebuild,
    )
    return {"proposal_id": proposal_id, **pub}


def _publish_with_fixed_receipt_id(
    root: Path,
    *,
    receipt_id: str,
    idempotency_key: str,
    actor_id: str,
    proposer_id: str,
    proposal_id: str,
    review_ids: list[str],
    resolved_signals: list[str],
    ops: list[dict[str, Any]],
    writes: dict[str, str | None],
    rebuild: bool,
) -> dict[str, Any]:
    from .model import text_sha256, write_markdown
    from .rebuild import rebuild_all
    from .transact import git_head

    validate_candidate_writes(root, writes)
    head = git_head(root)
    now_iso = iso_utc(utc_now())

    touched: list[dict[str, Any]] = []
    preimages: dict[str, str | None] = {}
    for rel, content in sorted(writes.items()):
        target = safe_path(root, rel)
        existed = target.is_file()
        before_text = target.read_text(encoding="utf-8") if existed else None
        preimages[rel] = before_text
        touched.append({
            "path": rel,
            "action": "deleted" if content is None else ("updated" if existed else "created"),
            "before_hash": text_sha256(before_text) if before_text is not None else None,
            "after_hash": text_sha256(content) if content is not None else None,
        })

    try:
        for rel, content in sorted(writes.items()):
            target = safe_path(root, rel)
            if content is None:
                if target.exists():
                    target.unlink()
            else:
                atomic_write_text(target, content)
    except Exception as exc:
        for rel, before_text in preimages.items():
            target = safe_path(root, rel)
            if before_text is None:
                if target.exists():
                    target.unlink()
            else:
                atomic_write_text(target, before_text)
        raise RuntimeError(f"proposal publication failed and rolled back cleanly: {exc}") from exc

    rcpt_fm: dict[str, Any] = {
        "type": "receipt",
        "id": receipt_id,
        "mode": "proposal_publish",
        "status": "committed",
        "idempotency_key": idempotency_key,
        "actor_id": actor_id,
        "proposer_id": proposer_id,
        "proposal_id": proposal_id,
        "review_ids": review_ids,
        "resolved_signals": resolved_signals,
        "created_at": now_iso,
        "committed_at": now_iso,
        "expected_revision": None,
        "parent_revision": head,
        "ops": ops,
        "touched_files": touched,
        "failure_reason": None,
    }
    body = (
        f"# Publication Receipt: `{receipt_id}`\n\n"
        f"- **Proposal:** `{proposal_id}` (by `{proposer_id}`)\n"
        f"- **Publisher:** `{actor_id}`\n"
        f"- **Authorizing reviews:** {', '.join(f'`{r}`' for r in review_ids)}\n"
        f"- **Resolved signals:** {', '.join(f'`{s}`' for s in resolved_signals) or 'none'}"
    )
    write_markdown(root / "factory/receipts" / f"{receipt_id}.md", rcpt_fm, body)
    if rebuild:
        rebuild_all(root)
    return {
        "receipt_id": receipt_id,
        "status": "committed",
        "mode": "proposal_publish",
        "touched_files": touched,
        "rebuilt": rebuild,
    }
