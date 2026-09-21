#!/usr/bin/env sh
# Regenerate deterministic v4 lexical and graph indexes.
set -eu
VAULT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -x "$VAULT_ROOT/.venv/bin/python" ]; then
    PYTHON="$VAULT_ROOT/.venv/bin/python"
else
    PYTHON="python3"
fi
cd "$VAULT_ROOT"
"$PYTHON" tools/rebuild_indexes.py "$@"
