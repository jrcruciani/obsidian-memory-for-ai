# Migrating From v4.0 / v4.1 to Knowledge Factory v5.0

v5.0 intentionally breaks v3/v4 directory paths and CLI commands to eliminate multi-era duplication and establish the four-plane Knowledge Factory layout. **`tools/kf.py migrate` automates the entire structural and schema conversion offline** without modifying your source v4 vault.

---

## 1. Automated Migration Walkthrough

```bash
# 1. Run offline migration into a new v5.0 target folder
python3 tools/kf.py migrate \
  --source /path/to/your-v4.1-vault \
  --target /path/to/your-v5.0-vault \
  --yes

# 2. Enter the migrated vault and run strict validation
cd /path/to/your-v5.0-vault
python3 tools/kf.py lint --strict

# 3. Inspect migration receipt and curation signals created during migration
python3 tools/kf.py query receipts --mode migration
python3 tools/kf.py query signals --status open
```

---

## 2. Structural & Schema Crosswalk (`v4.1` → `v5.0`)

| v4.1 Path / Concept | v5.0 Destination | Migration Behavior |
|---|---|---|
| `sources/**` | `sources/**` | Copied byte-for-byte unchanged |
| `memory/entities.md` (+ `memory/entities/*.md`) | `knowledge/entities.md` | Merged into `type: entity-registry` preserving all IDs, kinds, and NFKD aliases |
| `memory/facts/{entity}/{pred}.md` | `knowledge/facts/{entity}/{pred}.md` | Active head preserved; `derived_from` merges legacy `sources` + `derived_from` with rewritten `knowledge/` paths |
| `memory/facts/{entity}/{pred}/{date}.md` | `knowledge/facts/{entity}/{pred}/{date}.md` | Temporal supersession chain preserved; `status: superseded` set explicitly |
| `memory/events/YYYY-MM-DD/*.md` | `knowledge/events/YYYY-MM-DD/*.md` | Preserved append-only; `asserts` carried forward |
| `memory/decisions/*.md` | `knowledge/decisions/*.md` | Upgraded to v5 `decision` schema with `domain`, `summary`, and rewritten `derived_from` |
| `memory/{people,projects,context,insights}/*.md` | `knowledge/notes/{people,projects,context,insights}/*.md` | Wrapped in `type: note` (`authoritative: false`), wikilinks rewritten to `knowledge/...`, plus curation signal emitted for insights/context |
| `memory/schema/version.yaml` | `factory/schema/manifest.yaml` | Upgraded to `spec_version: "5.0"`, `protocol: "knowledge-factory"` |
| `memory/schema/predicates.yaml` | `factory/schema/predicates.yaml` | Custom v4 predicates merged with v5 defaults |
| `memory/schema/roles.yaml` | `factory/schema/policy.yaml` | Legacy roles mapped (`admin → owner`, `reviewer → reviewer`, `proposer → curator`) alongside standard v5 Executor/Curator/Reviewer/Owner roles |
| `memory/{_transactions,_proposals,_reviews}/` | `sources/v4-audit-archive/` + `factory/receipts/` | Legacy governance logs archived intact as read-only provenance; a formal `mode: migration` receipt hashes every migrated v5 file |
| `memory/_views/` & `memory/_indexes/` | `_generated/views/` & `_generated/indexes/` | Rebuilt deterministically with `source_digest` tamper protection |
| `memory/{_inbox,_ops,_claims}/` | *Retired* | Compact or discard pending v3 envelopes before migrating |

---

## 3. Data Semantic Conversions (Zero Fabricated Precision)

1. **Qualitative confidence (`high | medium | low`):**
   - v5.0 requires numeric `confidence` (`0.0..1.0`) or `null`.
   - Rather than inventing arbitrary numbers (such as turning `"high"` into `0.9`), `kf.py migrate` sets qualitative labels to `confidence: null` and emits an explicit curation **`signal`** listing the exact migrated facts so a Curator or Owner can calibrate numeric scores deliberately.
2. **Inclusive `valid_to` → Exclusive `valid_until`:**
   - Legacy inclusive `valid_to: YYYY-MM-DD` is converted to half-open exclusive `valid_until` (`valid_to + 1 day`), aligning all temporal intervals to `[valid_from, valid_until)`.
3. **Timestamps (`recorded_at`, `last_reviewed`):**
   - `observed_at` uses `observed_at`, falling back to `created_at` then `recorded_at`, normalized to UTC ISO-8601 (`...Z`).
   - `last_confirmed` uses `last_confirmed`, falling back to `last_reviewed` then the date of `observed_at`.

---

## 4. CLI Command Crosswalk

| v4.1 Command | v5.0 Unified `kf.py` Equivalent |
|---|---|
| `python3 tools/lint.py --strict` | `python3 tools/kf.py lint --strict` |
| `tools/rebuild-views.sh && tools/rebuild-indexes.sh` | `python3 tools/kf.py rebuild` |
| `tools/query.sh bootstrap` | `python3 tools/kf.py bootstrap [--profile executor\|curator]` |
| `tools/query.sh facts --entity X` | `python3 tools/kf.py query facts --entity X` |
| `tools/query.sh facts --why X Y` | `python3 tools/kf.py query why fact X Y` |
| `tools/query.sh resolve NAME` | `python3 tools/kf.py query resolve NAME` |
| `tools/query.sh search TERM` | `python3 tools/kf.py query search TERM` |
| `tools/query.sh graph entity X` | `python3 tools/kf.py query graph X` |
| `python3 tools/consolidate.py` | `python3 tools/kf.py curate scan --emit-signals` |
| `python3 tools/propose.py create ...` | `python3 tools/kf.py propose create ...` |
| `python3 tools/review.py approve ...` | `python3 tools/kf.py review approve ...` |
| `python3 tools/propose.py apply ...` | `python3 tools/kf.py publish --proposal-id ... --publisher ... --yes` |
| `python3 tools/transact.py ...` | `python3 tools/kf.py transact ...` (`owner` only) |
