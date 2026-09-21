# Goal: Ship v4.1 memory protocol

Implement the attached v4.1 improvement brief as an additive, offline,
Markdown/YAML + Git protocol. Preserve the v3 and v4 reference implementations.

## Acceptance

- [x] Temporal history and as-of queries, lineage and trust enforcement.
- [x] Deterministic aliases/search and a character-budgeted bootstrap.
- [x] Staleness reports and idempotent, review-only consolidation proposals.
- [x] JSON CLIs, concise agent instructions, and at least 15 offline evaluations.
- [x] At least 100 regression tests; unchanged v3/v4 gates; v4.1 deterministic
  views/indexes, fallback parity, and CI enforcement.
- [x] Complete spec, migration guide, version navigation, and completion record.

See `plan.md` for phases and `decisions.md` for compatibility resolutions.
