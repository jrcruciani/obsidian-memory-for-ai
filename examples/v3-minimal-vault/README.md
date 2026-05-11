# Example: v3 Minimal Vault

This example implements the draft **SPEC v3 — Atomic Markdown Memory** as a small, portable vault. It keeps the v2 idea of human-readable Markdown, but separates human prose from agent-facing records:

- `memory/facts/` — atomic semantic facts, one tuple per file.
- `memory/events/` — append-only episodic records.
- `memory/_views/` — generated materialized views committed for auditability in this example.
- `memory/_inbox/` — cooperative agent staging area.
- `tools/` — portable validation, query, reflection, and compaction scripts that travel with the vault.

The original `examples/minimal-vault/` remains the v2 reference. This directory is the v3 reference.

## Quick start

```bash
cd examples/v3-minimal-vault
python3 tools/lint.py
tools/rebuild-views.sh
tools/query.sh facts --entity elena-voss
tools/query.sh events --since 2026-03-01
```

The scripts require Python 3.11+ and PyYAML:

```bash
python3 -m pip install PyYAML
```

## Rules implemented here

### Facts and filenames

The canonical active fact path is:

```text
memory/facts/{entity}/{predicate}.md
```

Historical or superseded facts may use a suffix:

```text
memory/facts/{entity}/{predicate}--{slug}.md
```

The frontmatter `entity` and `predicate` are authoritative, but the path must match them. A suffix is allowed only after `--`. Predicates are controlled by `memory/schema/predicates.yaml`.

### Temporal semantics

- `valid_from` and `valid_to` are inclusive dates.
- `valid_to: null` means open-ended.
- `valid_from: null` means unknown start.
- Overlapping facts for the same `(entity, predicate)` with different values are contradictions unless one points at the other via `superseded_by`.

### Entity policy

Every referenced entity must appear in `memory/entities.md`. This is strict because typos in entity IDs silently split memory.

### Generated views

Generated files under `memory/_views/` are committed in this example so diffs show derived-state changes. In a private vault, you may ignore `_views/` and regenerate them locally.

For deterministic stale calculations, scripts use `MEMORY_TODAY` when set:

```bash
MEMORY_TODAY=2026-05-11 tools/rebuild-views.sh
```

### Wikilink subset

The linter supports these wikilink forms:

- `[[memory/facts/elena-voss/timezone]]`
- `[[memory/projects/concordance|Concordance]]`
- `[[concordance]]` when the basename is unique
- `[[memory/projects/concordance#Current status]]`

Ambiguous basenames are reported as errors.

## Anthropic Memory Tool mapping

The v3 `memory/` folder maps cleanly to Anthropic's `/memories` directory:

| v3 path | Memory Tool meaning |
|---------|---------------------|
| `memory/facts/` | Canonical semantic memories |
| `memory/events/` | Append-only episodic memories |
| `memory/decisions/` | Durable decisions with rationale |
| `memory/insights/` | Reflections and learned patterns |
| `memory/_views/` | Generated read models; do not edit as source |
| `memory/_inbox/` | Proposed writes from agents; compact before treating as canonical |
| `memory/_archive/` | Expired historical facts |

If a tool points directly at `memory/`, configure it to treat `_views/`, `_inbox/`, and `_archive/` as special-purpose folders rather than primary sources.

## Reflection ritual

`tools/reflect.py` is intentionally conservative. It does not call an LLM and does not merge into canonical memory. It accepts a short session summary and writes a proposed `event` into `memory/_inbox/{agent-id}/`:

```bash
tools/reflect.py --agent copilot --summary "Reviewed SPEC v3 and agreed to controlled predicates."
tools/compact.sh
```

Run `tools/compact.sh` to review inbox entries and move safe records into canonical memory.

