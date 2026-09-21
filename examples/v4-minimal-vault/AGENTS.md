# Agent memory protocol (preserved v4.0)

This vault deliberately retains v4.0 tooling and data. For bootstrap-first
loading, temporal history, lineage/trust, and the extraction prompt, use the
[v4.1 agent instructions](../v4.1-minimal-vault/AGENTS.md) after upgrading.

Read `CLAUDE.md` and relevant `_views/by-entity/` pages, then query before
asserting. Write through `transact.py` with an idempotency key, or through
`propose.py` and a different authorized reviewer via `review.py`.
Never hand-edit generated `_views/` or `_indexes/`; never rewrite existing
events or sources. Run lint and rebuild views/indexes before committing.
