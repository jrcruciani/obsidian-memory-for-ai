# Documentation Map — Knowledge Factory v5.0

This repository defines **Obsidian Memory for AI v5.0: The Knowledge Factory Reboot**. Plain Markdown, YAML frontmatter, and Git remain the sole canonical state.

## Canonical Reading Paths

| Audience | Start With | Next |
|---|---|---|
| New user starting a v5.0 vault | [`../README.md`](../README.md) | [`../examples/v5-knowledge-factory/`](../examples/v5-knowledge-factory/), then [`executor-and-curator.md`](executor-and-curator.md) |
| Protocol implementer / auditor | [`../SPEC-v5.0.md`](../SPEC-v5.0.md) | [`architecture.md`](architecture.md), [`../tools/`](../tools/), [`../tests/eval/`](../tests/eval/) |
| v4.0 / v4.1 vault owner upgrading | [`migration-from-v4.1.md`](migration-from-v4.1.md) | [`archive/SPEC-v4.1.md`](archive/SPEC-v4.1.md) |
| Host-agent / skill integrator | [`integrations.md`](integrations.md) | [`anti-patterns.md`](anti-patterns.md) |
| Product & governance reviewer | [`open-decisions.md`](open-decisions.md) | [`architecture.md`](architecture.md) |

## Document Inventory

| Path | Status | Purpose |
|---|---|---|
| [`../SPEC-v5.0.md`](../SPEC-v5.0.md) | **Normative (v5.0)** | Complete v5.0 protocol contract, schemas, CLI, invariants, and gates |
| [`personal-mode.md`](personal-mode.md) | **Current (v5.1)** | Personal fast-track mode, BM25/FTS5+RRF hybrid search, OKF v0.2, sleep-pack & MCP server |
| [`architecture.md`](architecture.md) | Current | Manifesto, four-plane layout, challenged v4.1 decisions, retired legacy concepts |
| [`executor-and-curator.md`](executor-and-curator.md) | Current | Operating model for Executors, Curators, and Reviewers/Owners |
| [`migration-from-v4.1.md`](migration-from-v4.1.md) | Current | Breaking changes, crosswalk tables, and automated `kf.py migrate` guide |
| [`anti-patterns.md`](anti-patterns.md) | Current | Common failure modes in Markdown-backed AI knowledge systems |
| [`integrations.md`](integrations.md) | Current | Host-agent setup (Claude Code, Codex, Hermes, Cursor, Obsidian CLI, cron) |
| [`open-decisions.md`](open-decisions.md) | Current | Explicit open protocol/product trade-offs |
| [`archive/SPEC-v4.1.md`](archive/SPEC-v4.1.md) | Historical | Frozen v4.1 specification for migration reference |
| [`optional/`](optional/) | Optional | Non-protocol Obsidian CLI recipes, photo ingest, and sidecar experiments |
