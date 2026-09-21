> **Before you clone**
>
> What you see here is an artifact: the concrete shape my problem took. It almost certainly doesn't fit your personal scenario perfectly, and that's fine. The interesting part isn't the code, it's the pattern of how I thought about the problem — that's what transfers. Read it, steal the idea, write your own. If any of this was useful to you, after clicking on the star, drop by [impermanente.es](https://impermanente.es) — there are posts and photos you might like.
>
> Context: [Seguimos compartiendo el producto, no la idea](https://impermanente.es/2026/05/25/seguimos-compartiendo-el-producto-no.html)

---

# Obsidian Memory for AI

**Persistent AI memory in plain Markdown, designed for Obsidian and usable by any assistant that can read files.**

> **Current stable version: v4.1 — Temporal, Traceable Atomic Markdown Memory.**
> The reference implementation lives in [`examples/v4.1-minimal-vault/`](examples/v4.1-minimal-vault/) and the compatibility contract lives in [`SPEC-v4.1.md`](SPEC-v4.1.md).
>
> v4.0 and v3.1 remain supported: [`SPEC-v4.md`](SPEC-v4.md), [`SPEC-v3.md`](SPEC-v3.md).

The project is intentionally boring infrastructure: no database, daemon, vector store, server, embeddings, or binary source of truth. A memory vault is a folder of Markdown and YAML files you can read, edit, diff, sync, copy, and move between tools.

## Start here

| If you want to... | Read |
|---|---|
| Understand the current v4.1 protocol | [`SPEC-v4.1.md`](SPEC-v4.1.md) |
| Copy a working v4.1 vault | [`examples/v4.1-minimal-vault/`](examples/v4.1-minimal-vault/) |
| Upgrade a v4.0 vault | [`migration-v4.1.md`](migration-v4.1.md) |
| Use the previous stable v4.0 protocol | [`SPEC-v4.md`](SPEC-v4.md), [`examples/v4-minimal-vault/`](examples/v4-minimal-vault/) |
| Migrate a v3 vault to v4 | [`migration-v4.md`](migration-v4.md) |
| Use the previous stable v3 protocol | [`SPEC-v3.md`](SPEC-v3.md), [`examples/v3-minimal-vault/`](examples/v3-minimal-vault/) |
| Migrate an older compiled-wiki vault to v3 | [`migration-v3.md`](migration-v3.md) |
| See the full documentation map | [`docs/README.md`](docs/README.md) |
| Understand the legacy v2 pattern | [`guide.md`](guide.md) |

## What v4.1 is

v4.1 builds on v4 transactions, reviews, and indexes while preserving the
original promise: **owned, transparent, portable AI memory in plain Markdown**.

### New in v4.1

| Capability | What it does |
|---|---|
| **Temporal history** | Supersede a fact without losing the old value; query `--as-of` or `--history` |
| **Lineage and trust** | Trace `--why` to evidence; enforce role caps and review for external inputs |
| **Core memory** | Load a deterministic `_views/bootstrap.md` within a character budget |
| **Consolidation** | Report stale facts and create diagnostic drafts for contradictions or broken references |
| **Aliases and retrieval** | Resolve names case/accent-insensitively; rank search identically without indexes |
| **Agent interfaces** | JSON CLIs, concise `AGENTS.md`, and an extraction-to-proposal template |
| **Offline evaluation** | Exact query contracts in CI, with no model or network dependency |

New frontmatter fields are optional. `"4.0"` vaults retain their existing lint
rules; `"4.1"` activates the additions. Legacy confidence labels and dates remain valid.

### Preserved from v3

| Layer | Path | Purpose |
|---|---|---|
| Human narrative | `memory/people/`, `memory/projects/`, `memory/context/`, `memory/decisions/`, `memory/insights/` | Notes you can read naturally in Obsidian |
| Agent facts | `memory/facts/{entity}/{predicate}.md` | One durable typed fact per file |
| Events | `memory/events/YYYY-MM-DD/{slug}.md` | Append-only episodic records |
| Schemas | `memory/schema/` | YAML schemas, controlled predicates, and new role policy |
| Generated views | `memory/_views/` | Derived read models; regenerate, do not hand-edit |
| Agent inbox | `memory/_inbox/{agent-id}/ops/` | Legacy v3 proposed writes (still supported) |
| Operations | `memory/_ops/applied/` | Receipts for applied changes |
| Claims | `memory/_claims/` | Advisory cooperative claims |

The important design move stays: **one fact version, one file**. The current
slot stays readable; superseded versions live in a predicate history folder.
Frontmatter is the schema, `tools/lint.py` is the constraint engine, and
generated `_views/` and `_indexes/` are rebuildable read models.

## Quick start

```bash
# v4.1 vault (current stable)
cd examples/v4.1-minimal-vault
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
source .venv/bin/activate
python3 tools/lint.py
MEMORY_TODAY=2026-09-21 tools/rebuild-views.sh
python3 tools/rebuild_indexes.py
MEMORY_TODAY=2026-09-21 tools/query.sh bootstrap
tools/query.sh facts --entity elena-voss
tools/query.sh facts --entity elena-voss --predicate role --as-of 2026-07-01
tools/query.sh facts --why elena-voss role
tools/query.sh search "Voss"
tools/query.sh graph entity concordance
```

The reference includes Elena's role transition, lineage to a confirmation
event, a reviewed external-source fact, aliases, and generated core memory.
The inherited v4 foundation provides:

- Git-native transactions with idempotency and staging (`tools/transact.py`)
- Formal proposal/review governance with role policy (`tools/propose.py`, `tools/review.py`)
- Deterministic lexical and graph indexes with filesystem fallback (`tools/rebuild_indexes.py`)
- Regression coverage for all supported versions plus 21 offline query evaluations

## When to use this

Use this repository when you want:

- personal or project memory that survives across AI tools
- plain-text ownership and `git diff` auditability
- human-readable notes and agent-readable facts in the same vault
- a small portable toolkit that travels with the vault
- atomic multi-operation writes with idempotency and recovery
- cooperative few-agent writes with formal review governance

Do **not** use it as a replacement for a database-backed enterprise memory system. If your problem needs large-scale graph traversal, ranked retrieval over tens of thousands of records, multi-user OLTP concurrency, or managed personalization for many end users, use SQLite/Kuzu, Mem0, Zep/Graphiti, Letta, Cloudflare Agent Memory, or a RAG platform.

## Repository layout

```text
.
├── README.md                         # Landing page and current orientation
├── docs/README.md                    # Documentation map
├── SPEC-v4.1.md                      # Current: stable v4.1 protocol contract
├── SPEC-v4.md                        # Previous: stable v4.0 protocol contract
├── SPEC-v3.md                        # Previous: stable v3.1 protocol contract
├── migration-v4.1.md                 # v4.0 → v4.1 migration guide
├── migration-v4.md                   # v3 → v4 migration guide
├── migration-v3.md                   # v2 → v3 migration checklist
├── automation-guide.md               # Optional automation patterns
├── plugin-guide.md                   # Optional host-agent plugin pattern
├── obsidian-cli.md                   # Optional Obsidian CLI recipes
├── photo-ingest-guide.md             # Optional photography ingest workflow
├── optional-ideas.md                 # Experimental ideas, not protocol
├── guide.md                          # Legacy v2 compiled-wiki guide
├── examples/
│   ├── v4.1-minimal-vault/           # Current v4.1 reference implementation
│   ├── v4-minimal-vault/             # Preserved v4.0 reference implementation
│   ├── v3-minimal-vault/             # Previous v3 reference implementation
│   └── minimal-vault/                # Legacy v2 reference
└── tests/                            # Regression tests and offline evaluations
```

## Version guide

| Version | Status | Meaning |
|---|---|---|
| v4.1 | **Current stable** | Temporal history, evidence/trust, bootstrap, consolidation, aliases, JSON, evaluations |
| v4.0 | Previous stable | Transactions, proposals/reviews, lexical/graph indexes on top of v3 |
| v3.1 | Previous stable | Agentic operation envelopes, claims, receipts, generated views |
| v3.0 | Frozen schema baseline | Atomic facts, events, schemas, linting, views, inbox compaction |
| v2.1 / v2.0 | Legacy | Prose-first compiled wiki pattern |

## Core commands

From `examples/v4.1-minimal-vault/`:

```bash
# Validate source truth
python3 tools/lint.py

# Regenerate derived views
MEMORY_TODAY=2026-09-21 tools/rebuild-views.sh

# Rebuild deterministic indexes
tools/rebuild-indexes.sh

# Query facts and events
tools/query.sh facts --entity elena-voss
tools/query.sh facts --entity elena-voss --predicate role
tools/query.sh facts --entity elena-voss --predicate role --history
tools/query.sh facts --why concordance tool
tools/query.sh resolve Voss
tools/query.sh events --since 2026-07-01
tools/query.sh search "Berlin"
tools/query.sh graph entity concordance
python3 tools/lint.py --stale --json
python3 tools/consolidate.py --dry-run

# Atomic transaction
python3 tools/transact.py begin --idempotency-key "add-elena-tool-2026-09" --agent agent-local-1234abcd
python3 tools/transact.py add --txn-id <txn-id> --op create_fact \
  --entity elena-voss --predicate tool --value "Obsidian"
python3 tools/transact.py commit --txn-id <txn-id> --yes

# Proposal workflow
python3 tools/propose.py create \
  --title "Add tool fact (alternative to the transaction above)" --namespace facts \
  --proposer agent-local-1234abcd \
  --op create_fact --entity elena-voss --predicate tool --value "Obsidian"
python3 tools/review.py approve --proposal-id <prop-id> --reviewer agent-human-00000001
python3 tools/propose.py apply --proposal-id <prop-id> --yes
```

CI installs PyYAML, lints all three supported reference vaults, rebuilds views
and indexes with deterministic dates, runs the full regression suite and
`python3 tests/eval/run_eval.py`, and fails on generated-artifact drift.

## How this differs from v2

v2 treated `memory/people/elena-voss.md` as both a human page and an agent source of truth. That worked, but it made schema enforcement, querying, concurrency, and drift detection fuzzy.

v3 keeps the human page, but moves the durable fact into files like:

```text
memory/facts/elena-voss/role.md
memory/facts/elena-voss/base.md
memory/facts/elena-voss/employer.md
```

The human note stays readable. The agent fact becomes typed, lintable, queryable with filesystem tools, and safe to propose through `_inbox/`.

## Compatibility with AI tools

| Tool | Recommended integration |
|---|---|
| Claude Code / Copilot CLI / Cursor-like agents | Follow `AGENTS.md`; read `_views/bootstrap.md` first, then query; write through transactions or reviewed proposals |
| Claude Desktop / Cowork-style tools | Package bootstrap-first loading and proposal extraction as commands/skills; see [`plugin-guide.md`](plugin-guide.md) |
| Anthropic Memory Tool | Map `memory/` to `/memories`; read `_views/bootstrap.md` first, then query. Follow `AGENTS.md`; route writes through transaction/proposal tools, never raw edits to generated files or existing events/sources |
| Standalone scripts | Use the portable tools in the vault; see [`automation-guide.md`](automation-guide.md) |
| Obsidian local maintenance | Use Obsidian CLI for native link/property audits; see [`obsidian-cli.md`](obsidian-cli.md) |

## Acknowledgments

This project draws on the plain-file knowledge-base pattern described by Andrej Karpathy, the tiered memory ideas popularized by MemGPT/Letta, typed memory concepts from Chetna, cooperative agent memory patterns from the 2026 memory-tooling ecosystem, and Obsidian's own Markdown-first conventions.

The v3 design keeps the parts that fit a personal, owner-controlled memory layer and deliberately leaves managed infrastructure problems to systems built for that scale.
