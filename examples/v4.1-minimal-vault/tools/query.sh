#!/usr/bin/env sh
# V4 memory vault query tool.
# Falls back to filesystem scanning when indexes are missing or stale.
#
# Usage:
#   query.sh facts   [--entity ENTITY] [--predicate PREDICATE]
#   query.sh events  [--since DATE]
#   query.sh id      RECORD_ID
#   query.sh operations [--status STATUS]
#   query.sh search  TERM          # lexical index with filesystem fallback
#   query.sh graph   entity ENTITY # graph index with filesystem fallback

set -eu

VAULT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS="$VAULT_ROOT/tools"

# Prefer .venv Python if available
if [ -x "$VAULT_ROOT/.venv/bin/python" ]; then
    PYTHON="$VAULT_ROOT/.venv/bin/python"
else
    PYTHON="python3"
fi

cd "$VAULT_ROOT"
exec "$PYTHON" "$TOOLS/query_impl.py" "$@"
