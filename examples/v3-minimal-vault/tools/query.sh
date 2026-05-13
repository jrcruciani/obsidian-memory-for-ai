#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
if [ -x .venv/bin/python ]; then
  PY=.venv/bin/python
else
  PY=python3
fi

usage() {
  echo "Usage:"
  echo "  tools/query.sh id ID"
  echo "  tools/query.sh facts [--entity ID] [--predicate PREDICATE] [--on YYYY-MM-DD]"
  echo "  tools/query.sh events --since YYYY-MM-DD"
  echo "  tools/query.sh operations [--status STATUS]"
  echo "  tools/query.sh inbox [--agent AGENT_ID]"
  echo "  tools/query.sh claims"
  echo "  tools/query.sh stale"
  echo "  tools/query.sh contradictions"
}

cmd="${1:-}"
shift || true

case "$cmd" in
  id)
    record_id="${1:-}"
    [[ -n "$record_id" ]] || { usage; exit 2; }
    "$PY" - "$record_id" <<'PY'
import pathlib
import sys
import yaml

record_id = sys.argv[1]
root = pathlib.Path.cwd()

def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    _, fm, _ = text.split("---", 2)
    return yaml.safe_load(fm) or {}

for path in sorted((root / "memory").rglob("*.md")):
    if "/_views/" in path.as_posix():
        continue
    data = frontmatter(path)
    if data.get("id") == record_id or data.get("operation_id") == record_id:
        print(f"{path.relative_to(root)}: {data.get('type')}")
PY
    ;;
  facts)
    entity=""
    predicate=""
    on_date=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --entity) entity="$2"; shift 2 ;;
        --predicate) predicate="$2"; shift 2 ;;
        --on) on_date="$2"; shift 2 ;;
        *) usage; exit 2 ;;
      esac
    done
    "$PY" - "$entity" "$predicate" "$on_date" <<'PY'
import datetime as dt
import pathlib
import sys
import yaml

entity, predicate, on_date = sys.argv[1:4]
root = pathlib.Path.cwd()
query_date = dt.date.fromisoformat(on_date) if on_date else None

def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    _, fm, _ = text.split("---", 2)
    return yaml.safe_load(fm) or {}

def date_or(value, default):
    if value is None:
        return default
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))

if entity:
    paths = sorted((root / "memory/facts" / entity).glob("*.md"))
else:
    paths = sorted((root / "memory/facts").rglob("*.md"))

for path in paths:
    data = frontmatter(path)
    if data.get("type") != "fact":
        continue
    if predicate and data.get("predicate") != predicate:
        continue
    if query_date:
        start = date_or(data.get("valid_from"), dt.date.min)
        end = date_or(data.get("valid_to"), dt.date.max)
        if not (start <= query_date <= end):
            continue
    print(f"{path.relative_to(root)}: {data.get('predicate')} = {data.get('value')}")
PY
    ;;
  events)
    since=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --since) since="$2"; shift 2 ;;
        *) usage; exit 2 ;;
      esac
    done
    [[ -n "$since" ]] || { usage; exit 2; }
    find memory/events -name '*.md' | sort | while read -r file; do
      date_part="$(basename "$(dirname "$file")")"
      [[ "$date_part" < "$since" ]] && continue
      summary="$("$PY" - "$file" <<'PY'
import pathlib, sys, yaml
text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
if not text.startswith("---\n"):
    print("")
    raise SystemExit(0)
_, fm, _ = text.split("---", 2)
print((yaml.safe_load(fm) or {}).get("summary", ""))
PY
)"
      echo "$file: $summary"
    done
    ;;
  operations)
    status=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --status) status="$2"; shift 2 ;;
        *) usage; exit 2 ;;
      esac
    done
    "$PY" - "$status" <<'PY'
import pathlib
import sys
import yaml

status = sys.argv[1]
root = pathlib.Path.cwd()

def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    _, fm, _ = text.split("---", 2)
    return yaml.safe_load(fm) or {}

for base in (root / "memory/_inbox", root / "memory/_ops"):
    if not base.exists():
        continue
    for path in sorted(base.rglob("*.md")):
        data = frontmatter(path)
        if data.get("type") != "operation":
            continue
        if status and data.get("status") != status:
            continue
        print(f"{path.relative_to(root)}: {data.get('status')} {data.get('operation_id')} {data.get('op')}")
PY
    ;;
  inbox)
    agent=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --agent) agent="$2"; shift 2 ;;
        *) usage; exit 2 ;;
      esac
    done
    "$PY" - "$agent" <<'PY'
import pathlib
import sys
import yaml

agent = sys.argv[1]
root = pathlib.Path.cwd()

def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    _, fm, _ = text.split("---", 2)
    return yaml.safe_load(fm) or {}

base = root / "memory/_inbox"
for path in (sorted(base.rglob("*.md")) if base.exists() else []):
    data = frontmatter(path)
    if agent and data.get("agent_id") != agent and f"/{agent}/" not in path.as_posix():
        continue
    print(f"{path.relative_to(root)}: {data.get('type')} {data.get('status', '')}")
PY
    ;;
  claims)
    cat memory/_views/claims.md
    ;;
  stale)
    cat memory/_views/stale.md
    ;;
  contradictions)
    cat memory/_views/contradictions.md
    ;;
  *)
    usage
    exit 2
    ;;
esac
