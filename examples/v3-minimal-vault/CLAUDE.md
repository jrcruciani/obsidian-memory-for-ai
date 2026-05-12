# Context for AI sessions

## Who I am
- **Name:** Elena Voss
- **Role:** Art conservator and pigment researcher
- **Base:** Berlin, Germany

## Active projects
- **Concordance** — mapping historical pigment recipes to modern spectroscopic signatures.
- **Gallery 5 survey** — condition survey of Cranach panels at the Gemäldegalerie.

## v3 memory protocol
- Human-readable narrative lives in `memory/people/`, `memory/projects/`, and `memory/context/`.
- Agent-readable facts live in `memory/facts/` and must pass `tools/lint.py`.
- New session records live in `memory/events/YYYY-MM-DD/`.
- Proposed agent writes should be operation envelopes in `memory/_inbox/{agent-id}/ops/` and are compacted later.
- Cooperative claims live in `memory/_claims/`; treat them as advisory, not transactional locks.
- Read generated context from `memory/_views/` when available, but never edit `_views/` directly.

## Update protocol
1. Add or update atomic facts in `memory/facts/` only when the fact is durable and sourced.
2. Add append-only events for session-level history.
3. Use `tools/ops.py` for proposed facts/claims, `tools/reflect.py` for proposed reflections, and `tools/compact.sh` for review.
4. Run `python3 tools/lint.py` and `tools/rebuild-views.sh` before committing.
