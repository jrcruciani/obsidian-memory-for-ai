# Repository Instructions — Knowledge Factory v5.0

## Verification Commands

```bash
# 1. Lint the v5.0 reference vault (strict schema, lineage, and _generated/ tamper check)
KF_TODAY=2026-10-15 python3 tools/kf.py --vault examples/v5-knowledge-factory lint --strict

# 2. Rebuild _generated/ views and indexes and confirm zero drift
KF_TODAY=2026-10-15 python3 tools/kf.py --vault examples/v5-knowledge-factory rebuild
git diff --exit-code -- examples/v5-knowledge-factory/_generated

# 3. Run the full offline unit, governance, lineage, and v4.1->v5.0 migration test suite
python3 -m unittest discover -s tests -v

# 4. Run the 26-contract offline deterministic query evaluation gate
python3 tests/eval/run_eval.py
```

## Architecture Overview

This repository defines **Obsidian Memory for AI v5.0: The Knowledge Factory Protocol** (`SPEC-v5.0.md`).
Canonical truth is always plain Markdown + YAML frontmatter + Git—never a database, daemon, vector store, or binary file.

- `tools/kf.py` + `tools/kflib/` is the unified portable CLI (kept byte-identical with `examples/v5-knowledge-factory/tools/`).
- Vaults have four planes: `sources/` (immutable evidence), `knowledge/` (living `entities.md`, `facts/`, `events/`, `skills/`, `guidance/`, `decisions/`, and non-authoritative `notes/`), `factory/` (`schema/`, `signals/`, `proposals/`, `reviews/`, `receipts/`), and `_generated/` (non-editable `views/` and `indexes/`).
- Never hand-edit `_generated/`; run `kf.py rebuild`.
- Respect role boundaries in `factory/schema/policy.yaml`: Executors capture `signals`/`events`; Curators scan drift and author `proposals`; independent Reviewers approve and `publish`.
