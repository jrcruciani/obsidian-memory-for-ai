#!/usr/bin/env python3
"""Knowledge Factory v5.0 Unified CLI (`kf.py`)."""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Any

# Ensure local kflib is importable regardless of current working directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from kflib import SPEC_VERSION  # noqa: E402
from kflib.bootstrap import build_bootstrap  # noqa: E402
from kflib.capture import capture_event, capture_signal  # noqa: E402
from kflib.curate import dismiss_signal, scan_vault_drift  # noqa: E402
from kflib.governance import (  # noqa: E402
    create_proposal,
    list_proposals,
    list_reviews,
    publish_proposal,
    show_proposal,
    submit_review,
)
from kflib.migrate import migrate_v4_to_v5  # noqa: E402
from kflib.model import NAMESPACES, SIGNAL_KINDS  # noqa: E402
from kflib.query import (  # noqa: E402
    query_by_id,
    query_decisions,
    query_events,
    query_facts,
    query_graph,
    query_guidance,
    query_receipts,
    query_resolve_entity,
    query_search,
    query_signals,
    query_skills,
    query_why,
)
from kflib.rebuild import rebuild_all  # noqa: E402
from kflib.schema_check import lint_vault  # noqa: E402
from kflib.templates import init_vault  # noqa: E402
from kflib.transact import (  # noqa: E402
    add_operations,
    begin_transaction,
    commit_transaction,
    list_transactions,
    load_ops_from_cli,
    recover_transactions,
    register_op_flags,
    rollback_transaction,
)


def _extract_global_flags(argv: list[str]) -> tuple[list[str], bool, Path | None]:
    cleaned: list[str] = []
    json_mode = False
    vault_override: Path | None = None
    idx = 0
    while idx < len(argv):
        tok = argv[idx]
        if tok == "--json":
            json_mode = True
            idx += 1
        elif tok == "--vault" and idx + 1 < len(argv):
            vault_override = Path(argv[idx + 1]).resolve()
            idx += 2
        elif tok.startswith("--vault="):
            vault_override = Path(tok.split("=", 1)[1]).resolve()
            idx += 1
        else:
            cleaned.append(tok)
            idx += 1
    return cleaned, json_mode, vault_override


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kf.py",
        description="Obsidian Memory for AI v5.0 — The Knowledge Factory CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = sub.add_parser("init", help="Initialize a new v5.0 Knowledge Factory vault")
    p_init.add_argument("target", type=Path, help="Target vault directory")
    p_init.add_argument("--force", action="store_true", help="Initialize even if directory is non-empty")

    # lint
    p_lint = sub.add_parser("lint", help="Validate schemas, invariants, lineage, and generated artifacts")
    p_lint.add_argument("--strict", action="store_true", help="Treat warnings as errors and verify _generated/ integrity")
    p_lint.add_argument("--stale", action="store_true", help="Include staleness checks")
    p_lint.add_argument("--check-generated", action="store_true", help="Verify _generated/ views and indexes are fresh and unedited")

    # bootstrap
    p_boot = sub.add_parser("bootstrap", help="Render deterministic character-budgeted context")
    p_boot.add_argument("--profile", default=None, help="Bootstrap profile (default, executor, curator)")
    p_boot.add_argument("--budget", type=int, default=None, help="Override character budget")

    # rebuild
    p_reb = sub.add_parser("rebuild", help="Deterministically regenerate _generated/ views and indexes")
    p_reb.add_argument("--views-only", action="store_true")
    p_reb.add_argument("--indexes-only", action="store_true")

    # transact
    p_txn = sub.add_parser("transact", help="Owner-only atomic staged transactions")
    txn_sub = p_txn.add_subparsers(dest="txn_cmd", required=True)
    p_tb = txn_sub.add_parser("begin")
    p_tb.add_argument("--idempotency-key", required=True)
    p_tb.add_argument("--actor", required=True)
    p_tb.add_argument("--expected-revision", default=None)

    p_ta = txn_sub.add_parser("add")
    p_ta.add_argument("--txn-id", required=True)
    register_op_flags(p_ta)

    p_tc = txn_sub.add_parser("commit")
    p_tc.add_argument("--txn-id", required=True)
    p_tc.add_argument("--yes", action="store_true")
    p_tc.add_argument("--rebuild", action="store_true")

    p_trb = txn_sub.add_parser("rollback")
    p_trb.add_argument("--txn-id", required=True)

    p_trec = txn_sub.add_parser("recover")
    p_trec.add_argument("--yes", action="store_true")

    txn_sub.add_parser("list")

    # capture (Executor low-friction layer)
    p_cap = sub.add_parser("capture", help="Capture append-only signals or events without mutating living truth")
    cap_sub = p_cap.add_subparsers(dest="cap_cmd", required=True)
    p_csig = cap_sub.add_parser("signal")
    p_csig.add_argument("--emitted-by", required=True)
    p_csig.add_argument("--kind", required=True, choices=SIGNAL_KINDS)
    p_csig.add_argument("--summary", required=True)
    p_csig.add_argument("--severity", default="medium", choices=["low", "medium", "high"])
    p_csig.add_argument("--target-namespace", default="facts", choices=NAMESPACES)
    p_csig.add_argument("--entities", nargs="+")
    p_csig.add_argument("--related-paths", nargs="+")
    p_csig.add_argument("--evidence", nargs="+")
    p_csig.add_argument("--idempotency-key", default=None)
    p_csig.add_argument("--body", default="")

    p_cevt = cap_sub.add_parser("event")
    p_cevt.add_argument("--recorded-by", required=True)
    p_cevt.add_argument("--event-id", required=True)
    p_cevt.add_argument("--occurred-at", required=True)
    p_cevt.add_argument("--summary", required=True)
    p_cevt.add_argument("--entities", nargs="+")
    p_cevt.add_argument("--sources", nargs="+")
    p_cevt.add_argument("--asserts", default=None)
    p_cevt.add_argument("--tags", nargs="+")
    p_cevt.add_argument("--body", default="")

    # curate (Decoupled Curator layer)
    p_cur = sub.add_parser("curate", help="Scan vault drift and triage signals")
    cur_sub = p_cur.add_subparsers(dest="cur_cmd", required=True)
    p_cscan = cur_sub.add_parser("scan")
    p_cscan.add_argument("--emit-signals", action="store_true")
    p_cscan.add_argument("--emitted-by", default="agent-curator-00000003")

    p_cdism = cur_sub.add_parser("dismiss-signal")
    p_cdism.add_argument("--signal-id", required=True)
    p_cdism.add_argument("--curator", required=True)
    p_cdism.add_argument("--reason", required=True)
    p_cdism.add_argument("--yes", action="store_true")
    p_cdism.add_argument("--rebuild", action="store_true")

    # propose
    p_prop = sub.add_parser("propose", help="Create/list/show executable curation proposals")
    prop_sub = p_prop.add_subparsers(dest="prop_cmd", required=True)
    p_pc = prop_sub.add_parser("create")
    p_pc.add_argument("--title", required=True)
    p_pc.add_argument("--namespace", required=True, choices=NAMESPACES)
    p_pc.add_argument("--proposer", required=True)
    p_pc.add_argument("--rationale", default=None)
    p_pc.add_argument("--resolves-signals", nargs="+")
    p_pc.add_argument("--proposal-derived-from", nargs="+")
    p_pc.add_argument("--status", default="proposed", choices=["draft", "proposed"])
    p_pc.add_argument("--idempotency-key", default=None)
    register_op_flags(p_pc, exclude=("--title",))

    p_pl = prop_sub.add_parser("list")
    p_pl.add_argument("--status", default=None)
    p_pl.add_argument("--namespace", default=None)

    p_ps = prop_sub.add_parser("show")
    p_ps.add_argument("--proposal-id", required=True)

    # review
    p_rev = sub.add_parser("review", help="Submit independent hash-bound reviews")
    rev_sub = p_rev.add_subparsers(dest="rev_cmd", required=True)
    for vcmd, req_comment in (("approve", False), ("reject", True), ("request-changes", True)):
        p_rv = rev_sub.add_parser(vcmd)
        p_rv.add_argument("--proposal-id", required=True)
        p_rv.add_argument("--reviewer", required=True)
        p_rv.add_argument("--comment", required=req_comment, default=None)

    p_rl = rev_sub.add_parser("list")
    p_rl.add_argument("--proposal-id", default=None)

    # publish
    p_pub = sub.add_parser("publish", help="Atomically publish an approved proposal and close linked signals")
    p_pub.add_argument("--proposal-id", required=True)
    p_pub.add_argument("--publisher", required=True)
    p_pub.add_argument("--yes", action="store_true")
    p_pub.add_argument("--rebuild", action="store_true")

    # query
    p_qry = sub.add_parser("query", help="Query living canonical knowledge, factory state, and lineage")
    q_sub = p_qry.add_subparsers(dest="q_cmd", required=True)

    qf = q_sub.add_parser("facts")
    qf.add_argument("--entity", default=None)
    qf.add_argument("--predicate", default=None)
    qf.add_argument("--as-of", default=None)
    qf.add_argument("--history", action="store_true")
    qf.add_argument("--trust", default=None)
    qf.add_argument("--min-confidence", type=float, default=None)

    qsk = q_sub.add_parser("skills")
    qsk.add_argument("--domain", default=None)
    qsk.add_argument("--trigger", default=None)
    qsk.add_argument("--history", action="store_true")

    qgd = q_sub.add_parser("guidance")
    qgd.add_argument("--domain", default=None)
    qgd.add_argument("--scope", default=None)
    qgd.add_argument("--priority", default=None)
    qgd.add_argument("--history", action="store_true")

    qdc = q_sub.add_parser("decisions")
    qdc.add_argument("--domain", default=None)
    qdc.add_argument("--status", default="accepted")
    qdc.add_argument("--history", action="store_true")

    qev = q_sub.add_parser("events")
    qev.add_argument("--since", default=None)
    qev.add_argument("--until", default=None)
    qev.add_argument("--entity", default=None)

    qsg = q_sub.add_parser("signals")
    qsg.add_argument("--status", default=None)
    qsg.add_argument("--kind", default=None)
    qsg.add_argument("--severity", default=None)

    qpr = q_sub.add_parser("proposals")
    qpr.add_argument("--status", default=None)
    qpr.add_argument("--namespace", default=None)

    qrc = q_sub.add_parser("receipts")
    qrc.add_argument("--mode", default=None)
    qrc.add_argument("--actor", default=None)

    qres = q_sub.add_parser("resolve")
    qres.add_argument("name")

    qid = q_sub.add_parser("id")
    qid.add_argument("record_id")

    qwhy = q_sub.add_parser("why")
    qwhy.add_argument("kind", choices=["fact", "skill", "guidance", "decision"])
    qwhy.add_argument("target")
    qwhy.add_argument("predicate", nargs="?", default=None)

    qsrch = q_sub.add_parser("search")
    qsrch.add_argument("term")
    qsrch.add_argument("--types", default=None, help="Comma-separated types: fact,skill,guidance,decision")

    qgr = q_sub.add_parser("graph")
    qgr.add_argument("node")

    # migrate
    p_mig = sub.add_parser("migrate", help="Migrate a v4.0/v4.1 vault into Knowledge Factory v5.0")
    p_mig.add_argument("--source", type=Path, required=True, help="Path to source v4.x vault")
    p_mig.add_argument("--target", type=Path, required=True, help="Path to new v5.0 target vault")
    p_mig.add_argument("--yes", action="store_true")

    return parser


def dispatch(args: argparse.Namespace, root: Path, out: io.StringIO) -> tuple[int, dict[str, Any], list[str]]:
    cmd = args.command
    if cmd == "init":
        info = init_vault(args.target.resolve(), force=args.force, copy_tools_from=Path(__file__).resolve().parent)
        print(f"Initialized Knowledge Factory v5.0 vault at {args.target.resolve()}", file=out)
        return 0, info, []

    if cmd == "lint":
        findings = lint_vault(
            root,
            strict=args.strict,
            check_stale=args.stale,
            check_generated=args.check_generated,
        )
        errors = [f for f in findings if f.severity == "ERROR"]
        warns = [f for f in findings if f.severity == "WARN"]
        for f in findings:
            print(f"[{f.severity}] {f.path}: {f.message}", file=out)
        if not findings:
            print("Vault lint passed cleanly (v5.0).", file=out)
        failed = bool(errors) or (args.strict and bool(warns))
        data = {
            "error_count": len(errors),
            "warning_count": len(warns),
            "findings": [f.to_dict() for f in findings],
        }
        return (1 if failed else 0), data, [f"{f.severity}: {f.path}: {f.message}" for f in findings]

    if cmd == "bootstrap":
        text = build_bootstrap(root, profile=args.profile, budget_override=args.budget)
        out.write(text)
        return 0, {"profile": args.profile or "default", "chars": len(text), "content": text}, []

    if cmd == "rebuild":
        written = rebuild_all(root, views_only=args.views_only, indexes_only=args.indexes_only)
        print(f"Rebuilt {len(written)} generated artifact(s).", file=out)
        return 0, {"written": written}, []

    if cmd == "transact":
        subcmd = args.txn_cmd
        if subcmd == "begin":
            meta = begin_transaction(
                root,
                idempotency_key=args.idempotency_key,
                actor_id=args.actor,
                expected_revision=args.expected_revision,
            )
            print(f"Transaction {meta['transaction_id']} ({meta['status']})", file=out)
            return 0, meta, []
        if subcmd == "add":
            ops = load_ops_from_cli(args)
            meta = add_operations(root, args.txn_id, ops)
            print(f"Staged {len(ops)} op(s) on {args.txn_id} (total={len(meta['ops'])}).", file=out)
            return 0, meta, []
        if subcmd == "commit":
            res = commit_transaction(root, args.txn_id, yes=args.yes, rebuild=args.rebuild)
            print(f"Committed {args.txn_id} -> receipt {res['receipt_id']}", file=out)
            return 0, res, []
        if subcmd == "rollback":
            res = rollback_transaction(root, args.txn_id)
            print(f"Rolled back {args.txn_id}.", file=out)
            return 0, res, []
        if subcmd == "recover":
            res = recover_transactions(root, yes=args.yes)
            print(f"Recovered {len(res['recovered'])} pending transaction(s).", file=out)
            return 0, res, []
        if subcmd == "list":
            res = list_transactions(root)
            print(f"Staged: {len(res['staged'])}, Receipts: {len(res['receipts'])}", file=out)
            return 0, res, []

    if cmd == "capture":
        if args.cap_cmd == "signal":
            sig = capture_signal(
                root,
                emitted_by=args.emitted_by,
                kind=args.kind,
                summary=args.summary,
                severity=args.severity,
                target_namespace=args.target_namespace,
                entities=args.entities,
                related_paths=args.related_paths,
                evidence=args.evidence,
                idempotency_key=args.idempotency_key,
                body=args.body,
            )
            print(f"Captured signal {sig['id']} ({sig['path']})", file=out)
            return 0, sig, []
        if args.cap_cmd == "event":
            ev = capture_event(
                root,
                recorded_by=args.recorded_by,
                event_id=args.event_id,
                occurred_at=args.occurred_at,
                summary=args.summary,
                entities=args.entities,
                sources=args.sources,
                asserts_raw=args.asserts,
                tags=args.tags,
                body=args.body,
            )
            print(f"Captured event {ev['id']} ({ev['path']})", file=out)
            return 0, ev, []

    if cmd == "curate":
        if args.cur_cmd == "scan":
            res = scan_vault_drift(root, emit_signals=args.emit_signals, emitted_by=args.emitted_by)
            if not res["detections"]:
                print("No vault drift or uncurated claims detected.", file=out)
            else:
                for d in res["detections"]:
                    print(f"[{d['severity'].upper()}:{d['kind']}] {d['summary']}", file=out)
            return 0, res, []
        if args.cur_cmd == "dismiss-signal":
            res = dismiss_signal(
                root,
                signal_id=args.signal_id,
                curator_id=args.curator,
                reason=args.reason,
                yes=args.yes,
                rebuild=args.rebuild,
            )
            print(f"Dismissed signal {args.signal_id} -> receipt {res.get('receipt_id')}", file=out)
            return 0, res, []

    if cmd == "propose":
        if args.prop_cmd == "create":
            ops = load_ops_from_cli(args)
            prop = create_proposal(
                root,
                title=args.title,
                namespace=args.namespace,
                proposer_id=args.proposer,
                ops=ops,
                rationale=args.rationale,
                resolves_signals=args.resolves_signals,
                derived_from=args.proposal_derived_from,
                status=args.status,
                idempotency_key=args.idempotency_key,
            )
            print(f"Created proposal {prop['id']} ({prop['status']})", file=out)
            return 0, prop, []
        if args.prop_cmd == "list":
            rows = list_proposals(root, status=args.status, namespace=args.namespace)
            for r in rows:
                print(f"{r['id']}  [{r['status']}]  {r['namespace']}  {r['title']}", file=out)
            if not rows:
                print("No proposals found.", file=out)
            return 0, {"proposals": rows}, []
        if args.prop_cmd == "show":
            info = show_proposal(root, args.proposal_id)
            print(f"{info['id']} [{info['status']}] — {info['title']} (reviews={len(info['reviews'])})", file=out)
            return 0, info, []

    if cmd == "review":
        if args.rev_cmd == "list":
            revs = list_reviews(root, proposal_id=args.proposal_id)
            for r in revs:
                print(f"{r['id']}  {r['verdict']}  by {r['reviewer_id']}  on {r['proposal_id']}", file=out)
            if not revs:
                print("No reviews found.", file=out)
            return 0, {"reviews": revs}, []
        verdict_map = {"approve": "approved", "reject": "rejected", "request-changes": "changes_requested"}
        rev = submit_review(
            root,
            proposal_id=args.proposal_id,
            reviewer_id=args.reviewer,
            verdict=verdict_map[args.rev_cmd],
            comment=args.comment,
        )
        print(f"Review {rev['id']} ({rev['verdict']}) -> proposal status: {rev['proposal_status']}", file=out)
        return 0, rev, []

    if cmd == "publish":
        pub = publish_proposal(
            root,
            proposal_id=args.proposal_id,
            publisher_id=args.publisher,
            yes=args.yes,
            rebuild=args.rebuild,
        )
        print(f"Published {args.proposal_id} -> receipt {pub['receipt_id']}", file=out)
        return 0, pub, []

    if cmd == "query":
        q = args.q_cmd
        if q == "facts":
            txt, rows = query_facts(
                root,
                entity=args.entity,
                predicate=args.predicate,
                as_of=args.as_of,
                history=args.history,
                trust=args.trust,
                min_confidence=args.min_confidence,
            )
            out.write(txt)
            return 0, {"facts": rows}, []
        if q == "skills":
            txt, rows = query_skills(root, domain=args.domain, trigger=args.trigger, history=args.history)
            out.write(txt)
            return 0, {"skills": rows}, []
        if q == "guidance":
            txt, rows = query_guidance(root, domain=args.domain, scope=args.scope, priority=args.priority, history=args.history)
            out.write(txt)
            return 0, {"guidance": rows}, []
        if q == "decisions":
            txt, rows = query_decisions(root, domain=args.domain, status=args.status, history=args.history)
            out.write(txt)
            return 0, {"decisions": rows}, []
        if q == "events":
            txt, rows = query_events(root, since=args.since, until=args.until, entity=args.entity)
            out.write(txt)
            return 0, {"events": rows}, []
        if q == "signals":
            txt, rows = query_signals(root, status=args.status, kind=args.kind, severity=args.severity)
            out.write(txt)
            return 0, {"signals": rows}, []
        if q == "proposals":
            rows = list_proposals(root, status=args.status, namespace=args.namespace)
            for r in rows:
                print(f"{r['id']}  [{r['status']}]  {r['namespace']}  {r['title']}", file=out)
            if not rows:
                print("No proposals found.", file=out)
            return 0, {"proposals": rows}, []
        if q == "receipts":
            txt, rows = query_receipts(root, mode=args.mode, actor=args.actor)
            out.write(txt)
            return 0, {"receipts": rows}, []
        if q == "resolve":
            code, txt, payload = query_resolve_entity(root, args.name)
            out.write(txt)
            return code, payload, ([] if code == 0 else [txt.strip()])
        if q == "id":
            code, txt, payload = query_by_id(root, args.record_id)
            out.write(txt)
            return code, payload, ([] if code == 0 else [txt.strip()])
        if q == "why":
            txt, payload = query_why(root, kind=args.kind, target=args.target, predicate=args.predicate)
            out.write(txt)
            return 0, payload, []
        if q == "search":
            tset = {s.strip() for s in args.types.split(",") if s.strip()} if args.types else None
            txt, rows, diags = query_search(root, args.term, types=tset)
            out.write(txt)
            return 0, {"results": rows}, diags
        if q == "graph":
            txt, rows, diags = query_graph(root, args.node)
            out.write(txt)
            return 0, {"relationships": rows}, diags

    if cmd == "migrate":
        res = migrate_v4_to_v5(args.source, args.target, yes=args.yes)
        print(
            f"Migrated v{res['from_version']} vault -> v5.0 at {args.target.resolve()} (receipt={res['receipt_id']})",
            file=out,
        )
        return 0, res, []

    raise ValueError(f"unknown command: {cmd}")


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    cleaned_argv, json_mode, vault_override = _extract_global_flags(raw_argv)
    parser = build_parser()
    try:
        args = parser.parse_args(cleaned_argv)
    except SystemExit as exc:
        code = int(exc.code) if isinstance(exc.code, int) else 2
        if json_mode:
            print(json.dumps({
                "ok": code == 0,
                "exit_code": code,
                "protocol_version": SPEC_VERSION,
                "command": "parse",
                "data": None,
                "text": "",
                "diagnostics": ["argument parsing exited"],
            }))
        return code

    root = vault_override or Path.cwd()
    buf = io.StringIO()
    try:
        exit_code, data, diagnostics = dispatch(args, root, buf)
        text = buf.getvalue()
        for d in diagnostics:
            if args.command != "lint":
                print(d, file=sys.stderr)
        if json_mode:
            if args.command == "lint":
                for d in diagnostics:
                    print(d, file=sys.stderr)
            print(json.dumps({
                "ok": exit_code == 0,
                "exit_code": exit_code,
                "protocol_version": SPEC_VERSION,
                "command": args.command,
                "data": data,
                "text": text,
                "diagnostics": diagnostics,
            }, ensure_ascii=False))
        else:
            sys.stdout.write(text)
        return exit_code
    except Exception as exc:
        msg = f"ERROR: {exc}"
        print(msg, file=sys.stderr)
        if json_mode:
            print(json.dumps({
                "ok": False,
                "exit_code": 1,
                "protocol_version": SPEC_VERSION,
                "command": getattr(args, "command", "unknown"),
                "data": None,
                "text": "",
                "diagnostics": [msg],
            }, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
