# Changelog

## v4.0.0 - 2026-07-01

**v4 Transactional Atomic Markdown Memory — three new capabilities**

### Git-native transactions
- Adds `tools/transact.py` with `begin / add / commit / rollback / recover / list` lifecycle.
- Transactions carry a stable `transaction_id` and caller-supplied `idempotency_key`; replaying a committed key is a no-op.
- Optional `expected_revision` check against Git HEAD before commit; refuses unsafe publication.
- Isolated staging under `memory/_staging/<txn-id>/` before atomically publishing to `memory/`.
- Markdown journal/receipt written to `memory/_transactions/<txn-id>.md` on every outcome.
- `recover --yes` rolls back any pending staging directories left by interrupted runs.
- Adds `memory/schema/transaction.schema.yaml`.

### Formal proposal/review lifecycle
- Adds `tools/propose.py` and `tools/review.py` with full draft→proposed→approved/rejected/changes-requested→applied lifecycle.
- Reviews are cryptographically bound to the proposal's `content_hash` at review time.
- `memory/schema/roles.yaml` stores namespace/role policy; `lint.py` and `review.py` enforce it.
- Self-approval is rejected at the tool level and by the linter.
- Unauthorized reviewers (outside `allowed_reviewers` and not `admin`) are rejected.
- Proposal governance required before `propose.py apply` proceeds.
- Adds `memory/schema/proposal.schema.yaml` and `memory/schema/review.schema.yaml`.

### Deterministic rebuildable indexes
- Adds `tools/rebuild_indexes.py` with `build_lexical_index()` and `build_graph_index()`.
- `memory/_indexes/lexical.md` — alphabetically sorted `entity/predicate = value [path]` for all facts.
- `memory/_indexes/graph.md` — entity relationship graph derived from fact values and wikilinks.
- Delete + rebuild = byte-identical output for the same canonical input.
- `tools/query.sh` extended with `search TERM` and `graph entity ENTITY`; both use index when available and fall back to direct filesystem scan, returning identical results in both modes.
- Adds `tools/rebuild-indexes.sh`.

### Reference vault
- New `examples/v4-minimal-vault/` with all v4 capabilities demonstrated.
- `memory/schema/roles.yaml` with example namespace/role policy.
- Example transaction journal, proposal, and review in `_transactions/`, `_proposals/`, `_reviews/`.

### Documentation
- New `SPEC-v4.md` — complete v4.0 protocol specification.
- New `migration-v4.md` — step-by-step v3→v4 migration guide.
- Updated `README.md` to present v4.0 as current stable; v3.1 clearly identified as previous stable.
- Updated `docs/README.md` documentation map.

### Tests
- New `tests/test_v4_tools.py` with 45 regression tests covering all v4 scenarios.
- All 62 tests pass (17 v3 + 45 v4).

### v3 compatibility
- v3 lint, views, and all 17 v3 tests continue to pass unchanged.
- `compact.py` in the v4 vault handles legacy v3-style inbox operations.

## Unreleased - documentation cleanup

- Reworks the root `README.md` as a concise v3.1 landing page.
- Adds `docs/README.md` as the canonical documentation map.
- Marks `guide.md` and `examples/minimal-vault/` as legacy v2 material.
- Rewrites optional automation and plugin guides around the current v3.1 operation-envelope workflow.

## Unreleased - v3.1.0 stable agentic protocol

- Adds markdown-native operation envelopes for proposed agent writes.
- Adds stable IDs to example facts, events, and insights.
- Adds advisory claim files under `memory/_claims/` and applied operation receipts under `memory/_ops/applied/`.
- Extends compaction into a validate/apply/receipt flow with precondition-hash conflict detection.
- Adds operational generated views for inbox, claims, operations, conflicts, IDs, and predicates.
- Expands `query.sh` and adds `tools/ops.py` for agent-facing operation workflows.
- Documents v3.1 as the current stable cooperative file protocol, not a database replacement.

## v3.0.0 - 2026-05-11

Stable v3.0 turns the v3 RFC into the Atomic Markdown Memory toolkit:

- Freezes the v3.0 compatibility contract in `SPEC-v3.md`.
- Adds the `memory/schema/version.yaml` marker required by the linter.
- Keeps controlled predicates, one fact per file, generated `_views`, `_inbox` staging, and `reflect.py` as the stable defaults.
- Documents v2→v3 migration as a manual, docs-only workflow in `migration-v3.md`.
- Clarifies that Obsidian CLI, host-agent plugins, scheduled automation, and provider memory tools are optional integrations.
- Adds regression tests for linting, queries, deterministic views, and compaction.

Historical v3.0 release checklist:

1. Run `python -m unittest discover -s tests`.
2. Run `python3 tools/lint.py` in `examples/v3-minimal-vault/`.
3. Run `MEMORY_TODAY=2026-05-11 tools/rebuild-views.sh` in `examples/v3-minimal-vault/`.
4. Confirm `git diff --exit-code -- memory/_views` is clean.
5. Review `SPEC-v3.md`, `README.md`, and `migration-v3.md` for release-blocking edits.
6. Tag `v3.0.0` after maintainer review.
