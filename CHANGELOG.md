# Changelog

## Unreleased - v3.1 agentic hardening

- Adds markdown-native operation envelopes for proposed agent writes.
- Adds stable IDs to example facts, events, and insights.
- Adds advisory claim files under `memory/_claims/` and applied operation receipts under `memory/_ops/applied/`.
- Extends compaction into a validate/apply/receipt flow with precondition-hash conflict detection.
- Adds operational generated views for inbox, claims, operations, conflicts, IDs, and predicates.
- Expands `query.sh` and adds `tools/ops.py` for agent-facing operation workflows.
- Documents v3.1 as a cooperative file protocol, not a database replacement.

## v3.0.0 - 2026-05-11

Stable v3.0 turns the v3 RFC into the Atomic Markdown Memory toolkit:

- Freezes the v3.0 compatibility contract in `SPEC-v3.md`.
- Adds the `memory/schema/version.yaml` marker required by the linter.
- Keeps controlled predicates, one fact per file, generated `_views`, `_inbox` staging, and `reflect.py` as the stable defaults.
- Documents v2→v3 migration as a manual, docs-only workflow in `migration-v3.md`.
- Clarifies that Obsidian CLI, host-agent plugins, scheduled automation, and provider memory tools are optional integrations.
- Adds regression tests for linting, queries, deterministic views, and compaction.

Release checklist before tagging:

1. Run `python -m unittest discover -s tests`.
2. Run `python3 tools/lint.py` in `examples/v3-minimal-vault/`.
3. Run `MEMORY_TODAY=2026-05-11 tools/rebuild-views.sh` in `examples/v3-minimal-vault/`.
4. Confirm `git diff --exit-code -- memory/_views` is clean.
5. Review `SPEC-v3.md`, `README.md`, and `migration-v3.md` for release-blocking edits.
6. Tag `v3.0.0` after maintainer review.
