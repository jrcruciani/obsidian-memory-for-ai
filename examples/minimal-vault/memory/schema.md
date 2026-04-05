---
title: "Schema"
type: rule
relevance: high
last_reviewed: 2026-03-20
---
# Schema — wiki operating manual

How this memory wiki operates. The AI reads this for conventions and workflows.

## Architecture

Three layers:
1. **Sources** (`sources/`) — Immutable raw inputs. AI reads but never modifies.
2. **Wiki** (`memory/`) — LLM-maintained knowledge. AI creates, updates, cross-references.
3. **Schema** (`CLAUDE.md`) — Loading instructions and identity. Tier 0 router.

## Memory hierarchy

| Tier | Content | When loaded |
|------|---------|-------------|
| 0 — Prompt | CLAUDE.md | Always, auto |
| 1 — Working memory | glossary, company, personality, working-context | Session start |
| 1.5 — Reactive | triggers, modes | On demand |
| 2 — Reference | people/, projects/, decisions/, insights/, log | When topic requires |

## Operations

### Ingest
Process new sources into wiki pages. Read source → discuss → create/update pages → update index + log.

### Query + File-back
Ask questions. Good answers → propose as insight pages. At session end: "Any insight worth filing?"

### Lint
Health-check: contradictions, stale claims, orphans, missing cross-refs, concept gaps.

### Log
Append to `log.md`: `## [YYYY-MM-DD] operation | topic`

## Page format

All pages need frontmatter:
```yaml
---
type: fact | preference | rule | project | person | decision | insight
relevance: high | medium | low
last_reviewed: YYYY-MM-DD
---
```

## Session lifecycle

1. Load Tier 1 files
2. Read index.md for navigation
3. Work (loading Tier 2 as needed via triggers)
4. At end: ask about insights, update working-context, append to log

## Maintenance

- Post-session: update affected notes, index, log
- Monthly: review staleness, consolidate, lint
- Quarterly: structural review
