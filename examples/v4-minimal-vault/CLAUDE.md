# Context for AI sessions

## Who I am
- **Name:** Elena Voss
- **Role:** Art conservator and pigment researcher
- **Base:** Berlin, Germany

## Active projects
- **Concordance** — mapping historical pigment recipes to modern spectroscopic signatures.
- **Gallery 5 survey** — condition survey of Cranach panels at the Gemäldegalerie.

## v4 memory protocol
- Human-readable narrative lives in `memory/people/`, `memory/projects/`, and `memory/context/`.
- Agent-readable facts live in `memory/facts/` and must pass `tools/lint.py`.
- New session records live in `memory/events/YYYY-MM-DD/`.
- **Transactions:** multi-op writes use `tools/transact.py begin/add/commit` for atomicity and idempotency.
- **Proposals:** formal review-gated changes use `tools/propose.py create` and `tools/review.py approve/reject`.
- Roles and namespace policy live in `memory/schema/roles.yaml`.
- Lexical and graph indexes in `memory/_indexes/` are derived — delete and rebuild at any time.
- Generated views in `memory/_views/` are derived — never edit them directly.

## Update protocol
1. For single-fact changes: use `tools/transact.py` with an idempotency key.
2. For changes requiring review: use `tools/propose.py` and `tools/review.py`.
3. Add append-only events for session-level history.
4. Run `tools/lint.py` then `tools/rebuild-views.sh` and `tools/rebuild-indexes.sh` before committing.
