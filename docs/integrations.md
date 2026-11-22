# Host-Agent & Obsidian Integrations (v5.0)

`tools/kf.py` is intentionally host-agnostic: any assistant or local script that can read files and invoke Python 3 can participate in a Knowledge Factory vault without an MCP server or background daemon.

---

## 1. Coding & Research Agents (Claude Code, Codex, Hermes, Cursor)

Point your agent workspace at the vault root (where `AGENTS.md` and `CLAUDE.md` reside) or pass `--vault /path/to/vault` from another repository:

```bash
# Session start for an Executor agent
python3 /path/to/vault/tools/kf.py --vault /path/to/vault bootstrap --profile executor

# Targeted procedural & factual lookup
python3 /path/to/vault/tools/kf.py --vault /path/to/vault query skills --trigger "deploy"
python3 /path/to/vault/tools/kf.py --vault /path/to/vault query guidance --scope executor

# Mid-task gap capture
python3 /path/to/vault/tools/kf.py --vault /path/to/vault capture signal \
  --emitted-by agent-executor-00000004 \
  --kind gap --severity medium --target-namespace skills \
  --summary "Document exact staging verification command"
```

## 2. Packaging Reusable Host Commands / Skills

| Slash Command | Underlying `kf.py` Workflow |
|---|---|
| `/kf-load` | `kf.py bootstrap --profile executor` + targeted `kf.py query` |
| `/kf-capture` | `kf.py capture signal` or `kf.py capture event` |
| `/kf-curate` | `kf.py bootstrap --profile curator` + `kf.py curate scan --emit-signals` + `kf.py propose create` |
| `/kf-review` | `kf.py propose show` + `kf.py review approve\|reject\|request-changes` + `kf.py publish --yes --rebuild` |
| `/kf-audit` | `kf.py lint --strict --stale` |

## 3. Scheduled Offline Curation (Cron / systemd timer / launchd)

Schedule a read-and-flag check that never mutates canonical `knowledge/`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd ~/Vaults/MyKnowledgeFactory
python3 tools/kf.py curate scan --emit-signals --emitted-by agent-curator-00000003
python3 tools/kf.py rebuild
python3 tools/kf.py lint --strict
```

Review newly emitted signals in Obsidian via `_generated/views/factory-queue.md`.

## 4. Obsidian Desktop Experience

- **Graph & Backlinks:** Wikilinks across `knowledge/notes/`, `knowledge/facts/`, `knowledge/skills/`, and `knowledge/decisions/` render natively in Obsidian's Graph View.
- **Properties:** Every record uses standard YAML frontmatter compatible with Obsidian Properties; avoid editing `_generated/` or canonical frontmatter directly without running `python3 tools/kf.py lint --strict`.
- **Optional recipes:** See [`optional/obsidian-cli.md`](optional/obsidian-cli.md), [`optional/photo-ingest-guide.md`](optional/photo-ingest-guide.md), and [`optional/optional-ideas.md`](optional/optional-ideas.md) for non-protocol extensions.
