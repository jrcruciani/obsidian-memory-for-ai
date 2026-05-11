#!/usr/bin/env python3
"""Validate a SPEC-v3 markdown memory vault."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - exercised in user environments
    print("PyYAML is required. Install with: python3 -m pip install PyYAML", file=sys.stderr)
    sys.exit(2)


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
SLUG_RE = re.compile(r"^[a-z0-9-]+$")


class Finding:
    def __init__(self, level: str, path: Path, message: str) -> None:
        self.level = level
        self.path = path
        self.message = message

    def __str__(self) -> str:
        return f"{self.level}: {self.path}: {self.message}"


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def split_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    data = yaml.safe_load(match.group(1)) or {}
    if not isinstance(data, dict):
        return {}, text[match.end() :]
    return data, text[match.end() :]


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def parse_date(value: Any) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        return dt.date.fromisoformat(value)
    raise ValueError(f"not a date: {value!r}")


def parse_datetime(value: Any) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value
    if not isinstance(value, str):
        raise ValueError(f"not a date-time: {value!r}")
    normalized = value.replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("date-time must include timezone")
    return parsed


def validate_type(value: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return any(validate_type(value, item) for item in expected)
    if expected == "null":
        return value is None
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def validate_schema(path: Path, data: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in schema.get("required", []):
        if field not in data:
            errors.append(f"missing required field {field!r}")

    props = schema.get("properties", {})
    for field, rules in props.items():
        if field not in data:
            continue
        value = data[field]
        if "const" in rules and value != rules["const"]:
            errors.append(f"{field!r} must be {rules['const']!r}")
        if "enum" in rules and value not in rules["enum"]:
            errors.append(f"{field!r} must be one of {rules['enum']!r}")
        formatted_scalar = rules.get("format") in {"date", "date-time"} and isinstance(value, (dt.date, dt.datetime))
        if "type" in rules and not formatted_scalar and not validate_type(value, rules["type"]):
            errors.append(f"{field!r} has invalid type")
        if "pattern" in rules and isinstance(value, str) and not re.match(rules["pattern"], value):
            errors.append(f"{field!r} does not match pattern {rules['pattern']}")
        if rules.get("format") == "date" and value is not None:
            try:
                parse_date(value)
            except ValueError as exc:
                errors.append(f"{field!r} invalid date: {exc}")
        if rules.get("format") == "date-time":
            try:
                parse_datetime(value)
            except ValueError as exc:
                errors.append(f"{field!r} invalid date-time: {exc}")
        if rules.get("type") == "array" and isinstance(value, list):
            item_rules = rules.get("items", {})
            for item in value:
                if "type" in item_rules and not validate_type(item, item_rules["type"]):
                    errors.append(f"{field!r} contains item with invalid type")
    return errors


def load_entities(root: Path) -> set[str]:
    data, _ = split_frontmatter(root / "memory/entities.md")
    return {item["id"] for item in data.get("entities", []) if isinstance(item, dict) and "id" in item}


def load_predicates(root: Path) -> set[str]:
    data = load_yaml(root / "memory/schema/predicates.yaml")
    return {item["id"] for item in data.get("predicates", []) if isinstance(item, dict) and "id" in item}


def markdown_files(root: Path) -> list[Path]:
    return sorted((root / "memory").rglob("*.md"))


def existing_link_targets(root: Path) -> tuple[set[str], dict[str, list[str]]]:
    targets: set[str] = set()
    by_stem: dict[str, list[str]] = {}
    for path in markdown_files(root):
        relative = rel(path, root)
        no_ext = relative[:-3]
        targets.add(relative)
        targets.add(no_ext)
        by_stem.setdefault(path.stem, []).append(no_ext)
    return targets, by_stem


def link_exists(link: str, targets: set[str], by_stem: dict[str, list[str]]) -> tuple[bool, bool]:
    normalized = link.strip().removesuffix(".md")
    if normalized in targets or f"{normalized}.md" in targets:
        return True, False
    candidates = by_stem.get(Path(normalized).name, [])
    if len(candidates) == 1:
        return True, False
    if len(candidates) > 1:
        return False, True
    return False, False


def fact_interval(data: dict[str, Any]) -> tuple[dt.date, dt.date]:
    start = parse_date(data.get("valid_from")) or dt.date.min
    end = parse_date(data.get("valid_to")) or dt.date.max
    return start, end


def overlaps(a: tuple[dt.date, dt.date], b: tuple[dt.date, dt.date]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def validate(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    schema_dir = root / "memory/schema"
    schemas = {path.stem.replace(".schema", ""): load_yaml(path) for path in schema_dir.glob("*.schema.yaml")}
    entities = load_entities(root)
    predicates = load_predicates(root)
    targets, by_stem = existing_link_targets(root)
    facts: list[tuple[Path, dict[str, Any]]] = []

    for path in markdown_files(root):
        if "/_views/" in path.as_posix():
            continue
        in_inbox = "/_inbox/" in path.as_posix()
        data, body = split_frontmatter(path)
        typ = data.get("type")
        if typ in schemas:
            for error in validate_schema(path, data, schemas[typ]):
                findings.append(Finding("ERROR", path, error))
        elif typ and typ not in {"entity-index", "source"}:
            findings.append(Finding("ERROR", path, f"unknown type {typ!r}"))

        if typ == "fact":
            facts.append((path, data))
            entity = data.get("entity")
            predicate = data.get("predicate")
            if entity not in entities:
                findings.append(Finding("ERROR", path, f"unknown entity {entity!r}"))
            if predicate not in predicates:
                findings.append(Finding("ERROR", path, f"unknown predicate {predicate!r}"))
            expected_dir = root / "memory/facts" / str(entity)
            if not in_inbox and path.parent != expected_dir:
                findings.append(Finding("ERROR", path, f"fact must live in memory/facts/{entity}/"))
            if not in_inbox and isinstance(predicate, str) and not (path.stem == predicate or path.stem.startswith(f"{predicate}--")):
                findings.append(Finding("ERROR", path, "fact filename must be predicate.md or predicate--suffix.md"))
            try:
                valid_from = parse_date(data.get("valid_from"))
                valid_to = parse_date(data.get("valid_to"))
                if valid_from and valid_to and valid_from > valid_to:
                    findings.append(Finding("ERROR", path, "valid_from must be <= valid_to"))
            except ValueError as exc:
                findings.append(Finding("ERROR", path, str(exc)))
            superseded_by = data.get("superseded_by")
            if superseded_by:
                target = root / superseded_by
                if not target.exists():
                    findings.append(Finding("ERROR", path, f"superseded_by target does not exist: {superseded_by}"))
            for source in data.get("sources", []) or []:
                if not (root / source).exists():
                    findings.append(Finding("ERROR", path, f"source does not exist: {source}"))

        if typ == "event":
            for entity in data.get("entities", []) or []:
                if entity not in entities:
                    findings.append(Finding("ERROR", path, f"unknown event entity {entity!r}"))
            try:
                occurred = parse_datetime(data.get("occurred_at"))
                expected_date = path.parent.name
                if occurred.astimezone(dt.timezone.utc).date().isoformat() != expected_date:
                    findings.append(Finding("ERROR", path, "event directory date must match occurred_at UTC date"))
            except ValueError as exc:
                findings.append(Finding("ERROR", path, str(exc)))
            for source in data.get("sources", []) or []:
                if not (root / source).exists():
                    findings.append(Finding("ERROR", path, f"source does not exist: {source}"))
            for derived in data.get("derived_facts", []) or []:
                if not (root / derived).exists():
                    findings.append(Finding("ERROR", path, f"derived fact does not exist: {derived}"))

        if typ in {"decision", "insight"}:
            for entity in data.get("entities", []) or []:
                if entity not in entities:
                    findings.append(Finding("ERROR", path, f"unknown {typ} entity {entity!r}"))
            for source in data.get("sources", []) or []:
                if not (root / source).exists():
                    findings.append(Finding("ERROR", path, f"source does not exist: {source}"))

        if typ == "entity-index":
            for item in data.get("entities", []) or []:
                if not isinstance(item, dict):
                    findings.append(Finding("ERROR", path, "entities must be objects"))
                    continue
                if not SLUG_RE.match(str(item.get("id", ""))):
                    findings.append(Finding("ERROR", path, f"invalid entity id {item.get('id')!r}"))

        for link in WIKILINK_RE.findall(body):
            exists, ambiguous = link_exists(link, targets, by_stem)
            if ambiguous:
                findings.append(Finding("ERROR", path, f"ambiguous wikilink: {link}"))
            elif not exists:
                findings.append(Finding("ERROR", path, f"unresolved wikilink: {link}"))

    for i, (path_a, data_a) in enumerate(facts):
        for path_b, data_b in facts[i + 1 :]:
            if data_a.get("entity") != data_b.get("entity") or data_a.get("predicate") != data_b.get("predicate"):
                continue
            if data_a.get("value") == data_b.get("value"):
                continue
            try:
                if not overlaps(fact_interval(data_a), fact_interval(data_b)):
                    continue
            except ValueError:
                continue
            rel_a = rel(path_a, root)
            rel_b = rel(path_b, root)
            if data_a.get("superseded_by") == rel_b or data_b.get("superseded_by") == rel_a:
                continue
            findings.append(Finding("ERROR", path_a, f"contradicts overlapping fact {rel_b}"))

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=Path.cwd(), type=Path, help="Vault root")
    args = parser.parse_args()
    root = args.root.resolve()
    findings = validate(root)
    for finding in findings:
        print(finding)
    return 1 if any(item.level == "ERROR" for item in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
