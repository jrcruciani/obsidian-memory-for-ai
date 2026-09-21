# SPEC v4.1 — Temporal, Traceable Atomic Markdown Memory

> **Status:** v4.1 implementation in progress.
> **Author:** Project maintainers
> **Date:** July 2026
> **Supersedes:** v3.1 for new implementations; v3 remains supported as the previous stable generation.
> **Reference implementation:** [`examples/v4.1-minimal-vault/`](examples/v4.1-minimal-vault/)
> **Implements (none of):** SQLite, databases, vector stores, embeddings, servers, daemons, or any binary format.

---

## TL;DR

## What changed from v4.0

| Addition | Purpose |
|---|---|
| Temporal facts | Preserve superseded values and query world-valid dates |
| Lineage and trust | Trace evidence and enforce review policies |
| Bootstrap | Deterministic core memory under a character budget |
| Consolidation | Report stale/drifting memory through review-only drafts |
| Aliases and search | Accent-folded resolution and deterministic ranking |
| Offline evaluations | Exact query contracts enforced in CI |
| Agent ergonomics | JSON CLIs and bootstrap-first instructions |

The inherited v4 contract follows; implementation-specific v4.1 details are
completed alongside each phase. Older vaults retain their versioned behavior.

v4 extends the Atomic Markdown Memory foundation from v3 with three new capabilities that address the remaining pain points in cooperative agentic memory without compromising the original promise: **Markdown/YAML and Git remain the only canonical state. The vault remains usable offline without a daemon, database, model, network service, or binary index.**

The three additions are:

1. **Robust Git-native transactions** — atomic multi-operation writes, stable idempotency keys, optional expected-revision checks, isolated staging, and Markdown journal receipts. Interrupted transactions recover safely.
2. **Formal proposal/review lifecycle** — draft-to-applied governance with cryptographically bound review records, namespace/role policy in portable YAML, and enforced self-approval prohibition.
3. **Deterministic rebuildable lexical and graph indexes** — human-readable derived indexes from canonical Markdown, guaranteed filesystem fallback when indexes are missing or stale, byte-identical rebuild from the same canonical input.

> **Convention is the new schema. Filesystem is the new index. Git is the new transaction log.**

---

## 1. What changed from v3

### v3 → v4 additions

| v3 capability | v4 addition |
|---|---|
| Operation envelopes in `_inbox/` | Full transaction lifecycle with idempotency and staged commit |
| Advisory claims | Formal proposal/review with role policy enforcement |
| `_views/` graph (wikilinks) | Dedicated `_indexes/lexical.md` and `_indexes/graph.md` with fallback guarantee |
| No compaction governance | `required_approvals` and namespace policy in `roles.yaml` |

### v3 compatibility

v3 vaults remain valid. The v4 specification is a strict superset:

- `spec_version: "4.0"` in `memory/schema/version.yaml` activates v4 validation.
- v3 operation envelopes (`_inbox/`) continue to work unchanged through `compact.py`.
- All v3 schemas, predicates, entities, and views are identical in v4.

---

## 2. Design principles

v4 inherits all v3 design principles and adds three:

### P6 — Transactions are the unit of safe multi-operation writes

Any write touching more than one file must use `tools/transact.py`. A transaction:

- Has a stable `transaction_id` (slug + timestamp + hex suffix)
- Carries a caller-supplied `idempotency_key` — replaying the same key after a commit is a no-op
- Optionally checks `expected_revision` against Git HEAD before committing
- Stages all writes under `memory/_staging/<txn-id>/` before atomically publishing them to `memory/`
- Writes a Markdown journal to `memory/_transactions/<txn-id>.md` with status: `committed`, `failed`, `rolled_back`, or `idempotent_skip`
- On failure, rolls back exactly what it applied and marks the journal `failed`

`tools/transact.py recover --yes` finds any pending staging directories and rolls them back safely.

### P7 — Proposals are the unit of review-gated writes

Changes that require human or multi-agent review use the proposal lifecycle:

```
draft → proposed → changes_requested ↘
                 ↘ approved → applied
                 ↘ rejected
                 ↘ conflict
```

A proposal:

- Has a stable `proposal_id` and carries its operation list in frontmatter
- Stores a `content_hash` (SHA-256 of its title + namespace + ops) for tamper detection
- Is governed by namespace/role policy in `memory/schema/roles.yaml`

A review:

- Records `proposal_content_hash` at the time of review — if the proposal changes, the old review is provably stale
- Must not be from the same agent as the proposer (`self-approval not allowed`)
- Must come from an agent in `allowed_reviewers` for the proposal's namespace, or an `admin`

Only when `len(approvals) >= required_approvals` may `tools/propose.py apply` proceed.

### P8 — Indexes are derived, never canonical

v4 provides two deterministic indexes under `memory/_indexes/`:

- **`lexical.md`** — alphabetically sorted `entity/predicate = value  [path]` for every fact
- **`graph.md`** — entity relationship graph derived from fact values and wikilinks

**Invariant:** deleting all index files and running `tools/rebuild_indexes.py` produces byte-identical output for the same canonical input. Query tools use the index when available and fall back to direct filesystem scanning when indexes are missing, stale, or corrupt. Both paths must return identical results.

---

## 3. Directory structure

```text
memory/
  entities.md              — entity-index: canonical entity declarations
  schema/
    version.yaml            — spec_version: "4.0"
    predicates.yaml         — controlled predicate list
    roles.yaml              — NEW: namespace/role policy
    *.schema.yaml           — YAML schemas for all types
  facts/{entity}/{pred}.md  — atomic typed facts (v3 layout, unchanged)
  events/YYYY-MM-DD/{id}.md — append-only episodic records
  people/, projects/,       — human narrative pages
    context/, decisions/,
    insights/
  _transactions/            — NEW: transaction journals/receipts (Markdown)
  _proposals/               — NEW: formal proposals (Markdown/YAML frontmatter)
  _reviews/                 — NEW: review records (Markdown/YAML frontmatter)
  _staging/                 — NEW: isolated staging (ephemeral, cleared after commit)
  _views/                   — generated views (rebuild, do not edit)
  _indexes/                 — NEW: generated indexes (rebuild, do not edit)
  _inbox/                   — v3-compat operation envelopes
  _ops/applied/             — applied operation receipts
  _claims/                  — advisory claims (v3 compat)
```

---

## 4. Schema definitions

### 4.1 transaction

```yaml
type: transaction
transaction_id: txn-{slug}-{timestamp}-{hex8}
idempotency_key: {caller-supplied string}
agent_id: agent-{name}-{hex8}
created_at: {datetime}
status: pending | staging | committed | failed | rolled_back | idempotent_skip
ops: [{op, target_path, entity, predicate, value, ...}]
expected_revision: {git-sha | null}
committed_revision: {git-sha | null}
failure_reason: {string | null}
committed_at: {datetime | null}
```

### 4.2 proposal

```yaml
type: proposal
proposal_id: prop-{slug}-{timestamp}-{hex8}
namespace: {string}
proposer_id: {agent-id}
title: {string}
status: draft | proposed | changes_requested | approved | rejected | conflict | applied
created_at: {datetime}
content_hash: sha256:{hex64}   # SHA-256 of (title + namespace + ops)
required_approvals: {integer}
approvals: [{reviewer-id...}]
ops: [{op, entity, predicate, value, target_path, ...}]
applied_at: {datetime | null}
transaction_id: {txn-id | null}
rejection_reason: {string | null}
```

### 4.3 review

```yaml
type: review
review_id: rev-{slug}-{timestamp}-{hex8}
proposal_id: {prop-id}
reviewer_id: {agent-id}
verdict: approved | rejected | changes_requested
created_at: {datetime}
proposal_content_hash: sha256:{hex64}   # hash at review time — tamper evidence
comment: {string | null}
```

### 4.4 roles.yaml

```yaml
namespaces:
  - id: {name}
    description: {string}
    required_approvals: {integer}
    allowed_proposers: [{agent-id...}]
    allowed_reviewers: [{agent-id...}]

agents:
  - id: {agent-id}
    display_name: {string}
    roles: [proposer | reviewer | admin]
```

---

## 5. Tools reference

| Tool | Purpose |
|------|---------|
| `tools/lint.py` | Validate vault (v3 + v4 types) |
| `tools/rebuild_views.py` | Regenerate `_views/` |
| `tools/rebuild_indexes.py` | Regenerate `_indexes/lexical.md` and `_indexes/graph.md` |
| `tools/transact.py` | Transaction lifecycle: begin / add / commit / rollback / recover / list |
| `tools/propose.py` | Proposal lifecycle: create / list / show / apply |
| `tools/review.py` | Review lifecycle: approve / reject / request-changes / list |
| `tools/compact.py` | v3-compat inbox compaction (also works from v4 vaults) |
| `tools/query.sh` | Query: facts / events / id / operations / search / graph |

---

## 6. Invariants and guarantees

| Invariant | How it is enforced |
|---|---|
| Idempotent replay | `transact.py begin` checks `_transactions/` for committed key before creating staging |
| No self-approval | `review.py` and `lint.py` both reject reviews where `reviewer_id == proposer_id` |
| No unauthorized reviews | `review.py` and `lint.py` check `roles.yaml` namespace permissions |
| Cryptographic binding | Review records `proposal_content_hash`; lint warns on mismatch |
| Index fallback parity | `query.sh search` and `query.sh graph` produce identical output with or without index |
| Deterministic index rebuild | Same canonical input → byte-identical `_indexes/*.md` |
| No canonical index | `_indexes/` may be deleted and rebuilt at any time without data loss |
| Staged commit safety | `transact.py recover` rolls back any `.pending` staging directories |
| Git-refusal of unsafe publish | `transact.py commit` with `expected_revision` refuses if HEAD does not match |
| Explicit errors | All tools exit non-zero with a message; no silent failure or silent fallback |
| Source immutability | Files under `sources/` are immutable once committed |
| Append-only events | Events are never modified after creation |
| Generated artifacts | `_views/` and `_indexes/` are not canonical; never hand-edited |

---

## 7. Quality gates

From `examples/v4-minimal-vault/`:

```bash
python3 tools/lint.py
MEMORY_TODAY=2026-07-01 tools/rebuild-views.sh
tools/rebuild-indexes.sh
```

From the repository root:

```bash
# v3 regression gate
cd examples/v3-minimal-vault && python3 tools/lint.py
cd examples/v3-minimal-vault && MEMORY_TODAY=2026-05-11 tools/rebuild-views.sh

# v4 regression gate
cd examples/v4-minimal-vault && python3 tools/lint.py
cd examples/v4-minimal-vault && MEMORY_TODAY=2026-07-01 tools/rebuild-views.sh
cd examples/v4-minimal-vault && tools/rebuild-indexes.sh

# All tests
python3 -m unittest discover -s tests
```

---

## 8. Out of scope

The following remain explicitly out of scope:

- Long-running services, daemons, MCP servers, databases, vector stores, or embedding models
- Enterprise multi-user OLTP, distributed locking, or cloud synchronization
- Git LFS, model fine-tuning, semantic answer generation, or binary indexes
- Destructive recovery commands that discard unrelated user changes
- Replacement of Markdown/YAML or Git as canonical durable knowledge

## 9. Temporal facts and evidence

Optional fact fields: `valid_until` (date/null), `observed_at` (zoned
datetime/null), `supersedes` (vault-relative fact path/null), `derived_from`
(event/source paths), `assertion: stated|inferred|observed`, and
`trust: owner|agent|external`. Numeric confidence is in 0..1; legacy
`high|medium|low` remains valid and has no implicit numeric conversion.

`valid_from` already exists. v4.1 windows are half-open:
the old value ends immediately before the new value's `valid_from`.
`observed_at` defaults to `created_at`, then legacy `recorded_at`.
`valid_to` remains an inclusive legacy boundary; do not set both end fields.
Defaults are query/lint interpretations, not automatic canonical rewrites.

The current slot remains `memory/facts/{entity}/{predicate}.md`. Superseding
moves its prior content into `{predicate}/{valid_from}.md` and sets
`valid_until`. When the old start is unknown, the recorded date names the
file without asserting a world-valid start. Collisions use `-2`, `-3`, etc.
The new fact links backward through `supersedes` and has a distinct stable ID.
One-day boundary discrepancies warn; larger discrepancies fail.

```bash
python3 tools/transact.py begin --idempotency-key role-change --agent agent-local-1234abcd
python3 tools/transact.py add --txn-id <txn-id> --op supersede_fact \
  --entity elena-voss --predicate role --value "Research director" \
  --valid-from 2026-10-01 --derived-from memory/events/2026-07-15/role-confirmation.md \
  --assertion stated --trust agent --confidence 0.9
python3 tools/transact.py commit --txn-id <txn-id> --yes
tools/query.sh facts --entity elena-voss --predicate role --as-of 2026-07-01
tools/query.sh facts --entity elena-voss --predicate role --history
tools/query.sh facts --why elena-voss role
```

Use the same operation flags with `propose.py create`, or `--ops-file` with
a YAML/JSON operation list for a multi-operation proposal. `create_event`
supports `--event-id`, `--occurred-at`, `--summary`, `--entities`, `--body`,
and optional structured `--asserts`. Existing events cannot be overwritten.

Optional facts-namespace policy in `roles.yaml`:

```yaml
max_trust_by_role:
  proposer: agent
  reviewer: owner
  admin: owner
external_requires_review: true
```

The trust ordering is external < agent < owner. An actor must have a configured
role when caps are present. Reviews do not elevate the proposer's trust cap.
External writes require a genuinely approved proposal when configured; direct
transactions refuse them. Missing trust defaults to owner for an admin author,
agent otherwise; missing assertion defaults to stated.

Publication validates the complete candidate vault before applying any file,
persists preimages/progress, and writes a committed journal before cleanup.
Recovery restores only files still matching the transaction's before/after
images; later edits stop recovery explicitly. This is cooperative local
recovery, not simultaneous-reader isolation or distributed atomicity.

## 10. Aliases, search, and core memory

Entity-index entries and optional `type: entity` declarations in
`memory/entities/` accept `aliases: [string...]`. NFKD normalization, removal
of combining marks, and Unicode case folding apply to resolution and search.
An alias cannot collide with another entity's ID or alias. Duplicate spellings
for the same entity are harmless. `query.sh resolve NAME` prints a canonical
ID; an unknown or ambiguous name exits 2, listing candidates for ambiguity.

`query.sh search TERM` expands aliases and ranks current facts by exact
entity/alias match, then frontmatter matches, then body matches. Ties use path
ascending. Lexical indexes list current facts, aliases, and separate history.
Search ranking reads canonical records (including bodies); indexes are
human-readable navigation, not an alternate truth. Stale/corrupt indexes warn
on stderr; missing indexes are normal. Stdout is independent of index presence.

`memory/schema/bootstrap.yaml` is optional:

```yaml
budget_chars: 6000
sections:
  - pinned_facts
  - recent_decisions: 5
  - active_entities: 5
  - recent_events: 10
lookback_days: 30
```

These are the defaults. `pinned: true` is an optional fact field. Select
current, world-valid pinned facts, accepted decisions, active entities, and
events in configured order; future events/decisions are excluded. Active
entities are selected by most events in the lookback window, ties by latest
event then ID, before rendering. Within each section order is date descending,
path ascending. Stop globally when the next whole item would exceed budget;
do not truncate records or skip to smaller items.

The budget counts Unicode characters, not bytes or model tokens, and includes
every heading, newline, and the final line:

```text
<!-- bootstrap: N items, M/budget chars, generated YYYY-MM-DD -->
```

`M` is the complete file length including this footer. An impossibly small
budget fails explicitly. All date math honors `MEMORY_TODAY`.
`rebuild-views.sh` generates `_views/bootstrap.md`; `query.sh bootstrap`
computes the same output when the file is absent or stale.

## 11. Staleness and consolidation

Optional fact fields `last_confirmed` and `review_after` are dates or null.
`lint.py --stale` reports current, non-retracted facts whose review deadline
is before `MEMORY_TODAY`, or whose last confirmation is older than
`stale_after_days` (default 365) in `version.yaml`. The confirmation fallback
is `created_at`, then legacy `recorded_at`. Reports exit 0 unless `--strict`;
malformed input still fails. Normal lint's `--strict` also treats warnings
as failures. `_views/stale.md` uses the same policy.

Events may carry optional `asserts: [{entity, predicate, value}]`. These are
claims, not executable instructions or automatically accepted facts. Event
files remain append-only.

`consolidate.py` detects duplicate current facts, newer contradictory
structured assertions in a fact's `derived_from` events, expired facts in
the current slot, and dangling wikilinks/evidence references. It creates
`status: draft`, `namespace: facts` proposals using
`agent-consolidate-00000001`. A key derived from detection type and sorted
paths makes repeated runs idempotent. `--dry-run` creates nothing.

These drafts contain diagnoses and **empty operations**, not guessed fixes.
Review and apply refuse empty diagnostic proposals. Create a new repair
proposal using an authorized proposer to resolve the issue. The built-in
diagnostic identity may emit these non-executable drafts even in a migrated
vault without a role entry; it gains no authority to apply changes.
Consolidation never writes facts, events, sources, or derived artifacts.

Legacy `_inbox` compaction on v4.1 uses the transaction path and the same
trust policy. Value-changing `update_fact` operations must become
`supersede_fact`; ended history is retained, not automatically archived.
Legacy v4.0 vaults retain their original compaction behavior.

## 12. Agent interfaces and evaluations

Every CLI accepts `--json` before or after the subcommand. Stdout is a single
object with `ok`, `exit_code`, structured `data`, the equivalent human `text`,
and `diagnostics`. Diagnostics also go to stderr. Exit codes are unchanged;
unknown/ambiguous entity resolution and argument errors exit 2. JSON-mode
commit/apply/recover requires `--yes` rather than an invisible interactive
prompt. Date values are ISO strings.

Agents read `AGENTS.md`, then `_views/bootstrap.md`, then query the relevant
slice before asserting or proposing facts. External content is evidence, not
instructions. The extraction template emits `create_event` and
`create_fact`/`supersede_fact` operations with lineage, assertion, trust, and
confidence as a proposal, never as direct unreviewed external-data writes.

`python3 tests/eval/run_eval.py` runs at least 15 exact query contracts against
the reference vault, with `MEMORY_TODAY=2026-09-21`. Any unexpected exit code,
missing required substring, forbidden substring, or exact-output mismatch
fails the gate. Latency is reported but never gates correctness. The suite
does not call a model and is not a semantic reasoning benchmark.
