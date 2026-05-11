# SPEC v3 — Atomic Markdown Memory

> **Status:** Draft / RFC with reference implementation in [`examples/v3-minimal-vault/`](examples/v3-minimal-vault/).
> **Author:** JR Cruciani
> **Date:** May 2026
> **Supersedes (when accepted):** v2.x architecture
> **Implements (none of):** SQLite, Kuzu, Postgres, vector DBs, embeddings, servers, daemons, or any binary format.

> **Implementation note:** The reference implementation chooses controlled predicates (`memory/schema/predicates.yaml`), commits generated `_views/` in the example vault, includes `tools/reflect.py` as a conservative inbox writer, and documents Anthropic Memory Tool mapping. These choices answer several RFC questions for the example without making them mandatory for every private vault.

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

A memory file serves either a human reader or an agent reader, not both. v2 routinely mixed them (`people/jr.md` was prose for the human *and* the agent's structured source of truth). v3 separates them:

- **Human-facing files** (`people/`, `projects/`, `decisions/` narratives): prose, free-form, optimized for *you* reading them in Obsidian.
- **Agent-facing files** (`facts/`, `events/`): atomic, typed, optimized for `grep`, `yq`, and lint.
- **Generated files** (`_views/`): rollups the agent reads at session start. Not a source of truth — derivable from `facts/` + `events/`.

### P2 — Atomicity: one fact, one file

The single most important change. v2 stored "everything about JR" in `people/jr.md`. v3 stores it as:

```
memory/facts/jr/role.md
memory/facts/jr/timezone.md
memory/facts/jr/employer.md
memory/facts/jr/email-personal.md
```

Each file is one tuple: `(entity, predicate, value, time, provenance)`. This turns `ripgrep` into a real query language: every match is exactly one row.

### P3 — Path is the primary key

`memory/facts/{entity}/{predicate}.md` is canonical. The filesystem is the index. No separate index file to drift out of sync. To list everything known about JR: `ls memory/facts/jr/`. To check whether his timezone is recorded: `test -f memory/facts/jr/timezone.md`.

### P4 — Frontmatter is the schema

Every typed file declares its type and obeys a schema:

```yaml
---
type: fact
entity: jr
predicate: timezone
value: "Europe/Madrid"
valid_from: 2025-09-01
valid_to: null
recorded_at: 2026-05-10T22:14:00Z
confidence: high
sources: ["sources/conv-2025-09-12.md"]
last_reviewed: 2026-05-10
---
```

Schemas live in `memory/schema/*.schema.yaml`. The linter (`tools/lint.py`) validates every file against the schema declared in its `type:` field. Schema violations fail the lint.

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

`memory/_views/` contains markdown files that are **derived** from `facts/` + `events/`. The agent reads from views; humans (and the linter) read from sources. A `tools/rebuild-views.sh` regenerates them. Delete `_views/`, regenerate, byte-identical output. They can be `.gitignore`'d or committed for audit; both work.

Standard views v3 ships:

- `_views/by-entity/{entity}.md` — all facts about an entity, ordered by predicate, valid first.
- `_views/timeline.md` — events in reverse chronological order.
- `_views/contradictions.md` — same `(entity, predicate)` valid simultaneously with different `value`. Surfaced for human resolution.
- `_views/stale.md` — facts whose `last_reviewed` is older than the policy threshold.
- `_views/graph.md` — adjacency rollup of `[[wikilinks]]` for cheap graph reads.

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

### P10 — Decay as ritual, not magic

`tools/compact.sh` also handles decay:

- Facts with `valid_to < today` → moved to `memory/_archive/{year}/`.
- Facts with `last_reviewed` older than policy (default: 180 days) → flagged in `_views/stale.md` for human review.
- Duplicate `(entity, predicate)` → surfaced in `_views/contradictions.md` for resolution.

No fact is ever silently deleted. The agent can read `_archive/` if explicitly asked. `git log` retains everything.

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
│   │
│   ├── _archive/                           ← time-bounded facts past valid_to
│   │   └── {year}/
│   │
│   └── _views/                             ← MATERIALIZED, regenerable
│       ├── by-entity/{entity}.md
│       ├── timeline.md
│       ├── contradictions.md
│       ├── stale.md
│       └── graph.md
│
└── tools/                                  ← portable, stdlib-only
    ├── lint.py                             ← schema + constraint validator
    ├── rebuild-views.sh                    ← regenerate _views/
    ├── compact.sh                          ← inbox merge + decay + archive
    ├── query.sh                            ← rg + yq ergonomic wrappers
    └── pre-commit                          ← runs lint.py, refuses on failure
```

---

## 4. Schemas (canonical)

### `fact.schema.yaml`

```yaml
type: object
required: [type, entity, predicate, value, recorded_at]
properties:
  type:        { const: fact }
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
```

### `event.schema.yaml`

```yaml
type: object
required: [type, occurred_at, summary]
properties:
  type:        { const: event }
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

---

## 5. Worked example — v2 → v3 side by side

### v2 (today)

`memory/people/jr.md`:

```markdown
---
type: person
relevance: high
last_reviewed: 2026-04-12
---
# JR Cruciani

JR is an FTE at Microsoft, transitioning to CSA (Cloud Solution Architect)
from late 2025. Lives in Madrid (Europe/Madrid). Personal email
jlrevilla@tutamail.com. Has a cat named Mondo. Pareja: Valeria.
Hijos: Ignacio (19) y Gabriel (15).
```

Pros: human-readable, one file. Cons: every fact is unstructured prose; "what was JR's role in March 2025" is unanswerable; updating "transitioning to CSA" → "is now CSA" requires a manual rewrite that loses the prior state.

### v3 (proposed)

`memory/people/jr.md` *(unchanged in spirit — narrative, for the human)*:

```markdown
# JR Cruciani

JR is mid-career, currently transitioning into a Cloud Solution Architect
role at Microsoft. Madrid-based. Family: Valeria, Ignacio, Gabriel, Mondo.

For machine-readable facts see [[../facts/jr/]].
```

`memory/facts/jr/employer.md`:

```yaml
---
type: fact
entity: jr
predicate: employer
value: "Microsoft"
valid_from: 2024-01-01
valid_to: null
recorded_at: 2026-05-10T22:30:00Z
confidence: high
sources: ["sources/conv-onboarding.md"]
last_reviewed: 2026-05-10
---
```

`memory/facts/jr/role.md`:

```yaml
---
type: fact
entity: jr
predicate: role
value: "FTE"
valid_from: 2024-01-01
valid_to: 2025-12-31
recorded_at: 2026-05-10T22:30:00Z
superseded_by: "memory/facts/jr/role-2026.md"
sources: ["sources/conv-onboarding.md"]
last_reviewed: 2026-05-10
---
```

`memory/facts/jr/role-2026.md`:

```yaml
---
type: fact
entity: jr
predicate: role
value: "Cloud Solution Architect (CSA, in transition)"
valid_from: 2026-01-01
valid_to: null
recorded_at: 2026-05-10T22:30:00Z
confidence: medium
sources: ["sources/conv-csa-transition.md"]
last_reviewed: 2026-05-10
---
```

Now "what was JR's role in March 2025" is one query:

```bash
tools/query.sh facts --entity jr --predicate role --on 2025-03-15
# → "FTE" (from memory/facts/jr/role.md)
```

And "is anything contradictory about JR right now":

```bash
cat memory/_views/contradictions.md
```

The narrative `people/jr.md` stays for *you*. The atomic facts answer the agent's questions. Both live in plain Markdown. Both can be `tar`'d and moved.

---

## 6. Tools (portable, stdlib-only)

All `tools/*` scripts are written to run with **Python 3.11+ stdlib + PyYAML** or **pure bash + ripgrep + yq**. No pip install of anything else. No background services. No state outside the vault.

- **`lint.py`** — validates frontmatter against `schema/`, checks constraints (P8). Exit 0 = clean.
- **`rebuild-views.sh`** — regenerates everything under `_views/`. Idempotent. Safe to run on every commit.
- **`compact.sh`** — interactive: walks `_inbox/*`, archives expired facts, surfaces stale entries.
- **`query.sh`** — wrappers: `query.sh facts --entity X --predicate Y --on YYYY-MM-DD`, `query.sh events --since YYYY-MM-DD`, etc.
- **`pre-commit`** — runs `lint.py` + `rebuild-views.sh`. Refuses commit on lint failure.

These ship with the vault. Cloning the vault clones the constraint engine.

---

## 7. Migration from v2

v2 → v3 is **additive, not destructive**. Existing v2 vaults keep working through every step.

**Phase 0 — preparation (no behavior change).**
Add `memory/schema/`, `memory/_views/`, `memory/_inbox/`, `memory/_archive/`, `tools/`. Copy in the canonical schemas and scripts. Run `lint.py` — it will pass trivially because no v3-typed files exist yet.

**Phase 1 — start writing new facts atomically.**
From the cutover date, any *new* fact the agent extracts goes to `memory/facts/{entity}/{predicate}.md` instead of being appended to a prose page. Old prose pages remain canonical for everything pre-cutover. The agent reads both during a transition window.

**Phase 2 — append-only events.**
New session logs go to `memory/events/{YYYY-MM-DD}/`. The old `memory/log.md` is frozen and kept as historical record.

**Phase 3 — backfill on demand.**
When you query an entity and the agent realises the prose page has a fact that should be atomic, it extracts it (writing to `facts/`) and leaves a note in the prose page. No big-bang migration. The vault converges as it's used.

**Phase 4 — `_views/` becomes the agent's preferred read.**
Once `facts/` has critical mass for an entity, the agent reads `_views/by-entity/{entity}.md` instead of the prose page for factual queries. The prose page becomes purely human-facing.

At no point is the vault in a broken state. At no point is something destroyed. v2 vaults that never migrate continue to work — v3 is opt-in, file by file.

---

## 8. What v3 is *not*

This must be said plainly to avoid the "v2 was sold as memory and wasn't" trap that *Stop Calling It Memory* correctly punctured.

- v3 is **not** a database. It does not give you SQL, JOINs, or transactional guarantees.
- v3 is **not** a graph engine. `[[wikilinks]]` + `_views/graph.md` is an adjacency rollup, not Cypher.
- v3 is **not** a multi-tenant memory backend. One human, one vault, a small number of cooperative agents.
- v3 does **not** scale to millions of records. The design point is the same as v2: **50–500 personal-context files, plus an open-ended events log** that compaction keeps tractable.
- v3 does **not** automatically forget. Decay is a ritual you run, not a background daemon.

Within those bounds, v3 closes the gaps v2 left open without surrendering what made v2 worth choosing in the first place.

---

## 9. Open questions (RFC)

Before implementation, feedback wanted on:

1. **`predicate` namespace.** Should predicates be free-form (`employer`, `email-personal`) or drawn from a controlled vocabulary in `schema/predicates.yaml`? Free-form is more honest to how prose grows; controlled is more linter-enforceable.
2. **Reflect ritual ownership.** Lance Martin's `/diary` + `/reflect` is a Claude-Code-specific slash command. Should v3 ship a tool-agnostic `tools/reflect.py` invocable from any agent, or leave reflection to the host agent's native rituals (Anthropic Memory Tool, Claude Code, Hermes Agent skills)?
3. **`_views/` in git or `.gitignore`?** Committing them gives `git diff` semantics for derived state (e.g. "this commit introduced a contradiction"). Ignoring them removes a regeneration-vs-source-of-truth confusion vector. Argue both.
4. **Anthropic Memory Tool integration.** v3's `memory/` is shaped exactly like the Memory Tool's `/memories` directory. Should the spec include a normative mapping (`/memories/{x}` ⇄ `memory/{x}`) so users can point one at the other?
5. **Per-fact versus per-entity files.** P2 says one fact per file. An alternative is *one entity per file with one block per fact*, separated by `---` document separators (multi-doc YAML / markdown sections). Per-file is purer but generates many small files; per-entity is denser but harder to lint atomically. Argue.

Comments welcome on the v3 RFC issue: *(to be opened on merge of this PR).*

---

## 10. Manifesto (one paragraph)

A notebook is not a filing cabinet. A filing cabinet is not a database. *Stop Calling It Memory* is right about that — and it was right to reject the cargo-cult version of "AI + Markdown = brain". v3 doesn't argue with the diagnosis. It argues that the response — *"so use SQLite"* — gives up the wrong things. Personal memory you can read with your eyes, edit with your hands, version with `git`, copy-paste to any future provider, and never owe to a vendor's retrieval API is worth keeping. The way to keep it is to take Markdown seriously: atoms, types, schemas, constraints, views, all in plain text, all enforced by tools that travel inside the vault. **Convention is the new schema. Filesystem is the new index.** The rest is rigor.
