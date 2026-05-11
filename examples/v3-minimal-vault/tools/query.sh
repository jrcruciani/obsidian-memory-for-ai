#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

usage() {
  echo "Usage:"
  echo "  tools/query.sh facts --entity ID [--predicate PREDICATE] [--on YYYY-MM-DD]"
  echo "  tools/query.sh events --since YYYY-MM-DD"
  echo "  tools/query.sh stale"
  echo "  tools/query.sh contradictions"
}

cmd="${1:-}"
shift || true

case "$cmd" in
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
    [[ -n "$entity" ]] || { usage; exit 2; }
    python3 - "$entity" "$predicate" "$on_date" <<'PY'
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

for path in sorted((root / "memory/facts" / entity).glob("*.md")):
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
      summary="$(python3 - "$file" <<'PY'
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
