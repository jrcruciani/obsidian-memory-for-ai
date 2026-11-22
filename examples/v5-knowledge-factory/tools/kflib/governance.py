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
    load_entities,
    load_policy,
    parse_datetime,
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
    enforce_no_pending_recovery,
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
    enforce_no_pending_recovery(root)
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
            op.setdefault("precondition_hash", file_sha256(slot))
        elif op["op"] in {"supersede_guidance", "retract_guidance"}:
            slot = safe_path(root, f"knowledge/guidance/{op.get('slug')}.md")
            if not slot.is_file():
                raise ValueError(f"target guidance does not exist: {rel_path(slot, root)}")
            op.setdefault("precondition_hash", file_sha256(slot))
        elif op["op"] == "supersede_decision":
            slot = safe_path(root, f"knowledge/decisions/{op.get('decision_id') or op.get('id')}.md")
            if not slot.is_file():
                raise ValueError(f"target decision does not exist: {rel_path(slot, root)}")
            op.setdefault("precondition_hash", file_sha256(slot))
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

    op_writes = compile_operations(root, enriched_ops, actor_id=proposer_id, reviewed=True)
    candidate_writes: dict[str, str | None] = {prop_rel: format_markdown(fm, "\n".join(body_lines)), **signal_updates}
    validate_candidate_writes(root, {**op_writes, **candidate_writes})

    preimages: dict[str, str | None] = {}
    for rel in candidate_writes:
        target = safe_path(root, rel)
        preimages[rel] = target.read_text(encoding="utf-8") if target.is_file() else None
    try:
        for rel in sorted(signal_updates):
            content = signal_updates[rel]
            if content is not None:
                atomic_write_text(safe_path(root, rel), content)
        prop_content = candidate_writes[prop_rel]
        assert prop_content is not None
        atomic_write_text(safe_path(root, prop_rel), prop_content)
    except Exception:
        for rel, before in preimages.items():
            target = safe_path(root, rel)
            if before is None:
                if target.exists():
                    target.unlink()
            else:
                atomic_write_text(target, before)
        raise
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


def _expected_op_target_slot(op: dict[str, Any]) -> str | None:
    kind = str(op.get("op", ""))
    if kind == "upsert_entity":
        return "knowledge/entities.md"
    if kind == "create_event":
        occ = parse_datetime(op.get("occurred_at"))
        ev_id = str(op.get("event_id") or op.get("id") or "")
        return f"knowledge/events/{occ.date().isoformat()}/{ev_id}.md"
    if kind in {"create_fact", "supersede_fact", "confirm_fact", "retract_fact"}:
        return f"knowledge/facts/{op.get('entity')}/{op.get('predicate')}.md"
    if kind in {"create_skill", "supersede_skill", "retract_skill"}:
        return f"knowledge/skills/{op.get('slug')}.md"
    if kind in {"create_guidance", "supersede_guidance", "retract_guidance"}:
        return f"knowledge/guidance/{op.get('slug')}.md"
    if kind in {"create_decision", "supersede_decision"}:
        return f"knowledge/decisions/{op.get('decision_id') or op.get('id')}.md"
    return None


def _verify_published_proposal_state(root: Path, proposal_id: str, prop_fm: dict[str, Any]) -> str:
    rcpt_id = prop_fm.get("receipt_id")
    if not isinstance(rcpt_id, str) or not rcpt_id.strip():
        raise ValueError(f"proposal {proposal_id} is marked published but has no receipt_id")
    rcpt_path = safe_path(root, f"factory/receipts/{rcpt_id}.md")
    if not rcpt_path.is_file():
        raise ValueError(f"proposal {proposal_id} is marked published, but receipt {rcpt_id} does not exist")
    rcpt_fm, _ = split_frontmatter(rcpt_path)
    if (
        rcpt_fm.get("type") != "receipt"
        or rcpt_fm.get("status") != "committed"
        or rcpt_fm.get("mode") != "proposal_publish"
        or rcpt_fm.get("proposal_id") != proposal_id
    ):
        raise ValueError(f"proposal {proposal_id} receipt {rcpt_id} is invalid or not committed for this proposal")

    touched = rcpt_fm.get("touched_files")
    if not isinstance(touched, list) or not touched:
        raise ValueError(f"proposal {proposal_id} receipt {rcpt_id} has no touched_files")
    has_knowledge_touch = False
    for entry in touched:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError(f"proposal {proposal_id} receipt {rcpt_id} has malformed touched_files entry")
        t_rel = entry["path"]
        if t_rel.startswith("knowledge/"):
            has_knowledge_touch = True
        if entry.get("action") in {"created", "updated"} and not safe_path(root, t_rel).is_file():
            raise ValueError(
                f"proposal {proposal_id} is marked published, but committed target {t_rel} does not exist"
            )
    if not has_knowledge_touch:
        raise ValueError(f"proposal {proposal_id} receipt {rcpt_id} recorded no canonical knowledge writes")

    ops = prop_fm.get("ops") or []
    entities_cache: dict[str, dict[str, Any]] | None = None
    for op in ops:
        if not isinstance(op, dict):
            continue
        slot = _expected_op_target_slot(op)
        if slot and not safe_path(root, slot).is_file():
            raise ValueError(
                f"proposal {proposal_id} is marked published, but canonical target {slot} is missing"
            )
        if op.get("op") == "upsert_entity":
            if entities_cache is None:
                entities_cache = load_entities(root)
            eid = str(op.get("entity_id") or op.get("id") or "")
            if eid not in entities_cache:
                raise ValueError(
                    f"proposal {proposal_id} is marked published, but entity {eid!r} is missing from knowledge/entities.md"
                )
    return rcpt_id


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
    enforce_no_pending_recovery(root, block_all_staged=True)
    prop_path, prop_fm, prop_body = load_proposal(root, proposal_id)
    prop_rel = rel_path(prop_path, root)

    if prop_fm.get("status") == "published":
        verified_rcpt_id = _verify_published_proposal_state(root, proposal_id, prop_fm)
        return {
            "proposal_id": proposal_id,
            "receipt_id": verified_rcpt_id,
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

    receipt_body = (
        f"# Publication Receipt: `{planned_rcpt_id}`\n\n"
        f"- **Proposal:** `{proposal_id}` (by `{proposer_id}`)\n"
        f"- **Publisher:** `{publisher_id}`\n"
        f"- **Authorizing reviews:** {', '.join(f'`{r}`' for r in review_ids)}\n"
        f"- **Resolved signals:** {', '.join(f'`{s}`' for s in resolved_sig_ids) or 'none'}"
    )
    pub = execute_atomic_publication(
        root,
        mode="proposal_publish",
        idempotency_key=ikey,
        actor_id=publisher_id,
        proposer_id=proposer_id,
        proposal_id=proposal_id,
        review_ids=review_ids,
        resolved_signals=resolved_sig_ids,
        ops=ops,
        writes=writes,
        receipt_id=planned_rcpt_id,
        receipt_body=receipt_body,
        rebuild=rebuild,
    )
    return {"proposal_id": proposal_id, **pub}
