# SPEC v5.0 — The Knowledge Factory Protocol

> **Status:** Stable v5.0 — Current normative protocol (`protocol: "knowledge-factory"`, `spec_version: "5.0"`)
> **Supersedes:** v4.1 (`docs/archive/SPEC-v4.1.md`), v4.0, v3.x, and v2.x (breaking directory and CLI reboot; automated migration via `tools/kf.py migrate`)
> **Reference implementation:** [`examples/v5-knowledge-factory/`](examples/v5-knowledge-factory/) and [`tools/`](tools/)
> **Canonical state:** Human-readable Markdown + YAML frontmatter + Git.
> **Explicitly excluded as truth source:** Databases, SQLite, daemons, servers, vector stores, proprietary backends, or binary storage formats.

---

## 1. Thesis & Protocol Manifesto

Versions 2 through 4.1 treated AI memory primarily as a **passive filing cabinet for declarative facts and episodic events**. In practice, real agent systems fail on three broader fronts:

1. **Procedural and normative amnesia:** Agents do not merely forget facts; they improvise procedures (`skills`) and violate domain guardrails (`guidance`) when operational know-how lives only in static prompts or unversioned prose notes.
2. **Runtime capture friction:** Asking a task-executing agent to pause mid-flight, design schema-compliant updates, check governance rules, and resolve conflicts produces either skipped updates or low-rigor mutations.
3. **Diagnostic pollution and multi-era sediment:** Accreting v3 `_inbox/` envelopes, `_claims/`, `_ops/`, v4 `_transactions/`, and empty unreviewable consolidation drafts (`ops: []`) obscured which files were authoritative, which were pipeline state, and which were derived read models.

**v5.0 reboots the repository around a Knowledge Factory operating model:**

- **Plain text remains sovereign:** Every living truth record, pipeline artifact, and audit receipt is a plain Markdown file with YAML frontmatter tracked in Git. Tooling runs 100% offline on Python 3 (`PyYAML` supported when installed, with a built-in zero-dependency stdlib YAML parser/serializer fallback).
- **Three pillars of living knowledge:** Agents consume governed **Declarative** (`facts`, `events`, `decisions`), **Procedural** (`skills`), and **Normative** (`guidance`) knowledge from one coherent schema engine.
- **Role-decoupled factory loop (`capture → curate → review → publish → consume`):**
  1. **Executors** focus on tasks, consume budgeted context, and emit low-friction append-only **`signals`** (gaps, friction, contradictions, observations) and **`events`**—never mutating `knowledge/` directly.
  2. **Curators** run decoupled offline passes (`curate scan`), triage signals and raw evidence, and synthesize executable, hash-bound **`proposals`**.
  3. **Reviewers / Owners** audit proposals against namespace policy (`policy.yaml`), submit cryptographically bound **`reviews`** (self-approval forbidden), and atomically **`publish`** changes—closing linked signals and writing immutable **`receipts`**.

---

## 2. Four-Plane Vault Architecture

A v5.0 vault separates concerns into four top-level planes so humans in Obsidian and agents on the filesystem never confuse raw evidence, living truth, pipeline governance, and derived views:

```text
vault-root/
├── AGENTS.md                        # Role-dispatched operating contract (Executor / Curator / Reviewer)
├── CLAUDE.md                        # Host compatibility pointer to AGENTS.md
├── sources/                         # Plane 0: Immutable primary evidence (transcripts, bulletins, field notes)
├── knowledge/                       # Plane 1: Living Canonical Knowledge (Truth Source)
│   ├── entities.md                  # Canonical entity registry + NFKD case/accent-folded aliases
│   ├── facts/{entity}/{pred}.md     # Active fact; superseded chain in {pred}/YYYY-MM-DD[-N].md
│   ├── events/YYYY-MM-DD/{id}.md    # Append-only episodic occurrences & raw structured claims
│   ├── skills/{slug}.md             # Active procedure; superseded chain in {slug}/YYYY-MM-DD[-N].md
│   ├── guidance/{slug}.md           # Active guardrail/policy; superseded chain in {slug}/YYYY-MM-DD[-N].md
│   ├── decisions/{id}.md            # Accepted ADRs; superseded chain in {id}/YYYY-MM-DD[-N].md
│   └── notes/{kind}/{slug}.md       # Optional non-authoritative Obsidian narrative pages
├── factory/                         # Plane 2: Factory Pipeline, Schemas & Governance Ledger
│   ├── schema/
│   │   ├── manifest.yaml            # spec_version: "5.0", protocol: "knowledge-factory", settings
│   │   ├── predicates.yaml          # Controlled predicate vocabulary
│   │   ├── policy.yaml              # Roles, agents, namespaces, approval thresholds, trust caps
│   │   ├── bootstrap.yaml           # Role-aware character-budgeted bootstrap profiles
│   │   └── *.schema.yaml            # Executable declarative schemas for all canonical types
│   ├── signals/YYYY-MM-DD/{id}.md   # Append-only gap, friction, stale, contradiction & claim flags
│   ├── proposals/{id}.md            # Executable candidate change bundles (SHA-256 content_hash)
│   ├── reviews/{id}.md              # Independent reviewer verdicts bound to proposal_content_hash
│   ├── receipts/{id}.md             # Unified immutable audit receipts (publish, transact, triage, migrate)
│   └── _staging/{txn-id}/           # Ephemeral crash-recovery staging (never committed)
└── _generated/                      # Plane 3: Regenerable Non-Editable Read Models
    ├── views/                       # bootstrap*.md, catalog.md, factory-queue.md, stale.md, conflicts.md, timeline.md, by-entity/*.md
    └── indexes/                     # lexical.md, graph.md
```

---

## 3. Canonical Record Types & Schemas

Every Markdown record in `knowledge/` and `factory/` (outside `factory/schema/*.yaml`) carries YAML frontmatter validated dynamically against `factory/schema/{type}.schema.yaml` by `tools/kf.py lint`. All record `id` values MUST be globally unique across the vault.

### 3.1 `entity-registry` (`knowledge/entities.md`)

Declares canonical entity slugs (`[a-z0-9][a-z0-9_-]*`), kinds (`person`, `project`, `organization`, `instrument`, `system`, `place`, `concept`), display names, and `aliases`. Aliases are normalized with Unicode NFKD, stripped of combining marks, and case-folded; folded collisions across distinct entities fail lint.

### 3.2 `fact` (`knowledge/facts/{entity}/{predicate}.md`)

```yaml
type: fact
id: fact-elena-voss-role-2026-07-15
entity: elena-voss
predicate: role
value: Lead conservator and pigment researcher
status: active                  # active | superseded | retracted
valid_from: "2026-07-15"        # ISO date or null (open start)
valid_until: null               # Exclusive ISO date upper bound [valid_from, valid_until) or null
observed_at: "2026-07-15T10:05:00Z"
confidence: 0.98                # Float in 0.0..1.0 or null (legacy string labels rejected in v5.0)
assertion: stated               # stated | observed | inferred
trust: owner                    # owner | agent | external
derived_from:
  - knowledge/events/2026-07-15/evt-role-confirmation.md
supersedes: knowledge/facts/elena-voss/role/2026-03-15.md
pinned: true
last_confirmed: "2026-09-15"
review_after: null
```

- **Half-open temporal semantics:** Validity windows are strictly `[valid_from, valid_until)`. When superseded, the prior fact moves to `knowledge/facts/{entity}/{predicate}/{YYYY-MM-DD[-N]}.md` with `status: superseded` and `valid_until` equal to the new head's `valid_from`.

### 3.3 `event` (`knowledge/events/YYYY-MM-DD/{id}.md`)

Append-only episodic record: `id`, `occurred_at` (UTC ISO-8601), `recorded_by`, `summary`, `entities`, `sources`, optional `tags`, and optional `asserts: [{entity, predicate, value}]`. Structured `asserts` are raw claims—never automatically accepted facts—until curated and published.

### 3.4 `skill` (`knowledge/skills/{slug}.md`)

Governed procedural knowledge consumed by agents when task triggers match:

```yaml
type: skill
id: skill-xrf-pigment-scan-v1
slug: xrf-pigment-scan
title: Non-Destructive XRF Pigment Scan
status: active                  # active | superseded | deprecated | retracted
version: 1
domain: conservation
triggers: ["xrf scan", "pigment analysis"]
inputs: ["panel region coordinates", "ambient RH reading"]
outputs: ["calibrated keV peak table"]
verification:
  - "Confirm copper K-alpha reference within +/- 0.02 keV"
entities: [concordance, elena-voss]
derived_from:
  - sources/2026-09-01-xrf-vendor-bulletin.md
  - factory/signals/2026-09-02/sig-missing-standardized-20260902t093000z-6d2911d2.md
trust: agent
confidence: 0.94
observed_at: "2026-09-03T15:10:00Z"
last_confirmed: "2026-09-03"
review_after: null
supersedes: null
pinned: true
```

### 3.5 `guidance` (`knowledge/guidance/{slug}.md`)

Governed normative guardrails, preferences, and explicit anti-patterns scoped by role:

- Required fields: `type: guidance`, `id`, `slug`, `title`, `status` (`active | superseded | retracted`), `domain`, `scope` (`executor | curator | reviewer | all`), `priority` (`critical | high | normal`), `policy_rule` (concise imperative rule injected into budgeted bootstrap), `trust` (`owner | agent`), `observed_at`, `last_confirmed`.
- Optional fields: `anti_patterns` (`list[str]`), `entities`, `derived_from`, `review_after`, `supersedes`, `pinned`.

### 3.6 `decision` (`knowledge/decisions/{id}.md`)

Durable architectural or domain decisions (`DEC-NNN...`): `id`, `title`, `status` (`accepted | superseded | deprecated | retracted`), `decided_at` (ISO date), `decided_by`, `domain`, `summary`, `entities`, `derived_from`, `consequences`, `supersedes`, `pinned`.

### 3.7 `signal` (`factory/signals/YYYY-MM-DD/{id}.md`)

Lightweight diagnostic flag or gap emitted by Executors or `kf.py curate scan`:

- `kind`: `gap | contradiction | friction | stale | observation | broken_reference | uncurated_claim`
- `severity`: `low | medium | high`
- `status`: `open -> proposed -> resolved` (or `dismissed` via audited curator triage)
- Carries `emitted_by`, `summary`, `target_namespace`, `entities`, `related_paths`, `evidence`, optional `idempotency_key`, `proposal_id`, `resolved_at`, `resolved_by_receipt`, `resolution_note`.

### 3.8 `proposal` (`factory/proposals/{id}.md`)

Executable candidate change bundle authored by a Curator or Owner:

- Required: `id`, `title`, `namespace` (`entities | facts | events | skills | guidance | decisions | mixed`), `proposer_id`, `status` (`draft | proposed | changes_requested | approved | rejected | conflict | published`), `created_at`, `ops` (**non-empty list** of supported operations), `required_approvals`, `content_hash`.
- `content_hash` is `sha256:` over canonical sorted JSON of `{title, namespace, proposer_id, ops, resolves_signals}`.
- Proposals with empty `ops` are **invalid in v5.0**; purely diagnostic findings belong in `factory/signals/`.

### 3.9 `review` (`factory/reviews/{id}.md`)

Independent governance verdict on a proposal: `id`, `proposal_id`, `reviewer_id`, `verdict` (`approved | rejected | changes_requested`), `created_at`, `proposal_content_hash`, and `comment` (mandatory on `rejected` or `changes_requested`).

### 3.10 `receipt` (`factory/receipts/{id}.md`)

Unified immutable audit record replacing both v3 `_ops/` and v4 `_transactions/`:

- `mode`: `proposal_publish | direct_transaction | signal_triage | migration | rollback`
- `status`: `committed | failed | rolled_back`
- Records `idempotency_key`, `actor_id`, `proposer_id`, `proposal_id`, `review_ids`, `resolved_signals`, `created_at`, `committed_at`, `expected_revision`, `parent_revision` (Git HEAD SHA), `ops`, and `touched_files: [{path, action, before_hash, after_hash}]`.

### 3.11 `note` (`knowledge/notes/{kind}/{slug}.md`)

Optional human narrative Obsidian pages (`kind: person | project | context | insight | general`) with `authoritative: false` enforced by lint so narrative prose never impersonates canonical truth.

---

## 4. The Knowledge Factory Lifecycle

```text
  [Executor Task Run]
          │
          ├── Consumes ──► kf bootstrap --profile executor + kf query
          │
          ▼ (detects gap / friction / new raw event)
   1. CAPTURE ───────────► factory/signals/*.md  &  knowledge/events/*.md
          │
          ▼ (decoupled Curator pass: kf curate scan + kf propose create)
   2. CURATE ────────────► factory/proposals/*.md  (links resolves_signals + derived_from)
          │
          ▼ (independent Reviewer: kf review approve|reject|request-changes)
   3. REVIEW ────────────► factory/reviews/*.md    (bound to proposal content_hash)
          │
          ▼ (kf publish --yes --rebuild)
   4. PUBLISH ───────────► knowledge/{facts,skills,guidance,decisions}/*.md
          │                + factory/receipts/*.md + signals marked resolved
          ▼
   5. CONSUME ───────────► _generated/{views,indexes}/*.md + deterministic queries
```

### Role & Trust Policy (`factory/schema/policy.yaml`)

| Role | Capture Signals/Events | Propose | Review & Publish | Direct `transact` | Default `max_trust` |
|---|:---:|:---:|:---:|:---:|:---:|
| `executor` | Yes | `events` only | No | **No** | `agent` |
| `curator` | Yes | All namespaces | No | **No** | `agent` |
| `reviewer` | Yes | Configured | Yes (never own proposal) | **No** | `owner` |
| `owner` | Yes | All namespaces | Yes (never own proposal) | **Yes** (non-external) | `owner` |

Trust ordering is `external < agent < owner`. Operations with `trust: external` ALWAYS require `propose → review → publish` when `external_requires_review: true`, even if authored by `owner`. Review approval authorizes publication; it never elevates a proposer's `max_trust` cap.

---

## 5. Unified CLI Contract (`tools/kf.py`)

Every command supports `--vault <dir>` and `--json` (before or after the subcommand). JSON mode outputs a single object `{ok, exit_code, protocol_version: "5.0", command, data, text, diagnostics}` on stdout and emits diagnostics on stderr.

| Command | Purpose |
|---|---|
| `kf.py init <dir> [--force]` | Scaffold a four-plane v5.0 vault with schemas, tools, and initial `_generated/` |
| `kf.py lint [--strict] [--stale] [--check-generated]` | Validate schemas, cross-record invariants, lineage, wikilinks, and `_generated/` integrity |
| `kf.py bootstrap [--profile default\|executor\|curator] [--budget N]` | Compute deterministic character-budgeted context directly from canonical files |
| `kf.py capture signal\|event ...` | Append-only low-friction capture for Executor agents |
| `kf.py curate scan [--emit-signals]` / `dismiss-signal` | Detect stale/contradictory/uncurated drift into `signals`, or dismiss signals with receipt |
| `kf.py propose create\|list\|show` | Author and inspect hash-bound executable proposals |
| `kf.py review approve\|reject\|request-changes\|list` | Record independent hash-bound review verdicts |
| `kf.py publish --proposal-id ID --publisher AGENT --yes [--rebuild]` | Validate candidate vault in shadow copy, publish atomically, close signals, emit receipt |
| `kf.py transact begin\|add\|commit\|rollback\|recover\|list` | Policy-gated atomic multi-operation transactions for `owner` |
| `kf.py query facts\|skills\|guidance\|decisions\|events\|signals\|proposals\|receipts\|why\|resolve\|id\|search\|graph` | Deterministic queries and full end-to-end lineage |
| `kf.py rebuild [--views-only\|--indexes-only]` | Deterministically regenerate `_generated/views/` and `_generated/indexes/` |
| `kf.py migrate --source <v4_dir> --target <v5_dir> --yes` | Offline migration from v4.0/v4.1 vaults with audit archive and migration receipt |

---

## 6. Budgeted Bootstrap & Non-Editable `_generated/` Guarantees

1. **Role-aware budgeted bootstrap (`factory/schema/bootstrap.yaml`):**
   - Defines character budgets (`budget_chars`) and ordered section pipelines per profile (`default`, `executor`, `curator`).
   - Counts exact Unicode characters including banner, headings, newlines, and footer:
     `<!-- bootstrap: profile=executor, N items, M/B chars, generated YYYY-MM-DD -->`
   - Never truncates an item mid-line and fails explicitly if `budget_chars` cannot fit the empty envelope.
   - All date windowing honors `KF_TODAY` (falling back to `MEMORY_TODAY`, then system date).

2. **Regenerable, non-editable `_generated/` artifacts:**
   - Every file under `_generated/` embeds a machine-verified header:
     `<!-- DO NOT EDIT: generated by kf rebuild | source_digest=sha256:... | content_sha256=sha256:... -->`
   - Deleting `_generated/` and running `kf.py rebuild` produces byte-identical output for the same canonical vault and `KF_TODAY`.
   - `kf.py query search` and `kf.py query graph` compute answers from canonical records; missing indexes change nothing, and stale/hand-edited indexes emit a `WARN` diagnostic on stderr without corrupting stdout.
   - Hand-editing any file in `_generated/` fails `kf.py lint --strict` (`content_sha256 mismatch`).

---

## 7. Core Invariants

| Invariant | Enforcement |
|---|---|
| Candidate-vault preflight | `publish`, `transact commit`, `capture`, and `propose create` validate a full shadow copy with `lint_vault` before writing live files |
| Preimage crash recovery | Interrupted writes restore preimages via `kf.py transact recover --yes` |
| No self-approval | `review`, `publish`, and `lint` reject `reviewer_id == proposer_id` |
| Hash-bound reviews | Editing a proposal changes `content_hash`, invalidating prior reviews |
| Non-empty proposals | Schema & `create_proposal` forbid `ops: []`; diagnostics use `signal` |
| Single active head per slot | At most one `status: active` record at `knowledge/{facts,skills,guidance}/{slot}.md` |
| Half-open intervals | `valid_from < valid_until`; adjacent supersessions satisfy `old.valid_until == new.valid_from` |
| Numeric confidence only | `0.0 <= confidence <= 1.0` or `null`; qualitative legacy strings are rejected |
| Non-editable `_generated/` | Embedded `source_digest` + `content_sha256` verified by `lint --strict` |
| Source & event immutability | `sources/` is read-only evidence; `knowledge/events/` refuses overwrites |

---

## 8. Retraction, Forgetting & Threat Boundaries

- **Non-destructive retraction:** Use `retract_fact`, `retract_skill`, or `retract_guidance` (`status: retracted`, `retracted_at`, `retraction_reason`). Retracted records disappear from current queries, `search`, and `bootstrap`, while remaining auditable in `--history` and `receipts`.
- **Git history vs. true erasure:** Retraction withdraws reliance; it does not scrub prior Git commits or remote clones. True erasure of sensitive personal data requires out-of-protocol history rewriting (`git filter-repo`) coordinated across all copies.
- **Cooperative local governance:** Role and trust policies prevent accidental agent drift, self-approval, and unreviewed external ingestion; they are not a cryptographic sandbox against an untrusted actor with raw filesystem write access to `factory/schema/policy.yaml`.

---

## 9. Acceptance & Quality Gates

```bash
# 1. Strict lint + _generated/ tamper/drift check on reference vault
KF_TODAY=2026-10-15 python3 tools/kf.py --vault examples/v5-knowledge-factory lint --strict

# 2. Byte-identical double rebuild gate
KF_TODAY=2026-10-15 python3 tools/kf.py --vault examples/v5-knowledge-factory rebuild
git diff --exit-code -- examples/v5-knowledge-factory/_generated

# 3. Full offline unit, governance, lineage & v4.1->v5.0 migration suite
python3 -m unittest discover -s tests -v

# 4. Deterministic 26-contract offline query evaluation gate
python3 tests/eval/run_eval.py
```
