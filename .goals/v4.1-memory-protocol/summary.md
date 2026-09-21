# Completion record

Implementation in progress. Baseline: 62 tests pass; v3 and v4 lint, views,
indexes, and tracked-artifact drift gates are green.

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
