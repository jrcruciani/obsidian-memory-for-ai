# Architecture & Manifesto — Why v5.0 Reboots the Protocol

## Core Premise

An AI memory folder that only accumulates atomic facts eventually turns into an append-only junk drawer. Agents do not just need to know *what is true* (`facts`); they need repeatable operational procedures (`skills`), explicit behavioral guardrails (`guidance`), durable rationale (`decisions`), and a disciplined way to turn messy runtime friction into verified institutional knowledge without derailing live tasks.

**The Knowledge Factory Reboot (v5.0)** keeps the foundational constraint—**legible Markdown + YAML frontmatter + Git + offline local tools, with zero database, daemon, or binary truth source**—while redesigning everything built on top of it.

---

## Decisions Challenged From v4.1 (and Why)

### 1. Challenged: "Memory = Facts + Events Only"
- **v4.1 limitation:** Procedural know-how lived in a static `AGENTS.md` file and scattered `insights/`/`context/` prose pages with no lifecycle, triggers, verification checks, or supersession history.
- **v5.0 design:** Promotes `skill` (`knowledge/skills/`) and `guidance` (`knowledge/guidance/`) to first-class canonical types with declarative schemas, temporal supersession chains, domain/scope filters, and automatic inclusion in budgeted `bootstrap` profiles.

### 2. Challenged: "Task Agents Author Canonical Mutations Mid-Flight"
- **v4.1 limitation:** Expecting an executing assistant to pause a user task, inspect `roles.yaml`, craft multi-op payloads, and manage hashes caused skipped capture or low-rigor guesses.
- **v5.0 design:** Introduces `signal` (`factory/signals/`) and decouples **Executor** (`capture signal|event`, `direct_transact: false`) from **Curator** (`curate scan`, `propose create`) and **Reviewer/Owner** (`review`, `publish`).

### 3. Challenged: "Consolidation Creates Unreviewable Empty Draft Proposals (`ops: []`)"
- **v4.1 limitation:** `consolidate.py` wrote `status: draft` files with `ops: []` into `_proposals/`, which `review.py` and `propose.py apply` then refused to touch—polluting proposals with non-proposals.
- **v5.0 design:** Diagnostic drift (`curate scan --emit-signals`) emits idempotent **`signals`** (`stale`, `contradiction`, `broken_reference`, `uncurated_claim`). Every `proposal` in `factory/proposals/` is strictly executable (`len(ops) >= 1`).

### 4. Challenged: "Three Overlapping Write/Audit Subsystems"
- **v4.1 limitation:** Simultaneously carried v3 `_inbox/` envelopes, `_claims/`, `_ops/applied/` receipts, v4 `_transactions/` journals, and `_proposals/`/`_reviews/`.
- **v5.0 design:** Retires `_inbox/`, `_claims/`, `_ops/`, and `compact.py`. Leaves two explicit write paths—review-gated `propose → review → publish` and policy-restricted `owner` `transact`—both emitting one unified `receipt` schema in `factory/receipts/`.

### 5. Challenged: "Underscore Folder Sprawl Inside `memory/`"
- **v4.1 limitation:** Mixing canonical facts (`memory/facts/`), human prose (`people/`, `projects/`, `context/`, `insights/`), pipeline state (`_proposals/`, `_reviews/`, `_transactions/`), and generated views (`_views/`, `_indexes/`) inside one `memory/` directory obscured what was editable vs. derived.
- **v5.0 design:** Separates the vault into four top-level planes: `sources/` (immutable evidence), `knowledge/` (living truth + explicitly non-authoritative `notes/`), `factory/` (schemas, signals, proposals, reviews, receipts), and `_generated/` (non-editable views and indexes).

### 6. Challenged: "Permissive Legacy Dual Encodings"
- **v4.1 limitation:** Accepting both `confidence: high|medium|low` and `0.0..1.0` meant `--min-confidence 0.8` silently missed `"high"` facts; accepting both inclusive `valid_to` and exclusive `valid_until` invited off-by-one bugs.
- **v5.0 design:** Enforces a single canonical representation: float `confidence` (`0.0..1.0` or `null`), half-open `[valid_from, valid_until)` dates, UTC ISO-8601 timestamps, and temporal supersession (retiring destructive `archive_fact`). `kf.py migrate` handles conversion cleanly without inventing fake numbers.

### 7. Challenged: "14 Scripts + 4 Shell Wrappers + Hard External Dependency Failure"
- **v4.1 limitation:** Every vault copied 18 separate scripts/wrappers, and running bare system Python without `PyYAML` crashed every command immediately.
- **v5.0 design:** Ships one unified CLI (`tools/kf.py`) backed by modular `tools/kflib/`, using `PyYAML` when available and falling back transparently to a deterministic stdlib YAML parser/serializer when `PyYAML` is absent.

---

## End-to-End Provenance Graph

Every published change in `knowledge/` forms a verifiable plain-text chain:

```text
sources/2026-09-01-xrf-vendor-bulletin.md       (Primary immutable evidence)
   ▲
   ├── factory/signals/.../sig-xrf-gap.md       (Executor gap capture; status: resolved)
   ▲
   ├── factory/proposals/prop-xrf-skill.md      (Curator executable proposal; SHA-256 content_hash)
   ▲
   ├── factory/reviews/rev-xrf-skill.md         (Independent Reviewer verdict bound to content_hash)
   ▲
   ├── factory/receipts/rcpt-publish-xrf.md     (Atomic publication receipt + before/after file hashes)
   │
   └── knowledge/skills/xrf-pigment-scan.md     (Living procedural skill consumed by Executors)
```

Querying `python3 tools/kf.py query why skill xrf-pigment-scan` reconstructs this entire chain offline in milliseconds.
