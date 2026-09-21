# Goal: Ship v4.1 memory protocol

Implement the attached v4.1 improvement brief as an additive, offline,
Markdown/YAML + Git protocol. Preserve the v3 and v4 reference implementations.

## Acceptance

- Temporal history and as-of queries, lineage and trust enforcement.
- Deterministic aliases/search and a character-budgeted bootstrap.
- Staleness reports and idempotent, review-only consolidation proposals.
- JSON CLIs, concise agent instructions, and at least 15 offline evaluations.
- At least 100 regression tests; unchanged v3/v4 gates; v4.1 deterministic
  views/indexes, fallback parity, and CI enforcement.
- Complete spec, migration guide, version navigation, and completion record.

See `plan.md` for phases and `decisions.md` for compatibility resolutions.
