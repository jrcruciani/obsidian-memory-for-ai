# Obsidian Memory for AI

**Turn your Obsidian vault into persistent memory for any AI assistant.**

---

## The problem

AI assistants forget everything between sessions. Every conversation starts from zero. If you have complex projects, a rich personal context, and specific preferences, you're stuck re-explaining yourself — or getting generic responses.

## The solution

A simple system of Markdown files inside your Obsidian vault that any AI can read at the start of a session. No plugins required, no vendor lock-in, no proprietary formats. Just plain text that makes your AI *know you*.

## What's in the guide

The full guide ([guide.md](guide.md)) covers:

| Component | What it does |
|-----------|-------------|
| **Master document** (`CLAUDE.md`) | Your identity, projects, preferences, and interaction rules — loaded automatically by Claude Code, pasteable into any AI |
| **Memory folder** (`memory/`) | Structured files for people, projects, glossary, and professional context |
| **Context summaries** (`ContextSummary.md`) | Semantic index per folder so the AI doesn't need to read every file |
| **Task list** (`TASKS.md`) | Time-horizoned tasks the AI can query and update |
| **Wikilinks & graph** | `[[wikilinks]]` with typed relationships (`extends`, `supports`, `contradicts`…) create a navigable knowledge graph — and you can ask the AI to build it for you |
| **Memory classification** | Each memory file is tagged by type (`fact`, `preference`, `rule`, `project`, `person`) and relevance (`high`, `medium`, `low`) for prioritization and decay |
| **Update protocol** | Instructions so the AI co-maintains the system at the end of each session |
| **Security guidelines** | What to keep out of the system and why |

## Quick start

1. Create a `CLAUDE.md` in your vault root with who you are, your projects, and how you want to be addressed
2. Add a `TASKS.md` with your current priorities
3. Create `memory/glossary.md` with your internal vocabulary
4. Point the AI to these files at the start of each session
5. At the end of each session, ask: *"Update the relevant memory files with what we did today"*

That's it. The system grows organically from there.

## Compatible with

| Tool | Integration |
|------|------------|
| Claude Code (CLI) | Native — reads `CLAUDE.md` automatically |
| VS Code + GitHub Copilot | `COPILOT.md` as workspace context |
| Claude.ai / ChatGPT | Paste or attach at session start |
| Cursor | `.cursorrules` or context files |
| Any AI with file access | Attach the relevant `.md` files |

## Why Obsidian

- **Plain Markdown** — no lock-in, works in any editor
- **Syncs everywhere** — iCloud, Syncthing, whatever you trust
- **Human-readable** — it's your second brain, not just the AI's
- **Graph view** — visualize the connections between your notes
- **No build step, no dependencies** — just files in folders

## Read the full guide

👉 **[guide.md](guide.md)**

## Acknowledgments

The memory classification system (type tagging, relevance scoring, and relationship types between memories) was inspired by [**Chetna**](https://github.com/vineetkishore01/Chetna), a Rust-based memory system for AI agents by [@vineetkishore01](https://github.com/vineetkishore01). Chetna implements these concepts as code (importance scoring, Ebbinghaus decay curves, typed memory relationships in a database). This project adapts the same ideas as pure Markdown conventions — no code required.

---

*Developed through real-world daily use with Claude Code. March 2026.*
