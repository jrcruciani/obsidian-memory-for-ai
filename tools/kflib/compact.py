"""Offline ledger compaction / cold archival (implements OD-004).

Rolls up old closed (`resolved`/`dismissed`) signals and committed receipts
older than `--before YYYY-MM-DD` into yearly verifiable rollup files under
`factory/archive/YYYY-ledger-rollup.md` while preserving referential integrity
for any active or remaining records.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from pathlib import Path
from typing import Any

from .locking import vault_write_lock
from .model import (
    atomic_write_text,
    file_sha256,
    iso_utc,
    parse_date,
    parse_datetime,
    rel_path,
    scan_records,
    today,
    utc_now,
)


def _record_date(fm: dict[str, Any]) -> dt.date | None:
    for key in ("resolved_at", "committed_at", "created_at"):
        raw = fm.get(key)
        if isinstance(raw, str) and raw.strip():
            try:
                return parse_datetime(raw).date()
            except ValueError:
                d = parse_date(raw)
                if d:
                    return d
    return None


def archive_ledger(
    root: Path,
    *,
    before: str,
    yes: bool = False,
) -> dict[str, Any]:
    """Archive closed signals and unreferenced committed receipts older than `before`."""
    if not yes:
        raise ValueError("archive-ledger requires --yes confirmation")
    cutoff = parse_date(before)
    if cutoff is None:
        raise ValueError(f"invalid --before date: {before!r} (expected YYYY-MM-DD)")

    with vault_write_lock(root):
        signals_to_archive: list[tuple[Path, str, dict[str, Any], int]] = []
        retained_receipt_ids: set[str] = set()

        for p, fm, _ in scan_records(root, "factory/signals", "signal"):
            r = rel_path(p, root)
            status = fm.get("status")
            rdate = _record_date(fm)
            if status in {"resolved", "dismissed"} and rdate is not None and rdate < cutoff:
                signals_to_archive.append((p, r, fm, rdate.year))
            else:
                rcpt = fm.get("resolved_by_receipt")
                if isinstance(rcpt, str) and rcpt:
                    retained_receipt_ids.add(rcpt)

        # Receipts referenced by remaining proposals must also stay in place
        for _, pfm, _ in scan_records(root, "factory/proposals", "proposal"):
            rcpt = pfm.get("published_receipt_id")
            if isinstance(rcpt, str) and rcpt:
                retained_receipt_ids.add(rcpt)

        receipts_to_archive: list[tuple[Path, str, dict[str, Any], int]] = []
        for p, fm, _ in scan_records(root, "factory/receipts", "receipt"):
            r = rel_path(p, root)
            rec_id = str(fm.get("id", ""))
            rdate = _record_date(fm)
            if (
                fm.get("status") == "committed"
                and rdate is not None
                and rdate < cutoff
                and rec_id not in retained_receipt_ids
            ):
                receipts_to_archive.append((p, r, fm, rdate.year))

        by_year: dict[int, list[str]] = defaultdict(list)
        now_iso = iso_utc(utc_now())

        for p, r, fm, year in signals_to_archive:
            sha = file_sha256(p)
            by_year[year].append(
                f"- `[signal]` `{fm.get('id')}` ({fm.get('status')}, kind=`{fm.get('kind')}`, receipt=`{fm.get('resolved_by_receipt')}`) "
                f"— {fm.get('summary')} | path=`{r}` | sha=`{sha}`"
            )
        for p, r, fm, year in receipts_to_archive:
            sha = file_sha256(p)
            by_year[year].append(
                f"- `[receipt]` `{fm.get('id')}` (mode=`{fm.get('mode')}`, actor=`{fm.get('actor_id')}`, committed=`{fm.get('committed_at')}`) "
                f"| path=`{r}` | sha=`{sha}`"
            )

        rollup_paths: list[str] = []
        archive_dir = root / "factory/archive"
        if by_year:
            archive_dir.mkdir(parents=True, exist_ok=True)
        for year, entries in sorted(by_year.items()):
            rel_rollup = f"factory/archive/{year}-ledger-rollup.md"
            rollup_path = root / rel_rollup
            header = (
                f"# Factory Ledger Cold Rollup — {year}\n\n"
                f"<!-- Archived closed signals and committed receipts before {cutoff.isoformat()} -->\n"
            )
            existing = rollup_path.read_text(encoding="utf-8") if rollup_path.is_file() else header
            block = f"\n## Compaction Batch ({now_iso}, before={cutoff.isoformat()}, ref={today().isoformat()})\n\n" + "\n".join(entries) + "\n"
            atomic_write_text(rollup_path, existing + block)
            rollup_paths.append(rel_rollup)

        # Remove archived files and prune empty signal date folders
        for p, _, _, _ in signals_to_archive:
            if p.is_file():
                p.unlink()
            if p.parent.is_dir() and not any(p.parent.iterdir()):
                p.parent.rmdir()
        for p, _, _, _ in receipts_to_archive:
            if p.is_file():
                p.unlink()

        return {
            "before": cutoff.isoformat(),
            "archived_signals": len(signals_to_archive),
            "archived_receipts": len(receipts_to_archive),
            "rollup_files": rollup_paths,
        }
