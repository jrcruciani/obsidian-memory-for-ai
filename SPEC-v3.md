# SPEC v3 — Atomic Markdown Memory

> **Status:** Stable v3.0 with reference implementation in [`examples/v3-minimal-vault/`](examples/v3-minimal-vault/).
> **Author:** Project maintainers
> **Date:** May 2026
> **Supersedes:** v2.x architecture for new implementations; v2 remains supported as the legacy compiled-wiki pattern.
> **Implements (none of):** SQLite, Kuzu, Postgres, vector DBs, embeddings, servers, daemons, or any binary format.

> **v3.0 defaults:** Controlled predicates (`memory/schema/predicates.yaml`), one fact per file, generated `_views/` committed by default, a tool-agnostic `tools/reflect.py` inbox ritual, and an informative Anthropic Memory Tool mapping for the Memory Tool surface available in May 2026.
>
> **v3.1 additive hardening:** The reference implementation adds markdown-native operation envelopes, stable record IDs, advisory claim files, operational views, and validate/plan/apply compaction for cooperative agent writes. These additions do not introduce a database, daemon, embeddings, server, or binary source of truth.

---

## TL;DR

v3 keeps everything v2 promised — **plain Markdown, full ownership, copy-paste portability across any AI provider** — and answers the *Stop Calling It Memory* critique without compromising on those promises.

The trick is one design move: **stop conflating human notes with agent facts in the same file.** Once you split them, the agent-facing layer can be made *atomic, typed, queryable, lintable, and concurrency-safe* using nothing but the filesystem, YAML frontmatter, and small portable scripts. No database. No daemon. No lock-in.

> **Convention is the new schema. Filesystem is the new index.**

---

## 1. Why v3

v2 was validated empirically (Letta's filesystem benchmark, 74% LoCoMo) and adopted in spirit by every major coding agent (CLAUDE.md, AGENTS.md, COPILOT.md, Cursor rules, Cline rules, Anthropic Memory Tool, Obsidian Agent Skills). The pattern works.

The honest 2026 critiques against v2 are five (see [README §Honest limits](README.md#honest-limits)):

1. **No real querying.**
2. **No relationships.**
3. **Scale ceiling at 500–5,000 notes.**
4. **No schema enforcement.**
5. **No concurrent multi-agent writes.**

The dominant industry response was: *"add a database."* Mem0 added vectors. Zep added a graph. Letta added a tiered runtime. Jonathan added SQLite + Kuzu. Each fix surrendered something this repo's audience explicitly chose Markdown to keep: ownership, transparency, vendor-neutrality, `git diff` as the audit log, the ability to `tar` your memory and move it.

v3's bet is that all five critiques can be answered **inside Markdown**, by treating the filesystem the way relational systems treat tables: with conventions, schemas, indexes (as paths), constraints (as linters), and views (as generated files). What you give up is the database engine. What you keep is everything that made v2 worth using.

---

## 2. Design principles

### P1 — Separate the audiences

A memory file serves either a human reader or an agent reader, not both. v2 routinely mixed them (`people/elena-voss.md` was prose for the human *and* the agent's structured source of truth). v3 separates them:

- **Human-facing files** (`people/`, `projects/`, `decisions/` narratives): prose, free-form, optimized for *you* reading them in Obsidian.
- **Agent-facing files** (`facts/`, `events/`): atomic, typed, optimized for `grep`, `yq`, and lint.
- **Generated files** (`_views/`): rollups the agent reads at session start. Not a source of truth — derivable from `facts/` + `events/`.

### P2 — Atomicity: one fact, one file

The single most important change. v2 stored "everything about Elena" in `people/elena-voss.md`. v3 stores it as:

```
memory/facts/elena-voss/role.md
memory/facts/elena-voss/base.md
memory/facts/elena-voss/employer.md
memory/facts/elena-voss/primary-project.md
```

Each file is one tuple: `(entity, predicate, value, time, provenance)`. This turns `ripgrep` into a real query language: every match is exactly one row.

Per-entity files with multiple facts are a valid local experiment, but they are not v3.0-compatible. The stable v3.0 contract uses one file per fact because path-level identity, git diffs, linter errors, compaction, and conflict resolution all become unambiguous.

### P3 — Path is the primary key

`memory/facts/{entity}/{predicate}.md` is canonical. The filesystem is the index. No separate index file to drift out of sync. To list everything known about Elena: `ls memory/facts/elena-voss/`. To check whether her base is recorded: `test -f memory/facts/elena-voss/base.md`.

### P4 — Frontmatter is the schema

Every typed file declares its type and obeys a schema:

```yaml
---
type: fact
entity: elena-voss
predicate: base
value: "Berlin, Germany"
valid_from: 2025-09-01
valid_to: null
recorded_at: 2026-05-10T22:14:00Z
confidence: high
sources: ["sources/conv-2025-09-12.md"]
last_reviewed: 2026-05-10
---
```

Schemas live in `memory/schema/*.schema.yaml`. The linter (`tools/lint.py`) validates every file against the schema declared in its `type:` field. Schema violations fail the lint.

Every v3.0 vault also carries `memory/schema/version.yaml`:

```yaml
spec_version: "3.0"
schema_status: stable
frozen_at: 2026-05-11
```

The version marker is the compatibility contract. A v3.0 linter must fail if the marker is missing, not `3.0`, or not marked `stable`.

### P5 — Bi-temporal by default

Every fact carries two time axes:

- `valid_from` / `valid_to` — when the fact is true *in the world*.
- `recorded_at` — when it was *written down*.

This is Zep's bi-temporal model in YAML. It makes "what did I believe in March about X" answerable without a graph DB.

### P6 — Append-only events

Episodic memory (`memory/events/`) is append-only, dated, never edited:

```
memory/events/2026-05-10/discussed-v3-spec-with-hermes.md
memory/events/2026-05-10/published-v21-readme.md
```

Append-only is what makes git history meaningful for memory and what eliminates write-write conflicts between agents (different agents write different files; no file is ever rewritten).

### P7 — Materialized views are generated, not authored

`memory/_views/` contains markdown files that are **derived** from `facts/` + `events/`. The agent reads from views; humans (and the linter) read from sources. A `tools/rebuild-views.sh` regenerates them. Delete `_views/`, regenerate, byte-identical output.

The v3.0 default is to commit `_views/` so `git diff` shows derived-state changes, including contradictions and stale-fact lists. Private vaults may `.gitignore` `_views/`, but then they must rebuild locally before relying on views. Lint validates source truth and does not require `_views/` to exist.

Standard views v3 ships:

- `_views/by-entity/{entity}.md` — all facts about an entity, ordered by predicate, valid first.
- `_views/timeline.md` — events in reverse chronological order.
- `_views/contradictions.md` — same `(entity, predicate)` valid simultaneously with different `value`. Surfaced for human resolution.
- `_views/stale.md` — facts whose `last_reviewed` is older than the policy threshold.
- `_views/graph.md` — adjacency rollup of `[[wikilinks]]` for cheap graph reads.

Determinism is part of the view contract: tools must produce UTF-8 Markdown with LF line endings, a trailing newline, stable locale-independent ordering, and date-dependent output controlled by `MEMORY_TODAY=YYYY-MM-DD` when set.

### P8 — Linter as constraint engine

`tools/lint.py` (zero deps beyond Python stdlib + PyYAML) enforces what a database would enforce:

- Frontmatter validates against `schema/{type}.schema.yaml`.
- `valid_from <= valid_to` (when both set).
- Every `entity` reference in a fact corresponds to a known entity (declared in `entities.md` or via convention).
- Every `[[wikilink]]` resolves to a real file (or is explicitly `unresolved:`).
- Every `sources:` path exists.
- No two files declare the same `(entity, predicate)` with overlapping validity windows and different values *without* one being marked `superseded_by:`.

Pre-commit hook in `tools/`. Runs in CI. Refuses to push if it fails. **The linter travels with the vault**, so portability is preserved: clone the vault elsewhere and the constraints come with it.

### P9 — Concurrency via inbox + compactor

Multi-agent writes go through `memory/_inbox/{agent-id}/`. Each agent owns its inbox folder. A `tools/compact.sh` ritual (manual or scheduled) reviews inbox entries and merges them into canon, preserving provenance. Because canon files are atomic (P2), conflicts collapse to "two agents wrote the same `(entity, predicate)`" — easy to surface and resolve.

This isn't WAL-grade concurrency. It's *cooperative* concurrency, sufficient for the realistic case (a few agents, human in the loop). For real OLTP-style multi-agent workloads, this is the wrong substrate — and that's correctly out of scope.

v3.1 makes that cooperation explicit rather than hand-wavy. Agents should prefer operation envelopes under `memory/_inbox/{agent-id}/ops/`:

```yaml
---
type: operation
operation_id: op-20260512t180000z-1a2b3c4d
op: create_fact
agent_id: agent-copilot-1a2b3c4d
created_at: 2026-05-12T18:00:00Z
target_id: fact-elena-voss-role
target_path: memory/facts/elena-voss/role.md
precondition_hash: null
status: proposed
reason: "Capture a durable role fact."
sources: ["sources/README.md"]
payload:
  type: fact
  id: fact-elena-voss-role
  entity: elena-voss
  predicate: role
  value: "Art conservator and pigment researcher"
  recorded_at: 2026-05-12T18:00:00Z
---
```

The compactor validates the envelope, checks preconditions, applies the filesystem change, rebuilds views, and records an applied receipt under `memory/_ops/applied/`. Conflicts stay visible in `_inbox/` and `_views/conflicts.md`.

Advisory claims live in `memory/_claims/{target-id}.yaml`. They are created with exclusive file creation, include `expires_at`, and are explicitly not transactional locks. On local filesystems they help cooperative agents avoid obvious collisions. On cloud-sync layers they are diagnostic signals, not correctness guarantees.

### P10 — Decay as ritual, not magic

`tools/compact.sh` also handles decay:

- Facts with `valid_to < today` → moved to `memory/_archive/{year}/`.
- Facts with `last_reviewed` older than policy (default: 180 days) → flagged in `_views/stale.md` for human review.
- Duplicate `(entity, predicate)` → surfaced in `_views/contradictions.md` for resolution.

No fact is ever silently deleted. The agent can read `_archive/` if explicitly asked. `git log` retains everything.

v3.1 can express decay policy in fact frontmatter:

```yaml
decay:
  review_after_days: 180
  archive_after_valid_to: true
  pin: false
```

Decay remains proposal-driven. Agents may emit `review_fact` or `archive_fact` operation envelopes; humans or trusted automation apply them through the same compactor flow.

---

## 3. Architecture

```
vault/
├── CLAUDE.md, COPILOT.md, AGENTS.md       ← procedural memory (Anthropic's & friends' convention)
├── TASKS.md
│
├── sources/                                ← Layer 1: immutable inputs (unchanged from v2)
│   ├── articles/
│   ├── notes/
│   └── assets/
│
├── memory/
│   │
│   ├── schema/                             ← portable type system
│   │   ├── fact.schema.yaml
│   │   ├── event.schema.yaml
│   │   ├── decision.schema.yaml
│   │   ├── insight.schema.yaml
│   │   └── entity.schema.yaml
│   │
│   ├── entities.md                         ← canonical list of known entities (people, projects, orgs)
│   │
│   ├── facts/                              ← Layer 2a: atomic semantic memory
│   │   └── {entity}/
│   │       └── {predicate}.md
│   │
│   ├── events/                             ← Layer 2b: append-only episodic memory
│   │   └── {YYYY-MM-DD}/
│   │       └── {slug}.md
│   │
│   ├── decisions/                          ← durable decisions w/ rationale (typed)
│   ├── insights/                           ← reflect-after-session output (typed)
│   │
│   ├── people/                             ← Layer 2c: human-facing prose pages
│   │   └── {entity}.md                     ← narrative; links to facts/{entity}/
│   ├── projects/                           ← human-facing prose pages
│   ├── context/                            ← stable structural prose (company, personality)
│   │
│   ├── glossary.md
│   ├── working-context.md
│   ├── triggers.md
│   ├── modes.md
│   │
│   ├── _inbox/                             ← agent-scoped write staging
│   │   └── {agent-id}/
│   │       └── ops/{operation-id}.md       ← v3.1 proposed write envelopes
│   ├── _claims/                            ← v3.1 advisory target claims
│   │   └── {target-id}.yaml
│   ├── _ops/                               ← v3.1 operation receipts
│   │   └── applied/{operation-id}.md
│   │
│   ├── _archive/                           ← time-bounded facts past valid_to
│   │   └── {year}/
│   │
│   └── _views/                             ← MATERIALIZED, regenerable
│       ├── by-entity/{entity}.md
│       ├── by-id.md
│       ├── by-predicate.md
│       ├── inbox.md
│       ├── claims.md
│       ├── operations.md
│       ├── conflicts.md
│       ├── timeline.md
│       ├── contradictions.md
│       ├── stale.md
│       └── graph.md
│
└── tools/                                  ← portable, stdlib-only
    ├── lint.py                             ← schema + constraint validator
    ├── rebuild-views.sh                    ← regenerate _views/
    ├── compact.sh                          ← inbox merge + decay + archive
    ├── ops.py                              ← v3.1 operation/claim helper
    ├── query.sh                            ← rg + yq ergonomic wrappers
    └── pre-commit                          ← runs lint.py, refuses on failure
```

---

## 4. Schemas (canonical and frozen for v3.0)

The schemas in `examples/v3-minimal-vault/memory/schema/` are the v3.0 reference schemas. Compatible vaults may add local predicates and optional fields, but changes that alter required fields, field meanings, path semantics, or date semantics are breaking changes and require a documented migration or a future major version.

### `fact.schema.yaml`

```yaml
type: object
required: [type, entity, predicate, value, recorded_at]
properties:
  type:        { const: fact }
  id:          { type: string, pattern: "^[a-z0-9][a-z0-9_-]*$" } # v3.1 stable id
  entity:      { type: string, pattern: "^[a-z0-9-]+$" }
  predicate:   { type: string, pattern: "^[a-z0-9-]+$" }
  value:       { }                          # any YAML scalar or block
  valid_from:  { type: [string, "null"], format: date }
  valid_to:    { type: [string, "null"], format: date }
  recorded_at: { type: string, format: date-time }
  confidence:  { enum: [high, medium, low] }
  sources:     { type: array, items: { type: string } }
  last_reviewed: { type: string, format: date }
  superseded_by: { type: [string, "null"] }   # path to the fact that replaced this one
  tags:        { type: array, items: { type: string } }
  decay:       { type: object }               # v3.1 review/archive policy
```

### `event.schema.yaml`

```yaml
type: object
required: [type, occurred_at, summary]
properties:
  type:        { const: event }
  id:          { type: string, pattern: "^[a-z0-9][a-z0-9_-]*$" } # v3.1 stable id
  occurred_at: { type: string, format: date-time }
  summary:     { type: string }
  entities:    { type: array, items: { type: string } }   # entity ids touched
  kind:        { enum: [conversation, decision, ingest, action, observation] }
  sources:     { type: array, items: { type: string } }
  derived_facts: { type: array, items: { type: string } } # paths to facts/ written from this event
```

### `entity.schema.yaml`

```yaml
type: object
required: [type, id, kind]
properties:
  type:    { const: entity }
  id:      { type: string, pattern: "^[a-z0-9-]+$" }
  kind:    { enum: [person, project, org, place, concept, tool] }
  display: { type: string }
  aliases: { type: array, items: { type: string } }
```

(Decision and insight schemas follow the same shape; omitted for brevity — see `memory/schema/` in the reference vault.)

`memory/schema/predicates.yaml` is controlled per vault. The example predicates are illustrative, not a global registry; a private vault may add local predicates there without changing the v3.0 contract.

### `operation.schema.yaml` (v3.1 additive)

Operation envelopes are agent proposals, not canonical memory records. They let agents describe intended mutations before a human or trusted compactor applies them:

```yaml
type: object
required: [type, operation_id, op, agent_id, created_at, status, reason]
properties:
  type: { const: operation }
  operation_id: { type: string, pattern: "^op-[a-z0-9][a-z0-9_-]*$" }
  op: { enum: [create_fact, update_fact, add_event, archive_fact, review_fact, rename_entity, add_entity, add_predicate] }
  agent_id: { type: string, pattern: "^agent-[a-z0-9-]+-[a-f0-9]{8}$" }
  created_at: { type: string, format: date-time }
  target_id: { type: [string, "null"] }
  target_path: { type: [string, "null"] }
  precondition_hash: { type: [string, "null"] }
  status: { enum: [proposed, validated, applied, rejected, conflict, superseded] }
  reason: { type: string }
  payload: { type: object }
```

`precondition_hash` is an optimistic-concurrency guard over the target file contents. It detects stale writes; it does not make the filesystem transactional.

### `claim.schema.yaml` (v3.1 additive)

Claims are advisory files under `memory/_claims/{target-id}.yaml`. They use exclusive file creation and TTLs to help cooperative agents avoid obvious collisions. They are intentionally weaker than locks and must be treated as diagnostic on cloud-synced filesystems.

---

## 5. Worked example — v2 → v3 side by side

### v2 (today)

`memory/people/elena-voss.md`:

```markdown
---
type: person
relevance: high
last_reviewed: 2026-04-12
---
# Elena Voss

Elena is an art conservator and pigment researcher based in Berlin, Germany.
She works with historical pigment recipes and spectroscopic signatures.
Her primary research project is Concordance.
```

Pros: human-readable, one file. Cons: every fact is unstructured prose; "what was Elena's role in March 2025" is unanswerable; updating a project or employer requires a manual rewrite that loses the prior state.

### v3 (proposed)

`memory/people/elena-voss.md` *(unchanged in spirit — narrative, for the human)*:

```markdown
# Elena Voss

Elena is an art conservator and pigment researcher based in Berlin, Germany.
Her primary research project is Concordance, mapping historical pigment recipes
to modern spectroscopic signatures.

For machine-readable facts see [[../facts/elena-voss/]].
```

`memory/facts/elena-voss/employer.md`:

```yaml
---
type: fact
entity: elena-voss
predicate: employer
value: "Gemäldegalerie"
valid_from: 2024-01-01
valid_to: null
recorded_at: 2026-05-10T22:30:00Z
confidence: high
sources: ["sources/conv-onboarding.md"]
last_reviewed: 2026-05-10
---
```

`memory/facts/elena-voss/role.md`:

```yaml
---
type: fact
entity: elena-voss
predicate: role
value: "Art conservator"
valid_from: 2024-01-01
valid_to: 2025-12-31
recorded_at: 2026-05-10T22:30:00Z
superseded_by: "memory/facts/elena-voss/role-2026.md"
sources: ["sources/conv-onboarding.md"]
last_reviewed: 2026-05-10
---
```

`memory/facts/elena-voss/role-2026.md`:

```yaml
---
type: fact
entity: elena-voss
predicate: role
value: "Art conservator and pigment researcher"
valid_from: 2026-01-01
valid_to: null
recorded_at: 2026-05-10T22:30:00Z
confidence: medium
sources: ["sources/conv-role-update.md"]
last_reviewed: 2026-05-10
---
```

Now "what was Elena's role in March 2025" is one query:

```bash
tools/query.sh facts --entity elena-voss --predicate role --on 2025-03-15
# → "Art conservator" (from memory/facts/elena-voss/role.md)
```

And "is anything contradictory about Elena right now":

```bash
cat memory/_views/contradictions.md
```

The narrative `people/elena-voss.md` stays for *you*. The atomic facts answer the agent's questions. Both live in plain Markdown. Both can be `tar`'d and moved.

---

## 6. Tools (portable, stdlib-only)

All `tools/*` scripts are written to run with **Python 3.11+ stdlib + PyYAML** or **pure bash + ripgrep + yq**. No pip install of anything else. No background services. No state outside the vault.

- **`lint.py`** — validates frontmatter against `schema/`, checks constraints (P8). Exit 0 = clean.
- **`rebuild-views.sh`** — regenerates everything under `_views/`. Idempotent. Safe to run on every commit.
- **`ops.py`** — creates v3.1 operation envelopes and advisory claims without mutating canon.
- **`compact.sh`** — interactive: validates and applies operation envelopes, preserves applied receipts, archives expired facts, surfaces conflicts.
- **`query.sh`** — wrappers: `query.sh facts --entity X --predicate Y --on YYYY-MM-DD`, `query.sh id ID`, `query.sh operations --status conflict`, etc.
- **`pre-commit`** — runs `lint.py` + `rebuild-views.sh`. Refuses commit on lint failure.

These ship with the vault. Cloning the vault clones the constraint engine.

---

## 7. Migration from v2

v2 → v3 is **additive, not destructive**. Existing v2 vaults keep working through every step.

**Phase 0 — preparation (no behavior change).**
Add `memory/schema/`, `memory/_views/`, `memory/_inbox/`, `memory/_archive/`, `tools/`, `memory/entities.md`, and `memory/schema/predicates.yaml`. Include `memory/schema/version.yaml` with `spec_version: "3.0"`. Run `lint.py` only after this bootstrap set exists; it will pass trivially if no v3-typed files exist yet.

**Phase 1 — start writing new facts atomically.**
From the cutover date, any *new* fact the agent extracts goes to `memory/facts/{entity}/{predicate}.md` instead of being appended to a prose page. Old prose pages remain canonical for everything pre-cutover. The agent reads both during a transition window.

**Phase 2 — append-only events.**
New session logs go to `memory/events/{YYYY-MM-DD}/`. The old `memory/log.md` is frozen and kept as historical record.

**Phase 3 — backfill on demand.**
When you query an entity and the agent realises the prose page has a fact that should be atomic, it extracts it (writing to `facts/`) and leaves a note in the prose page. No big-bang migration. The vault converges as it's used.

**Phase 4 — `_views/` becomes the agent's preferred read.**
Once `facts/` has critical mass for an entity, the agent reads `_views/by-entity/{entity}.md` instead of the prose page for factual queries. The prose page becomes purely human-facing.

At no point is the vault in a broken state. At no point is something destroyed. v2 vaults that never migrate continue to work — v3 is opt-in, file by file.

v3.0 does not ship automatic migration tooling. Migration is a docs-first, manual-review workflow because rewriting prose into facts is semantic work. Agents may assist by drafting candidate facts, but the stable path is checklist-driven and destructive rewrites are out of scope.

---

## 8. What v3 is *not*

This must be said plainly to avoid the "v2 was sold as memory and wasn't" trap that *Stop Calling It Memory* correctly punctured.

- v3 is **not** a database. It does not give you SQL, JOINs, or transactional guarantees.
- v3 is **not** a graph engine. `[[wikilinks]]` + `_views/graph.md` is an adjacency rollup, not Cypher.
- v3 is **not** a multi-tenant memory backend. One human, one vault, a small number of cooperative agents.
- v3.1 claims are **not** distributed locks. They are advisory files for cooperative local agents and diagnostic signals when sync layers disagree.
- v3 does **not** scale to millions of records. The design point is the same as v2: **50–500 personal-context files, plus an open-ended events log** that compaction keeps tractable.
- v3 does **not** automatically forget. Decay is a ritual you run, not a background daemon.

Within those bounds, v3 closes the gaps v2 left open without surrendering what made v2 worth choosing in the first place.

---

## 9. Stable v3.0 decisions

The RFC questions are closed for v3.0:

1. **Predicate namespace:** controlled per-vault vocabulary in `memory/schema/predicates.yaml`.
2. **Reflect ritual ownership:** v3 ships `tools/reflect.py` as a conservative, tool-agnostic inbox writer. Host-specific rituals are optional integrations.
3. **`_views/` versioning:** commit generated views by default for auditability; private vaults may ignore them and regenerate locally.
4. **Anthropic Memory Tool mapping:** document an informative mapping from `memory/` to `/memories` for the Memory Tool surface available in May 2026. Future provider changes do not redefine the v3.0 contract.
5. **Fact granularity:** one fact per file is normative for v3.0.

Optional alternatives may be documented as experiments, but they are not the stable v3.0 path.

---

## 10. Compatibility requirements

Core requirements:

- Python 3.11+.
- PyYAML.
- POSIX shell for `*.sh` wrappers.
- Git if you want `_views/` diffs and pre-commit checks.
- No server, daemon, database, embeddings, or network dependency.

Stable CLI surface:

- `python3 tools/lint.py [--root PATH]`: exit `0` when clean, non-zero on errors.
- `tools/rebuild-views.sh`: regenerate all `_views/` from source memory.
- `tools/ops.py create-fact --agent AGENT --entity ID --predicate PREDICATE --value VALUE --reason TEXT`.
- `tools/ops.py add-event --agent AGENT --summary TEXT`.
- `tools/ops.py claim --agent AGENT --target-id ID --operation-id OP_ID`.
- `tools/query.sh id ID`.
- `tools/query.sh facts [--entity ID] [--predicate PREDICATE] [--on YYYY-MM-DD]`.
- `tools/query.sh events --since YYYY-MM-DD`.
- `tools/query.sh operations [--status STATUS]`, `tools/query.sh inbox [--agent AGENT]`, and `tools/query.sh claims`.
- `tools/query.sh stale` and `tools/query.sh contradictions`.
- `tools/reflect.py --agent ID --summary TEXT [--dry-run]`: write a proposed event operation to `_inbox`.
- `tools/compact.sh [--yes]`: review/apply operation envelopes, move legacy inbox entries, and archive expired facts.

Optional, non-normative integrations include Obsidian CLI, host-agent plugins, scheduled automation, provider-specific memory tools, and any managed memory service. They can improve UX but are not required for v3.0 compatibility.

---

## 11. Manifesto (one paragraph)

A notebook is not a filing cabinet. A filing cabinet is not a database. *Stop Calling It Memory* is right about that — and it was right to reject the cargo-cult version of "AI + Markdown = brain". v3 doesn't argue with the diagnosis. It argues that the response — *"so use SQLite"* — gives up the wrong things. Personal memory you can read with your eyes, edit with your hands, version with `git`, copy-paste to any future provider, and never owe to a vendor's retrieval API is worth keeping. The way to keep it is to take Markdown seriously: atoms, types, schemas, constraints, views, all in plain text, all enforced by tools that travel inside the vault. **Convention is the new schema. Filesystem is the new index.** The rest is rigor.
