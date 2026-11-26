# Changelog

## v5.1.0 - 2026-11-26

**Personal Memory Mode, Hybrid Retrieval, Locking, OKF v0.2 Interop & Stdio MCP**

- **Personal Memory Mode (`init --profile personal`, `remember`, `forget`, `note`):** Streamlines single-owner personal vaults with 1-command bitemporal fact capture/supersession (`auto_entity`, `allow_custom_predicates`, audit receipts), non-destructive `forget`, quick narrative `note`, and an Obsidian-native `_generated/views/dashboard.md` — while keeping `skills`, `guidance`, and `trust: external` writes review-gated against prompt injection.
- **Zero-copy shadow validation & cooperative write locking:** `validate_candidate_writes()` no longer copies `sources/` (or `tools/`/binary assets) into `/tmp`, and `kflib/locking.py` wraps mutating operations with a re-entrant cooperative lock (`factory/_staging/.kf.lock`).
- **Multi-term BM25 search & fast O(1) index drift check:** Upgrades `query search` and `query skills --trigger` from literal substring matching to NFKD-folded, field-weighted multi-term Okapi BM25 with `--include-notes`, `--include-sources`, and `--limit`; `_warn_if_index_stale()` checks embedded banner digests instead of rebuilding indexes on every query.
- **Disposable SQLite FTS5 + local Ollama embedding RRF index (`kf.py index build`, `query search --hybrid`):** Adds an optional, 100% regenerable read model at `_generated/indexes/search.sqlite` (Markdown + Git remain the sole canonical truth).
- **Multi-hop & temporal graph (`query graph --depth N --to <target> --as-of YYYY-MM-DD`):** Adds BFS neighborhood traversal, shortest-path lookup, and point-in-time fact edge filtering.
- **Token-aware bootstrap (`--max-tokens`, `chars_per_token`), normalized contradiction scanning & Sleep-Time Curation (`curate sleep-pack`):** Prevents false contradictions from whitespace/case/accent variations and bundles drift + signals + `<untrusted_source_data>` excerpts for offline LLM curation.
- **Google OKF v0.2 interoperability & forgiving lint (`export-okf`, `import-okf`, `lint --forgiving`):** Exports living knowledge to Open Knowledge Format v0.2 and forgivingly imports external bundles into immutable `sources/okf-imports/` + curation signals.
- **Ledger archival (`archive-ledger --before YYYY-MM-DD --yes`, resolving `OD-004`):** Rolls up old closed signals and unreferenced committed receipts into yearly SHA-256 rollup files under `factory/archive/`.
- **Zero-dependency stdio MCP server (`tools/kf_mcp.py`):** Exposes 12 JSON-RPC 2.0 MCP tools and 4 Markdown resources over Python stdlib.
- **Personal evaluation & scale stress gate (`tests/eval/run_personal_eval.py`):** Adds 8 LongMemEval/LoCoMo-inspired personal evaluations (including a 280-doc + 50 MB `sources/` stress test) and 17 new TDD unit/integration tests (58/58 total tests passing in both PyYAML and `KF_NO_PYYAML=1` modes).

## v5.0.0 - 2026-11-22

**The Knowledge Factory Reboot — Clean-Break v5.0 Protocol & Unified Toolkit**

- **Protocol & architecture reboot (`SPEC-v5.0.md`):** Replaces the passive single-folder `memory/` model with a four-plane Knowledge Factory architecture (`sources/`, `knowledge/`, `factory/`, `_generated/`) and an explicit five-stage loop (`capture → curate → review → publish → consume`).
- **Nine first-class governed canonical types:** `fact`, `event`, `skill`, `guidance`, `decision`, `signal`, `proposal`, `review`, and `receipt` (plus `entity-registry` and non-authoritative `note`), each backed by live declarative schemas in `factory/schema/*.schema.yaml`.
- **Executor vs. Curator vs. Reviewer separation:**
  - Executors consume role-budgeted context (`bootstrap --profile executor`) and emit low-friction append-only `signals` and `events`, and are blocked from direct transactions or unreviewed canonical writes.
  - Curators run `curate scan --emit-signals`, triage open signals (`dismiss-signal`), and author executable proposals (`propose create`).
  - Independent Reviewers/Owners submit hash-bound `reviews` and atomically `publish` proposals, automatically resolving linked `signals` and emitting unified `receipts`.
- **Unified zero-wrapper CLI (`tools/kf.py` + `tools/kflib/`):** Consolidates 14 legacy Python/Bash scripts into a single portable CLI supporting `--json` across `init`, `lint`, `bootstrap`, `capture`, `curate`, `propose`, `review`, `publish`, `transact`, `query`, `rebuild`, and `migrate`, with a built-in stdlib YAML parser/dumper fallback when `PyYAML` is absent.
- **Full end-to-end lineage (`kf.py query why`):** Traces any living `fact`, `skill`, `guidance`, or `decision` through its `supersedes` chain, `derived_from` primary sources/events, authoring `receipt`, `proposal`, `reviews`, and originating `signals`.
- **Non-editable `_generated/` read models:** Embeds `source_digest` and `content_sha256` banners in all generated views and indexes; `lint --strict` fails on hand-edits or drift, while `query search` and `query graph` guarantee canonical filesystem parity.
- **Legacy retirement & automated migration (`kf.py migrate`):** Retires v3 `_inbox/`, `_claims/`, `_ops/`, `compact.py`, `archive_fact`, qualitative string confidence (`high|medium|low`), inclusive `valid_to`, and empty diagnostic proposals (`ops: []`). Provides automated `v4.x → v5.0` migration preserving v4 audit logs in `sources/v4-audit-archive/`, converting qualitative confidence to `null` + curation signal (without fabricating numbers), and validating with `lint --strict`.
- **Offline verification & CI:** Ships `examples/v5-knowledge-factory/`, comprehensive TDD unit/integration/migration suites (`tests/test_v5_*.py`), 26 offline exact-query contracts (`tests/eval/`), and `.github/workflows/knowledge-factory-v5.yml`.

## v4.1.0 - 2026-09-21

**Temporal, Traceable Atomic Markdown Memory — additive v4.1**

- Preserves superseded facts with world-valid and observed times, as-of/history
  queries, history indexes, and per-entity timelines.
- Adds evidence lineage, assertion types, numeric confidence, and role-based
  trust caps with mandatory review for external facts when configured.
- Generates a deterministic, character-budgeted `_views/bootstrap.md`.
- Adds staleness reports and idempotent diagnostic consolidation proposals,
  including comparisons against optional structured event assertions.
- Resolves case/accent-insensitive entity aliases and ranks lexical results
  identically with missing, stale, or corrupt derived indexes.
- Adds JSON CLI envelopes, bootstrap-first agent guidance, and 21 offline
  query evaluations enforced in CI alongside regression and drift gates.
- Historical specification preserved at `docs/archive/SPEC-v4.1.md`.

## v4.0.0 - 2026-07-01

**v4 Transactional Atomic Markdown Memory**

- Added Git-native staged transactions, formal proposal/review lifecycle, and deterministic rebuildable lexical and graph indexes.

## v3.0.0 - 2026-05-11

**v3 Atomic Markdown Memory**

- Introduced one-fact-per-file Markdown records, append-only events, controlled predicates, and generated views.
