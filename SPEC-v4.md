# SPEC v4 — Transactional Atomic Markdown Memory

> **Status:** Stable v4.0 — current protocol.
> **Author:** Project maintainers
> **Date:** July 2026
> **Supersedes:** v3.1 for new implementations; v3 remains supported as the previous stable generation.
> **Reference implementation:** [`examples/v4-minimal-vault/`](examples/v4-minimal-vault/)
> **Implements (none of):** SQLite, databases, vector stores, embeddings, servers, daemons, or any binary format.

---

## TL;DR

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
