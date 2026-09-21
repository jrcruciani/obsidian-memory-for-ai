"""Version-gated semantic checks for the additive v4.1 protocol."""

from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from lint import Finding, parse_date, parse_datetime, rel, split_frontmatter
from memory_model import confidence, current, fold, interval, observed, records, safe_path


def validate_aliases(root: Path) -> list[Finding]:
    path = root / "memory/entities.md"
    data, _ = split_frontmatter(path)
    findings = []
    owners: dict[str, str] = {}
    entries = [*data.get("entities", []),
               *(entry for _, entry in records(root, "memory/entities", "entity"))]
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        aliases = entry.get("aliases", [])
        if not isinstance(aliases, list):
            findings.append(Finding("ERROR", path, f"aliases for {entry['id']} must be a list"))
            continue
        for alias in [entry["id"], *aliases]:
            if not isinstance(alias, str) or not alias.strip():
                findings.append(Finding("ERROR", path, "aliases must be non-empty strings"))
                continue
            key = fold(alias)
            if key in owners and owners[key] != entry["id"]:
                findings.append(Finding("ERROR", path, f"alias collision: {alias!r} belongs to {owners[key]} and {entry['id']}"))
            owners[key] = entry["id"]
    return findings


def validate_assertions(root: Path, entities: set[str], predicates: set[str]) -> list[Finding]:
    findings = []
    for path, data in records(root, "memory/events", "event"):
        assertions = data.get("asserts", [])
        if not isinstance(assertions, list):
            findings.append(Finding("ERROR", path, "asserts must be a list"))
            continue
        for claim in assertions:
            if not isinstance(claim, dict) or not {"entity", "predicate", "value"} <= claim.keys():
                findings.append(Finding("ERROR", path, "asserts items require entity, predicate, value"))
            elif not isinstance(claim["entity"], str) or claim["entity"] not in entities:
                findings.append(Finding("ERROR", path, "asserts contains an unknown entity"))
            elif not isinstance(claim["predicate"], str) or claim["predicate"] not in predicates:
                findings.append(Finding("ERROR", path, "asserts contains an unknown predicate"))
    return findings


def validate_facts(root: Path, facts: list[tuple[Path, dict[str, Any]]]) -> list[Finding]:
    findings = []
    grouped: dict[tuple[str, str], list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    for path, data in facts:
        entity, predicate = data.get("entity"), data.get("predicate")
        grouped[(str(entity), str(predicate))].append((path, data))
        slot = root / "memory/facts" / str(entity) / f"{predicate}.md"
        is_history = path.parent == slot.with_suffix("")
        try:
            if current(data):
                if path != slot:
                    raise ValueError("current fact must live at memory/facts/{entity}/{predicate}.md")
            elif "valid_until" in data:
                if not is_history:
                    raise ValueError("superseded fact must live under the predicate/ history folder")
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:-[2-9]\d*|-1\d+)?", path.stem):
                    raise ValueError("history filename must be YYYY-MM-DD[-N].md (N >= 2)")
                parse_date(path.stem[:10])
            # Legacy valid_to / predicate--suffix histories remain readable.
            start, end = interval(data)
            if start > end:
                raise ValueError("valid_from must be <= valid_until")
            if data.get("valid_until") is not None and data.get("valid_to") is not None:
                raise ValueError("use valid_until or legacy valid_to, not both non-null")
            observed(data)
            confidence(data.get("confidence"))
            if data.get("assertion", "stated") not in {"stated", "inferred", "observed"}:
                raise ValueError("assertion must be stated, inferred, or observed")
            if data.get("trust", "agent") not in {"owner", "agent", "external"}:
                raise ValueError("trust must be owner, agent, or external")
            if "pinned" in data and not isinstance(data["pinned"], bool):
                raise ValueError("pinned must be boolean")
            for field in ("last_confirmed", "review_after"):
                parse_date(data.get(field))
            if data.get("status") == "retracted":
                if not data.get("retracted_at") or not data.get("reason"):
                    raise ValueError("retracted fact requires retracted_at and reason")
            evidence = data.get("derived_from", [])
            if not isinstance(evidence, list):
                raise ValueError("derived_from must be a list")
            for reference in evidence:
                target = safe_path(root, reference, ("memory/events/", "sources/"))
                if not target.is_file():
                    raise ValueError(f"derived_from path does not exist: {reference}")
            if data.get("assertion") == "inferred" and not evidence:
                findings.append(Finding("WARN", path, "inferred fact has no derived_from evidence"))
            if data.get("trust") == "external" and data.get("confidence") is None:
                findings.append(Finding("WARN", path, "external fact has no confidence"))
            previous = data.get("supersedes")
            if previous:
                target = safe_path(root, previous, ("memory/facts/",))
                if not target.is_file():
                    raise ValueError(f"supersedes path does not exist: {previous}")
                prior, _ = split_frontmatter(target)
                if target == path or prior.get("entity") != entity or prior.get("predicate") != predicate:
                    raise ValueError("supersedes must reference a previous fact for the same entity/predicate")
                old_end = parse_date(prior.get("valid_until"))
                new_start = parse_date(data.get("valid_from"))
                if old_end is None or new_start is None:
                    raise ValueError("supersedes requires previous valid_until and new valid_from")
                distance = abs((old_end - new_start).days)
                if distance == 1:
                    findings.append(Finding("WARN", path, "supersedes boundary differs by one day"))
                elif distance:
                    raise ValueError("supersedes valid_until must equal this fact's valid_from")
        except (ValueError, TypeError) as exc:
            findings.append(Finding("ERROR", path, str(exc)))
    for items in grouped.values():
        currents = [(p, d) for p, d in items if current(d)]
        # Fully ended legacy groups are valid; new history chains require a head.
        if len(currents) > 1 or (not currents and any("valid_until" in d for _, d in items)):
            findings.append(Finding("ERROR", items[0][0], "exactly one current fact is required per entity/predicate"))
        for i, (path, data) in enumerate(items):
            for other_path, other in items[i + 1:]:
                try:
                    a, b = interval(data), interval(other)
                    if max(a[0], b[0]) >= min(a[1], b[1]):
                        continue
                    adjacent = data.get("supersedes") == rel(other_path, root) or other.get("supersedes") == rel(path, root)
                    if adjacent and (min(a[1], b[1]) - max(a[0], b[0])).days <= 1:
                        continue
                    if data.get("value") != other.get("value"):
                        findings.append(Finding("ERROR", path, f"contradicts overlapping fact {rel(other_path, root)}"))
                except (ValueError, TypeError):
                    continue  # Invalid intervals already produce per-fact findings.
    return findings
