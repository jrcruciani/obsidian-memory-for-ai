#!/usr/bin/env python3
"""Analyze canonical records and emit idempotent diagnostic proposal drafts."""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml
import cli

from lint import WIKILINK_RE, link_exists, parse_date, parse_datetime, rel, split_frontmatter
from memory_model import current, observed, records, safe_path, today
from propose import CONSOLIDATOR, create_proposal


def detections(root: Path) -> list[dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}

    def detect(kind: str, paths: list[str], title: str, details: list[str]) -> None:
        paths = sorted(set(paths))
        key = f"consolidate:{kind}:" + hashlib.sha256("\n".join(paths).encode()).hexdigest()
        results[key] = {"kind": kind, "paths": paths, "title": title, "details": details, "idempotency_key": key}

    facts = records(root, "memory/facts", "fact")
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for path, data in facts:
        relative = rel(path, root)
        entity, predicate = data.get("entity"), data.get("predicate")
        if current(data):
            groups[(str(entity), str(predicate))].append(relative)
        end = parse_date(data.get("valid_until"))
        slot = f"memory/facts/{entity}/{predicate}.md"
        if end and end < today() and relative == slot:
            detect("expired-current", [relative], f"Expired fact remains in current slot: {entity}/{predicate}",
                   [f"valid_until {end} has passed; review the history layout"])
        for reference in data.get("derived_from", []):
            evidence = safe_path(root, reference, ("memory/events/", "sources/"))
            if not evidence.is_file():
                continue  # Reported below as a dangling reference, not ignored.
            event, _ = split_frontmatter(evidence)
            if event.get("type") != "event" or not current(data):
                continue
            if parse_datetime(event["occurred_at"]) <= observed(data):
                continue
            claims = event.get("asserts", [])
            if not isinstance(claims, list) or any(not isinstance(claim, dict) for claim in claims):
                raise ValueError(f"{reference}: asserts must be a list of claim objects")
            changed = [claim for claim in claims if claim.get("entity") == entity
                       and claim.get("predicate") == predicate and claim.get("value") != data.get("value")]
            if changed:
                detect("newer-assertion", [relative, reference], f"Newer evidence contradicts {entity}/{predicate}",
                       [f"Fact value: {data.get('value')!r}; event claims: {changed!r}"])
    for (entity, predicate), paths in sorted(groups.items()):
        if len(paths) > 1:
            detect("duplicate-current", paths, f"Multiple current facts for {entity}/{predicate}",
                   ["Choose the correct value and temporal windows; do not silently discard either assertion"])

    canonical = [path for path in sorted((root / "memory").rglob("*.md"))
                 if not any(part.startswith("_") for part in path.relative_to(root / "memory").parts)]
    targets: set[str] = set()
    by_stem: dict[str, list[str]] = defaultdict(list)
    for path in canonical:
        relative = rel(path, root)
        targets.update((relative, relative.removesuffix(".md")))
        by_stem[path.stem].append(relative.removesuffix(".md"))
    for path in canonical:
        data, body = split_frontmatter(path)
        missing = []
        for reference in data.get("derived_from", []):
            if not safe_path(root, reference, ("memory/events/", "sources/")).is_file():
                missing.append(reference)
        for link in WIKILINK_RE.findall(body):
            exists, ambiguous = link_exists(link, targets, by_stem)
            if not exists or ambiguous:
                missing.append(link)
        if missing:
            relative = rel(path, root)
            detect("dangling-reference", [relative, *missing], f"Dangling references in {relative}",
                   sorted(set(missing)))
    return [results[key] for key in sorted(results)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit detections and drafts as JSON")
    parser.add_argument("--dry-run", action="store_true", help="Analyze without creating drafts")
    args = parser.parse_args()
    root = Path.cwd()
    try:
        findings = detections(root)
        proposals = []
        for finding in findings:
            if args.dry_run:
                print(f"{finding['kind']}: {finding['title']}")
            else:
                data = create_proposal(root, finding["title"], "facts", CONSOLIDATOR, [],
                                       status="draft", key=finding["idempotency_key"], diagnosis=finding)
                print(f"Draft {data['proposal_id']}: {finding['title']}")
                proposals.append(data)
        if not findings:
            print("No consolidation issues detected.")
        cli.result({"detections": findings, "proposals": proposals, "dry_run": args.dry_run})
        return 0
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(cli.run(main))
