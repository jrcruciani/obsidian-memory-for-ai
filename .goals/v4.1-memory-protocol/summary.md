# Completion record

Completed: all seven mandatory work items. The only deferred item is the
explicitly optional LongMemEval adapter. Baseline was 62 passing tests.

Phase 1 creates a separate v4.1 reference and spec without changing the
supported older implementations.

Phase 2 adds temporal supersession, lineage, trust policy, historical queries,
and timelines. The reference demonstrates Elena's July 15 role transition.
33 new tests cover these features and legacy lint compatibility.

The copied v4 transaction implementation could not restore overwritten facts
after a partial failure. The v4.1 transaction path now persists preimages and
publication progress, validates a candidate vault, and recovers interruptions.
Proposal application and two-file review writes use this same transaction path.
Apply rechecks real, authorized, content-bound reviews rather than trusting an
editable approval list. These fixes are necessary for safe supersession and
external-data review, not changes to the preserved v4 implementation.

Phase 3 adds accent-folded entity resolution, alias/value/body ranking, explicit
stale-index diagnostics, and canonical query parity (including empty results).
Bootstrap counts every character, including headings and its self-counting
footer. Exact-limit and one-character-over-limit tests verify the real output
budget. There are now 52 v4.1 tests (114 total).

Phase 4 implements all four consolidation detections, including newer
structured event assertions. Each issue emits exactly one idempotent draft,
with no guessed operations and no canonical edits. Stale reporting and views
share a configurable semantic-age policy. Legacy inbox compaction on a v4.1
vault now routes through transactions and cannot bypass external-data review.
67 v4.1 tests cover this phase (129 total); the clean vault produces no drafts.

Phase 5 adds structured JSON on all CLIs, including parse/error paths,
bootstrap-first AGENTS guidance, and 20 exact offline query evaluations.
CI now enforces v4.1 strict lint, two rebuilds with drift checks, and evaluations
alongside the unchanged older-version gates. 81 v4.1 tests (143 total) include
a deliberately wrong-answer fixture proving the evaluation gate fails.

The preserved v4 vault receives only an `AGENTS.md` navigation/protocol note;
its tools, canonical records, generated files, and quality gates are unchanged.

## Final acceptance evidence

| Requirement | Result |
|---|---|
| Temporal supersession and lineage/trust | Implemented and demonstrated in the reference vault |
| Aliases, ranked retrieval, budgeted bootstrap | Implemented with missing/stale/corrupt artifact parity |
| Staleness and all four consolidation detections | Implemented; planted fixtures emit one idempotent draft each |
| JSON and agent ergonomics | All CLIs supported, including error paths and review |
| Unit tests | 152 pass on Python 3.11 (90 v4.1 plus 62 preserved tests) |
| Offline evaluations | 21/21 pass; a wrong-answer fixture proves failure detection |
| Generated artifacts | 18 files byte-identical over two consecutive rebuilds and deletion/rebuild tests |
| Bootstrap budget | 966/6000 characters, including its footer |
| Clean-vault consolidation | No drafts |
| v3/v4 regression gates | Pass; original tools/data/views unchanged |
| Protocol exclusions | No prohibited infrastructure/network imports in v4.1 tools |
| Documentation | Spec, migration, changelog, navigation, plugin/agent guidance, privacy caveat complete |

Final checks also cover marker-only migration with retained v4 schemas,
proposal supersession, stale review preconditions, commit-time trust checks,
retraction visibility, staging exclusion, and corrupted-bootstrap fallback.
The new external equipment claim has an immutable source, an independent
review, an applied proposal, and a transaction receipt.

CI retains the old gates and adds strict v4.1 lint, repeated deterministic
rebuild/drift checks, and the offline evaluations. Runtime tools require only
Python 3 + PyYAML. Git integration remains optional.
