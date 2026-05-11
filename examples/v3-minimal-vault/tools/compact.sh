#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
python3 tools/compact.py "$@"
