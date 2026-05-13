#!/usr/bin/env python3
"""Validate a SPEC-v3 markdown memory vault."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
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
STABLE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
AGENT_ID_RE = re.compile(r"^agent-[a-z0-9-]+-[a-f0-9]{8}$")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SUPPORTED_SPEC_VERSION = "3.0"


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


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def safe_relative(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str) or not value:
        return False
    candidate = Path(value)
    return not candidate.is_absolute() and ".." not in candidate.parts


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


def validate_agent_id(path: Path, value: Any) -> list[str]:
    if not isinstance(value, str) or not AGENT_ID_RE.match(value):
        return [f"'agent_id' must match {AGENT_ID_RE.pattern}"]
    return []


def validate_precondition_hash(path: Path, value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, str) or not HASH_RE.match(value):
        return [f"'precondition_hash' must match {HASH_RE.pattern}"]
    return []


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


def validate_spec_version(root: Path) -> list[Finding]:
    path = root / "memory/schema/version.yaml"
    if not path.exists():
        return [Finding("ERROR", path, "missing v3 schema version marker")]
    data = load_yaml(path)
    version = data.get("spec_version")
    status = data.get("schema_status")
    findings: list[Finding] = []
    if str(version) != SUPPORTED_SPEC_VERSION:
        findings.append(Finding("ERROR", path, f"spec_version must be {SUPPORTED_SPEC_VERSION!r}"))
    if status != "stable":
        findings.append(Finding("ERROR", path, "schema_status must be 'stable'"))
    return findings


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


def validate_claims(root: Path, schema: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    claims_dir = root / "memory/_claims"
    if not claims_dir.exists():
        return findings
    for path in sorted(claims_dir.glob("*.yaml")):
        data = load_yaml(path)
        if not isinstance(data, dict):
            findings.append(Finding("ERROR", path, "claim must be a YAML object"))
            continue
        for error in validate_schema(path, data, schema):
            findings.append(Finding("ERROR", path, error))
        target_id = data.get("target_id")
        if isinstance(target_id, str) and path.stem != target_id:
            findings.append(Finding("ERROR", path, "claim filename must match target_id"))
        for error in validate_agent_id(path, data.get("agent_id")):
            findings.append(Finding("ERROR", path, error))
        for field in ("created_at", "expires_at", "heartbeat_at"):
            try:
                parse_datetime(data.get(field))
            except ValueError as exc:
                findings.append(Finding("ERROR", path, f"{field}: {exc}"))
    return findings


def validate_operation_payload(
    root: Path,
    path: Path,
    data: dict[str, Any],
    schemas: dict[str, dict[str, Any]],
    entities: set[str],
    predicates: set[str],
) -> list[Finding]:
    findings: list[Finding] = []
    payload = data.get("payload")
    op = data.get("op")
    if payload is None:
        return findings
    if not isinstance(payload, dict):
        return [Finding("ERROR", path, "'payload' must be an object")]

    payload_type = payload.get("type")
    if payload_type in schemas:
        for error in validate_schema(path, payload, schemas[payload_type]):
            findings.append(Finding("ERROR", path, f"payload: {error}"))

    if op in {"create_fact", "update_fact"}:
        if payload_type != "fact":
            findings.append(Finding("ERROR", path, f"{op} payload must have type 'fact'"))
        entity = payload.get("entity")
        predicate = payload.get("predicate")
        if entity not in entities:
            findings.append(Finding("ERROR", path, f"payload unknown entity {entity!r}"))
        if predicate not in predicates:
            findings.append(Finding("ERROR", path, f"payload unknown predicate {predicate!r} — declare it in memory/schema/predicates.yaml"))
        try:
            valid_from = parse_date(payload.get("valid_from"))
            valid_to = parse_date(payload.get("valid_to"))
            if valid_from and valid_to and valid_from > valid_to:
                findings.append(Finding("ERROR", path, "payload valid_from must be <= valid_to"))
        except ValueError as exc:
            findings.append(Finding("ERROR", path, f"payload: {exc}"))
        for source in payload.get("sources", []) or []:
            if not (root / source).exists():
                findings.append(Finding("ERROR", path, f"payload source does not exist: {source} — sources: items must be filesystem paths relative to the vault root, not URLs"))

    if op == "add_event":
        if payload_type != "event":
            findings.append(Finding("ERROR", path, "add_event payload must have type 'event'"))
        for entity in payload.get("entities", []) or []:
            if entity not in entities:
                findings.append(Finding("ERROR", path, f"payload unknown event entity {entity!r}"))
        for source in payload.get("sources", []) or []:
            if not (root / source).exists():
                findings.append(Finding("ERROR", path, f"payload source does not exist: {source} — sources: items must be filesystem paths relative to the vault root, not URLs"))

    return findings


def validate(root: Path) -> list[Finding]:
    findings: list[Finding] = validate_spec_version(root)
    schema_dir = root / "memory/schema"
    schemas = {path.stem.replace(".schema", ""): load_yaml(path) for path in schema_dir.glob("*.schema.yaml")}
    if "claim" in schemas:
        findings.extend(validate_claims(root, schemas["claim"]))
    entities = load_entities(root)
    predicates = load_predicates(root)
    targets, by_stem = existing_link_targets(root)
    facts: list[tuple[Path, dict[str, Any]]] = []
    stable_ids: dict[str, Path] = {}
    operation_ids: dict[str, Path] = {}

    for path in markdown_files(root):
        if "/_views/" in path.as_posix():
            continue
        in_inbox = "/_inbox/" in path.as_posix()
        in_archive = "/_archive/" in path.as_posix()
        in_ops = "/_ops/" in path.as_posix()
        data, body = split_frontmatter(path)
        typ = data.get("type")
        if typ in schemas:
            for error in validate_schema(path, data, schemas[typ]):
                findings.append(Finding("ERROR", path, error))
        elif typ and typ not in {"entity-index", "source"}:
            findings.append(Finding("ERROR", path, f"unknown type {typ!r}"))

        stable_id = data.get("id")
        if typ not in {"decision", "entity-index"} and stable_id:
            if not isinstance(stable_id, str) or not STABLE_ID_RE.match(stable_id):
                findings.append(Finding("ERROR", path, f"id must match {STABLE_ID_RE.pattern}"))
            elif stable_id in stable_ids:
                findings.append(Finding("ERROR", path, f"duplicate id {stable_id!r} also used by {rel(stable_ids[stable_id], root)}"))
            else:
                stable_ids[stable_id] = path

        if typ == "fact":
            if not in_inbox and not in_archive:
                facts.append((path, data))
            entity = data.get("entity")
            predicate = data.get("predicate")
            if entity not in entities:
                findings.append(Finding("ERROR", path, f"unknown entity {entity!r}"))
            if predicate not in predicates:
                findings.append(Finding("ERROR", path, f"unknown predicate {predicate!r} — declare it in memory/schema/predicates.yaml"))
            expected_dir = root / "memory/facts" / str(entity)
            if not in_inbox and not in_archive and path.parent != expected_dir:
                findings.append(Finding("ERROR", path, f"fact must live in memory/facts/{entity}/"))
            if not in_inbox and not in_archive and isinstance(predicate, str) and not (path.stem == predicate or path.stem.startswith(f"{predicate}--")):
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
                    findings.append(Finding("ERROR", path, f"source does not exist: {source} — sources: items must be filesystem paths relative to the vault root, not URLs"))

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
                    findings.append(Finding("ERROR", path, f"source does not exist: {source} — sources: items must be filesystem paths relative to the vault root, not URLs"))
            for derived in data.get("derived_facts", []) or []:
                if not (root / derived).exists():
                    findings.append(Finding("ERROR", path, f"derived fact does not exist: {derived}"))

        if typ == "operation":
            if not in_inbox and not in_ops:
                findings.append(Finding("ERROR", path, "operations must live in memory/_inbox/ or memory/_ops/"))
            operation_id = data.get("operation_id")
            if isinstance(operation_id, str):
                if operation_id in operation_ids:
                    findings.append(Finding("ERROR", path, f"duplicate operation_id {operation_id!r} also used by {rel(operation_ids[operation_id], root)}"))
                else:
                    operation_ids[operation_id] = path
            for error in validate_agent_id(path, data.get("agent_id")):
                findings.append(Finding("ERROR", path, error))
            for error in validate_precondition_hash(path, data.get("precondition_hash")):
                findings.append(Finding("ERROR", path, error))
            target_path = data.get("target_path")
            if not safe_relative(target_path):
                findings.append(Finding("ERROR", path, "target_path must be a relative path without '..'"))
            for source in data.get("sources", []) or []:
                if not (root / source).exists():
                    findings.append(Finding("ERROR", path, f"source does not exist: {source} — sources: items must be filesystem paths relative to the vault root, not URLs"))
            findings.extend(validate_operation_payload(root, path, data, schemas, entities, predicates))

        if typ in {"decision", "insight"}:
            for entity in data.get("entities", []) or []:
                if entity not in entities:
                    findings.append(Finding("ERROR", path, f"unknown {typ} entity {entity!r}"))
            for source in data.get("sources", []) or []:
                if not (root / source).exists():
                    findings.append(Finding("ERROR", path, f"source does not exist: {source} — sources: items must be filesystem paths relative to the vault root, not URLs"))

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
