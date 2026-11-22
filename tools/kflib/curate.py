"""Decoupled Curator engine: vault drift scanning and signal triage."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .capture import capture_signal
from .model import (
    format_markdown,
    is_active_head,
    iso_utc,
    parse_date,
    parse_datetime,
    rel_path,
    safe_path,
    scan_records,
    slugify,
    split_frontmatter,
    today,
    utc_now,
)
from .schema_check import compute_stale_records
from .transact import enforce_no_pending_recovery, execute_atomic_publication, get_agent_roles


def _enforce_curator_or_owner(root: Path, agent_id: str) -> None:
    roles = set(get_agent_roles(root, agent_id))
    if not (roles & {"curator", "owner"}):
        raise ValueError(f"agent {agent_id!r} (roles={sorted(roles)}) is not authorized for curator operations")


def scan_vault_drift(
    root: Path,
    *,
    emit_signals: bool = False,
    emitted_by: str = "agent-curator-00000003",
) -> dict[str, Any]:
    if emit_signals:
        _enforce_curator_or_owner(root, emitted_by)

    detections: list[dict[str, Any]] = []
    ref = today()

    def add_detection(
        kind: str,
        severity: str,
        target_ns: str,
        summary: str,
        *,
        entities: list[str] | None = None,
        related_paths: list[str] | None = None,
        evidence: list[str] | None = None,
    ) -> None:
        paths_sorted = sorted(set(related_paths or []))
        ev_sorted = sorted(set(evidence or []))
        key_material = f"scan:{kind}:{summary}:{'|'.join(paths_sorted)}:{'|'.join(ev_sorted)}"
        ikey = "scan-" + hashlib.sha256(key_material.encode("utf-8")).hexdigest()[:16]
        detections.append({
            "kind": kind,
            "severity": severity,
            "target_namespace": target_ns,
            "summary": summary,
            "entities": sorted(set(entities or [])),
            "related_paths": paths_sorted,
            "evidence": ev_sorted,
            "idempotency_key": ikey,
        })

    # 1. Stale facts, skills, guidance
    for stale_rel, reason in compute_stale_records(root):
        fm, _ = split_frontmatter(root / stale_rel)
        rtype = str(fm.get("type", "fact"))
        ns_map = {"fact": "facts", "skill": "skills", "guidance": "guidance"}
        ents = [fm["entity"]] if fm.get("entity") else list(fm.get("entities") or [])
        add_detection(
            "stale",
            "low",
            ns_map.get(rtype, "facts"),
            f"Stale {rtype} at {stale_rel} ({reason})",
            entities=ents,
            related_paths=[stale_rel],
        )

    # 2. Index current & historical facts for contradiction / uncurated claim analysis
    active_facts_by_slot: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
    all_fact_values_by_slot: dict[tuple[str, str], set[str]] = {}
    for p, fm, _ in scan_records(root, "knowledge/facts", "fact"):
        r = rel_path(p, root)
        slot = (str(fm.get("entity")), str(fm.get("predicate")))
        if fm.get("status") != "retracted":
            all_fact_values_by_slot.setdefault(slot, set()).add(repr(fm.get("value")))
        if is_active_head(fm):
            active_facts_by_slot[slot] = (r, fm)
        end_d = parse_date(fm.get("valid_until"))
        if end_d and end_d <= ref and r == f"knowledge/facts/{slot[0]}/{slot[1]}.md" and fm.get("status") == "active":
            add_detection(
                "stale",
                "high",
                "facts",
                f"Expired active fact at {r} (valid_until={end_d} <= {ref})",
                entities=[slot[0]],
                related_paths=[r],
            )

    # 3. Inspect event `asserts` against canonical facts
    for ev_path, ev_fm, _ in scan_records(root, "knowledge/events", "event"):
        ev_rel = rel_path(ev_path, root)
        ev_occ = parse_datetime(ev_fm["occurred_at"])
        for claim in ev_fm.get("asserts") or []:
            if not isinstance(claim, dict):
                continue
            ent = str(claim.get("entity", ""))
            pred = str(claim.get("predicate", ""))
            val = claim.get("value")
            slot = (ent, pred)
            if slot in active_facts_by_slot:
                fact_rel, fact_fm = active_facts_by_slot[slot]
                fact_obs = parse_datetime(fact_fm["observed_at"])
                if fact_fm.get("value") != val and ev_occ >= fact_obs:
                    add_detection(
                        "contradiction",
                        "high",
                        "facts",
                        f"Newer event {ev_fm['id']} asserts {ent}/{pred}={val!r}, contradicting {fact_rel} ({fact_fm.get('value')!r})",
                        entities=[ent],
                        related_paths=[fact_rel],
                        evidence=[ev_rel],
                    )
            elif repr(val) not in all_fact_values_by_slot.get(slot, set()):
                add_detection(
                    "uncurated_claim",
                    "medium",
                    "facts",
                    f"Uncurated event claim in {ev_fm['id']}: {ent}/{pred}={val!r}",
                    entities=[ent],
                    evidence=[ev_rel],
                )

    # 4. Broken evidence references
    for folder in ("knowledge/facts", "knowledge/skills", "knowledge/guidance", "knowledge/decisions"):
        for p, fm, _ in scan_records(root, folder):
            r = rel_path(p, root)
            for ref_target in fm.get("derived_from") or []:
                try:
                    tp = safe_path(root, str(ref_target))
                    if not tp.is_file():
                        add_detection(
                            "broken_reference",
                            "high",
                            "mixed",
                            f"Dangling derived_from reference {ref_target!r} in {r}",
                            related_paths=[r],
                        )
                except ValueError:
                    add_detection(
                        "broken_reference",
                        "high",
                        "mixed",
                        f"Invalid derived_from path {ref_target!r} in {r}",
                        related_paths=[r],
                    )

    emitted: list[dict[str, Any]] = []
    if emit_signals:
        for det in detections:
            sig = capture_signal(
                root,
                emitted_by=emitted_by,
                kind=det["kind"],
                severity=det["severity"],
                target_namespace=det["target_namespace"],
                summary=det["summary"],
                entities=det["entities"],
                related_paths=det["related_paths"],
                evidence=det["evidence"],
                idempotency_key=det["idempotency_key"],
            )
            emitted.append(sig)

    return {"detections": detections, "emitted_signals": emitted}


def _verify_dismissed_signal_state(
    root: Path,
    signal_id: str,
    sig_rel: str,
    sig_fm: dict[str, Any],
) -> str:
    rcpt_id = sig_fm.get("resolved_by_receipt")
    if not isinstance(rcpt_id, str) or not rcpt_id.strip():
        raise ValueError(f"signal {signal_id} is marked dismissed but has no resolved_by_receipt")
    rcpt_path = safe_path(root, f"factory/receipts/{rcpt_id}.md")
    if not rcpt_path.is_file():
        raise ValueError(f"signal {signal_id} is marked dismissed, but receipt {rcpt_id} does not exist")
    rcpt_fm, _ = split_frontmatter(rcpt_path)
    if (
        rcpt_fm.get("type") != "receipt"
        or rcpt_fm.get("status") != "committed"
        or rcpt_fm.get("mode") != "signal_triage"
        or signal_id not in (rcpt_fm.get("resolved_signals") or [])
    ):
        raise ValueError(f"signal {signal_id} receipt {rcpt_id} is invalid or not committed for this signal")
    touched = rcpt_fm.get("touched_files")
    if not isinstance(touched, list) or not any(
        isinstance(entry, dict) and entry.get("path") == sig_rel
        for entry in touched
    ):
        raise ValueError(f"signal {signal_id} receipt {rcpt_id} did not record touching {sig_rel}")
    return rcpt_id


def dismiss_signal(
    root: Path,
    *,
    signal_id: str,
    curator_id: str,
    reason: str,
    yes: bool,
    rebuild: bool = False,
) -> dict[str, Any]:
    if not yes:
        raise ValueError("dismiss-signal requires --yes confirmation")
    enforce_no_pending_recovery(root, block_all_staged=True)
    _enforce_curator_or_owner(root, curator_id)
    clean_reason = reason.strip()
    if not clean_reason:
        raise ValueError("dismiss-signal requires a non-empty --reason")

    found_path: Path | None = None
    found_fm: dict[str, Any] = {}
    found_body = ""
    for p, fm, body in scan_records(root, "factory/signals", "signal"):
        if fm.get("id") == signal_id:
            found_path, found_fm, found_body = p, fm, body
            break
    if found_path is None:
        raise ValueError(f"signal not found: {signal_id}")

    rel = rel_path(found_path, root)
    cur_status = found_fm.get("status")
    if cur_status == "dismissed":
        verified_rcpt_id = _verify_dismissed_signal_state(root, signal_id, rel, found_fm)
        return dict(found_fm, path=rel, receipt_id=verified_rcpt_id, idempotent_replay=True)
    if cur_status == "resolved":
        raise ValueError(f"cannot dismiss signal {signal_id}: signal is already resolved")
    if cur_status not in {"open", "proposed"}:
        raise ValueError(f"cannot dismiss signal {signal_id} in status {cur_status!r}")

    now = utc_now()
    now_iso = iso_utc(now)
    stamp = now.strftime("%Y%m%dt%H%M%Sz")
    ikey = f"dismiss-{signal_id}"
    suffix = hashlib.sha256(f"{ikey}:{now_iso}".encode("utf-8")).hexdigest()[:8]
    planned_rcpt_id = f"rcpt-{slugify(ikey, 20)}-{stamp}-{suffix}"
    updated_fm = dict(
        found_fm,
        status="dismissed",
        proposal_id=None,
        resolved_at=now_iso,
        resolved_by_receipt=planned_rcpt_id,
        resolution_note=clean_reason,
    )
    pub = execute_atomic_publication(
        root,
        mode="signal_triage",
        idempotency_key=ikey,
        actor_id=curator_id,
        ops=[{"op": "dismiss_signal", "signal_id": signal_id, "reason": clean_reason}],
        writes={rel: format_markdown(updated_fm, found_body)},
        resolved_signals=[signal_id],
        receipt_id=planned_rcpt_id,
        rebuild=rebuild,
    )
    return dict(updated_fm, path=rel, receipt_id=pub["receipt_id"], idempotent_replay=False)
