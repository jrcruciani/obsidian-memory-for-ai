# Executor vs. Curator Operating Guide

The central operational insight of **Knowledge Factory v5.0** is that **using knowledge under task pressure** and **curating durable institutional knowledge** must be decoupled into distinct roles with distinct budgets, permissions, and tools.

---

## Role Matrix

| Dimension | Executor (`agent-executor-*`) | Curator (`agent-curator-*`) | Reviewer / Owner (`agent-reviewer-*`, `agent-owner-*`) |
|---|---|---|---|
| **Primary goal** | Complete the user's immediate task accurately | Turn signals, events, and raw sources into clean proposals | Enforce accuracy, trust caps, and governance before publication |
| **Bootstrap profile** | `kf.py bootstrap --profile executor` | `kf.py bootstrap --profile curator` | `kf.py bootstrap --profile default` + `factory-queue.md` |
| **Reads most** | `facts`, `skills`, `guidance`, `decisions` | Open `signals`, recent `events`, `sources/`, stale report | Pending `proposals`, `reviews`, `policy.yaml`, `sources/` |
| **Allowed writes** | `capture signal`, `capture event` | `curate scan --emit-signals`, `curate dismiss-signal`, `propose create` | `review approve\|reject\|request-changes`, `publish`, (`owner`: `transact`) |
| **Direct `knowledge/` mutation** | **Forbidden** | **Forbidden** | `publish` (any reviewer/owner) or `transact` (`owner` only, non-external) |

---

## 1. The Executor Loop (Fast & Safe)

1. **Bootstrap:** Read `_generated/views/bootstrap-executor.md` (or run `python3 tools/kf.py bootstrap --profile executor`). This loads critical/executor `guidance`, pinned `facts`, active `skills` (with trigger keywords), and recent `decisions` within a strict character budget.
2. **Query before acting:**
   - Resolve entity names/aliases: `python3 tools/kf.py query resolve "<name>"`
   - Load matching procedures: `python3 tools/kf.py query skills --trigger "<keyword>"`
   - Inspect facts & lineage: `python3 tools/kf.py query facts --entity <id>` and `query why`
3. **Capture friction & gaps—never improvise silent schema edits:**
   When a skill is missing, a fact looks outdated, two sources disagree, or a new event occurs:
   ```bash
   python3 tools/kf.py capture signal \
     --emitted-by agent-executor-00000004 \
     --kind gap \
     --severity high \
     --target-namespace skills \
     --summary "Missing procedure for azurite spectral deconvolution" \
     --entities concordance \
     --evidence sources/2026-10-12-venice-panel-field-notes.md \
     --idempotency-key gap-azurite-deconv
   ```

### Signal Taxonomy (`--kind`)

| Kind | When to Emit |
|---|---|
| `gap` | Needed a fact, skill, or policy guardrail that does not exist in `knowledge/` |
| `friction` | An existing skill or workflow step was ambiguous, brittle, or incomplete |
| `contradiction` | New primary evidence or event assertions conflict with an active record |
| `stale` | A record's `review_after` passed or reality moved on |
| `observation` | Useful domain observation worth curator evaluation |
| `uncurated_claim` | Emitted by `curate scan` when an `event.asserts` claim has no corresponding fact |
| `broken_reference` | Emitted by `curate scan` if any lineage path is missing |

---

## 2. The Curator Loop (Deliberate & Evidence-Driven)

Run a Curator session after a work sprint, on a schedule, or when open signals accumulate:

1. **Load Curator Context & Scan Drift:**
   ```bash
   python3 tools/kf.py bootstrap --profile curator
   python3 tools/kf.py curate scan --emit-signals --emitted-by agent-curator-00000003
   python3 tools/kf.py query signals --status open
   ```
2. **Triage Noise vs. Signal:**
   - If an open signal is a duplicate, temporary anomaly, or out of scope, dismiss it with an explicit rationale (creates an audited `signal_triage` receipt):
     ```bash
     python3 tools/kf.py curate dismiss-signal \
       --signal-id <sig-id> \
       --curator agent-curator-00000003 \
       --reason "Temporary loan bench; permanent Berlin base unchanged." \
       --yes --rebuild
     ```
3. **Synthesize Executable Proposals:**
   - Read the primary `sources/` and `events/` referenced by the signal.
   - Author a concrete proposal (`create_fact`, `supersede_fact`, `create_skill`, `supersede_skill`, `create_guidance`, `create_decision`, or `mixed` bundle) linking `--resolves-signals`:
     ```bash
     python3 tools/kf.py propose create \
       --title "Add tempera relative humidity ceiling guidance" \
       --namespace guidance \
       --proposer agent-curator-00000003 \
       --rationale "Codifies Venice field notes into an executor guardrail." \
       --resolves-signals <sig-id> \
       --ops-file ops.yaml
     ```
   - Linked signals automatically transition from `open` → `proposed`.

---

## 3. The Reviewer & Publisher Loop (Independent Governance)

1. **Inspect Pending Proposals:**
   ```bash
   python3 tools/kf.py propose list --status proposed
   python3 tools/kf.py propose show --proposal-id <prop-id>
   ```
2. **Verify Provenance & Policy:**
   - Confirm cited `derived_from` sources actually state what the proposal claims.
   - Confirm `trust` (`external`, `agent`, `owner`) and numeric `confidence` are honest.
   - Submit a hash-bound verdict as a **different** authorized agent (`reviewer` or `owner`):
     ```bash
     python3 tools/kf.py review approve \
       --proposal-id <prop-id> \
       --reviewer agent-reviewer-00000002 \
       --comment "Verified against field notes."
     ```
3. **Publish Atomically:**
   ```bash
   python3 tools/kf.py publish \
     --proposal-id <prop-id> \
     --publisher agent-reviewer-00000002 \
     --yes --rebuild
   python3 tools/kf.py lint --strict
   ```
   Publication validates a full shadow copy first, writes living records to `knowledge/`, marks linked `signals` as `resolved`, updates the proposal to `published`, records `factory/receipts/rcpt-*.md`, and regenerates `_generated/`.
