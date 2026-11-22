# Obsidian Memory for AI — v5.0: The Knowledge Factory Reboot

**Turn a plain Markdown Obsidian vault into a governed, offline Knowledge Factory where AI agents capture gaps, curate evidence into proposals, review changes, and consume living facts, skills, and guidance.**

> **Current protocol:** **v5.0 — The Knowledge Factory (`SPEC-v5.0.md`)**
> **Reference vault:** [`examples/v5-knowledge-factory/`](examples/v5-knowledge-factory/)
> **Migrating from v4.0 / v4.1?** Run `python3 tools/kf.py migrate` — see [`docs/migration-from-v4.1.md`](docs/migration-from-v4.1.md).

---

## Why 5.0 Is a Reboot, Not v4.2

Earlier versions (`v2` → `v4.1`) proved that plain Markdown, YAML frontmatter, and Git can give AI assistants durable, inspectable memory without a database, vector store, or daemon. Yet treating memory as a **passive store of atomic facts** hit a ceiling:

1. **Agents need procedural and normative knowledge, not just facts.** Knowing *where Elena works* (`fact`) does not teach an agent *how to calibrate a non-destructive XRF scan* (`skill`) or *when to halt spectroscopy in high humidity* (`guidance`).
2. **Task execution and knowledge curation are opposite cognitive modes.** Asking an agent mid-task to author schema-perfect mutations leads to skipped updates or noisy guesses.
3. **Accreted legacy layers blurred authority.** Carrying v3 `_inbox/`, `_claims/`, `_ops/`, v4 `_transactions/`, five overlapping prose folders, and unreviewable empty diagnostic drafts made vaults harder to reason about.

**v5.0 re-architects the vault as a Knowledge Factory** while keeping the non-negotiable core intact: **100% legible Markdown + YAML frontmatter + Git + local offline Python 3 tools (zero database, zero daemon, zero binary truth source, and a built-in stdlib YAML fallback when `PyYAML` is absent).**

---

## How the Knowledge Factory Works

```text
Executor Agent (fast, read-mostly)
  ├─ Consumes: budgeted `bootstrap --profile executor` + `query {facts,skills,guidance,decisions}`
  └─ Captures: append-only `signals` (gaps, friction, contradictions) & `events`
         │
         ▼
Curator Agent (decoupled, analytical)
  ├─ Scans:    `curate scan --emit-signals` + open signals + `sources/`
  └─ Proposes: executable hash-bound `proposals` (facts, skills, guidance, decisions)
         │
         ▼
Reviewer / Owner (governance gate)
  ├─ Audits:   `review approve|reject|request-changes` (self-approval prohibited)
  └─ Publishes:`publish --yes --rebuild` -> updates `knowledge/`, closes `signals`, writes `receipt`
```

### Four Vault Planes

| Plane | Directory | Role |
|---|---|---|
| **0. Primary Sources** | `sources/` | Immutable raw transcripts, bulletins, field logs |
| **1. Living Knowledge** | `knowledge/` | Canonical `entities.md`, `facts/`, `events/`, `skills/`, `guidance/`, `decisions/`, and non-authoritative `notes/` |
| **2. Factory Ledger** | `factory/` | `schema/` (`manifest.yaml`, `policy.yaml`, `*.schema.yaml`), `signals/`, `proposals/`, `reviews/`, `receipts/` |
| **3. Derived Read Models** | `_generated/` | Regenerable, non-editable `views/` and `indexes/` protected by SHA-256 digests |

---

## Quick Start

```bash
# Explore and verify the v5.0 reference vault (works with Python 3.10+; PyYAML optional)
cd examples/v5-knowledge-factory

# 1. Validate schemas, cross-record invariants, lineage, and _generated/ integrity
KF_TODAY=2026-10-15 python3 tools/kf.py lint --strict

# 2. Load role-specific budgeted bootstrap context
KF_TODAY=2026-10-15 python3 tools/kf.py bootstrap --profile executor
KF_TODAY=2026-10-15 python3 tools/kf.py bootstrap --profile curator

# 3. Query living facts (current, historical --as-of, skills, guidance, and full Factory lineage)
KF_TODAY=2026-10-15 python3 tools/kf.py query facts --entity elena-voss
KF_TODAY=2026-10-15 python3 tools/kf.py query facts --entity elena-voss --predicate role --as-of 2026-07-01
KF_TODAY=2026-10-15 python3 tools/kf.py query skills --trigger "xrf"
KF_TODAY=2026-10-15 python3 tools/kf.py query guidance --scope executor
KF_TODAY=2026-10-15 python3 tools/kf.py query why skill xrf-pigment-scan
KF_TODAY=2026-10-15 python3 tools/kf.py query search "Voss"
KF_TODAY=2026-10-15 python3 tools/kf.py query graph concordance

# 4. Initialize a brand-new vault anywhere
python3 tools/kf.py init ~/MyKnowledgeFactory
```

---

## Key Workflow Commands

```bash
# Executor: capture a knowledge gap without mutating canonical truth
python3 tools/kf.py capture signal \
  --emitted-by agent-executor-00000004 \
  --kind gap --severity high --target-namespace skills \
  --summary "Missing calibration checklist for Raman portable probe" \
  --entities concordance

# Curator: scan vault drift and synthesize a proposal closing the signal
python3 tools/kf.py curate scan --emit-signals --emitted-by agent-curator-00000003
python3 tools/kf.py propose create \
  --title "Add Raman probe calibration skill" \
  --namespace skills \
  --proposer agent-curator-00000003 \
  --resolves-signals <sig-id> \
  --ops-file proposal_ops.yaml

# Reviewer / Owner: review and publish atomically
python3 tools/kf.py review approve --proposal-id <prop-id> --reviewer agent-reviewer-00000002 --comment "Verified."
python3 tools/kf.py publish --proposal-id <prop-id> --publisher agent-reviewer-00000002 --yes --rebuild
```

Every command accepts `--json` for structured machine consumption.

---

## Documentation Map

| Topic | Document |
|---|---|
| Normative v5.0 protocol contract | [`SPEC-v5.0.md`](SPEC-v5.0.md) |
| Architecture manifesto & retired legacy concepts | [`docs/architecture.md`](docs/architecture.md) |
| Executor vs. Curator vs. Reviewer operating guide | [`docs/executor-and-curator.md`](docs/executor-and-curator.md) |
| Migrating from v4.0 / v4.1 (`kf.py migrate`) | [`docs/migration-from-v4.1.md`](docs/migration-from-v4.1.md) |
| Operational anti-patterns & failure modes | [`docs/anti-patterns.md`](docs/anti-patterns.md) |
| Host-agent & Obsidian integrations | [`docs/integrations.md`](docs/integrations.md) |
| Open product & protocol decisions | [`docs/open-decisions.md`](docs/open-decisions.md) |
| Full documentation index | [`docs/README.md`](docs/README.md) |
| Offline deterministic query evaluations | [`tests/eval/README.md`](tests/eval/README.md) |

---

## When to Use (and Not Use) This

**Use Knowledge Factory v5.0 when you want:**
- Plain-text ownership in Obsidian with full `git diff` and `receipt` provenance from raw evidence → signal → proposal → review → living truth.
- Governed `facts`, `skills`, `guidance`, and `decisions` shared across Claude Code, Codex, Hermes, Cursor, or custom local scripts.
- Strict separation between fast task execution and deliberate offline knowledge curation.

**Do not use this when you need:**
- High-concurrency multi-tenant OLTP, sub-millisecond vector retrieval over hundreds of thousands of documents, or cryptographic isolation against untrusted local users with write access to the Git tree.
