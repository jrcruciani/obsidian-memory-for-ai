# Obsidian Memory for AI

**Turn your Obsidian vault into persistent memory for any AI assistant.**

---

## The problem

AI assistants forget everything between sessions. Every conversation starts from zero. If you have complex projects, a rich personal context, and specific preferences, you're stuck re-explaining yourself — or getting generic responses.

## The solution

A system of Markdown files inside your Obsidian vault that any AI can read at the start of a session. No plugins, no vendor lock-in, no proprietary formats. Just plain text that makes your AI *know you*.

The full system uses five components that you build incrementally:

| Component | Purpose |
|-----------|---------|
| **Master document** (`CLAUDE.md`) | Tier 0 pointer: identity basics, interaction rules, and loading instructions — not the full memory |
| **Memory folder** (`memory/`) | Structured files for people, projects, glossary, decisions, professional context |
| **Context summaries** | Semantic index per folder so the AI navigates without reading everything |
| **Task list** (`TASKS.md`) | Time-horizoned tasks the AI can query and update |
| **Wikilinks & typed relationships** | `[[wikilinks]]` with verbs (`extends`, `supports`, `contradicts`…) that create a navigable knowledge graph |

Start with just `CLAUDE.md` and `TASKS.md`. Add the rest as you need it.

**Keep `CLAUDE.md` / `COPILOT.md` lean.** Treat them as Tier 0 routers, not warehouses. Detailed people/project context belongs in `memory/` and should load on demand through `ContextSummary.md`, the glossary, and related notes.

## See it in action

The [`examples/minimal-vault/`](examples/minimal-vault/) directory contains a complete working example — a fictional art conservator with research projects, collaborators, a glossary, and a decision record. Copy the structure, replace the content with yours.

## Read the full guide

**[guide.md](guide.md)** covers architecture, every component in detail, integration with different AI tools, the update protocol, and maintenance routines.

**[plugin-guide.md](plugin-guide.md)** explains how to package the system as a Cowork plugin with slash commands and auto-triggering skills for Claude Desktop.

**[automation-guide.md](automation-guide.md)** shows how to build standalone agents (using the Anthropic API or GitHub Copilot SDK) that maintain your memory files automatically — session-end updates, scheduled audits, consistency checks — without needing an open chat session.

**[obsidian-cli.md](obsidian-cli.md)** shows how to use the Obsidian CLI (1.12+) for vault health audits, property sweeps, and quick capture from the terminal — no AI context needed.

---

## Why plain Markdown instead of a vector database

This is the question I get asked most. The short answer: because the trade-offs favor Markdown for this use case, and the things you give up don't matter as much as they seem.

### What you get

- **Full transparency.** Every piece of context is a file you can read, edit, and version-control. There is no black box deciding what the AI "remembers." When the AI says something wrong, you open the file and fix it.
- **Zero infrastructure.** No database to host, no embeddings to recompute, no server to keep running. The system works on a plane with no internet.
- **Portability across AI tools.** The same Markdown files work with Claude Code, Copilot, ChatGPT, Cursor, or any tool that can read text. A vector database locks you into whatever retrieval API it exposes.
- **Human-readable memory.** Your vault is your second brain *first*, and the AI's memory *second*. You browse it, link it, search it, think with it. A vector store is opaque to you.
- **Version control.** `git log` shows you exactly what changed, when, and why. Try that with embeddings.
- **Composable loading.** The `ContextSummary.md` router pattern lets you control exactly what the AI reads and in what order. You're the retrieval algorithm, and you're smarter than cosine similarity at knowing what's relevant to your session.

### What you give up

- **Semantic search over large corpora.** If you have 10,000 notes and need to find "that thing about Byzantine trade routes" without knowing where it is, a vector database will find it faster. This system relies on explicit structure (summaries, glossary, wikilinks) instead of embeddings. At vault sizes under ~500 notes, grep and good organization are faster than any retrieval pipeline.
- **Automatic relevance scoring.** Vector databases rank results by similarity. Here, you mark relevance manually (`high`/`medium`/`low` in frontmatter) and maintain it through periodic reviews. This is more work. It's also more accurate, because *you* know what's relevant better than an embedding model does.
- **Automatic memory decay.** Systems like [Chetna](https://github.com/vineetkishore01/Chetna) implement Ebbinghaus-style decay curves in code. Here, decay is manual: you review `last_reviewed` dates and downgrade or archive stale entries. Treat `last_reviewed` as the date of **semantic validation**, not as a batch-audit stamp. The guide includes explicit maintenance cadences (post-session, monthly, quarterly) to keep this sustainable.
- **Scaling past thousands of files.** This system is designed for personal context — the 50–500 files that define who you are, what you're working on, and how you think. It's not a replacement for a RAG pipeline over your company's entire knowledge base. It's the *personal layer* that sits on top of whatever else you use.

### When to use what

| Scenario | This system | Vector DB / RAG |
|----------|-------------|-----------------|
| Personal context (identity, preferences, projects) | Yes | Overkill |
| Active project memory (people, decisions, tasks) | Yes | Overkill |
| Searching 10,000+ documents by semantic meaning | No | Yes |
| Multi-user shared knowledge base | No | Yes |
| Context that must be human-readable and editable | Yes | Difficult |
| Context that must survive across different AI tools | Yes | Vendor-dependent |

The honest take: if you're already running a RAG pipeline for other reasons, this system complements it — it handles the personal, curated context that RAG is bad at. They're not competing solutions; they operate at different layers.

---

## Compatible tools

| Tool | How it works |
|------|-------------|
| Claude Code (CLI) | Native — reads `CLAUDE.md` automatically from working directory + `~/.claude/CLAUDE.md` globally |
| Claude Desktop (Cowork) | Via plugin — see [plugin-guide.md](plugin-guide.md) |
| VS Code + GitHub Copilot | `COPILOT.md` as workspace context, with the same Tier 0 semantics as `CLAUDE.md` |
| Obsidian CLI (1.12+) | Native vault commands for auditing, property management, and quick capture — see [obsidian-cli.md](obsidian-cli.md) |
| Claude.ai / ChatGPT | Paste or attach at session start |
| Cursor | `.cursorrules` or context files |
| Any AI with file access | Attach the relevant `.md` files |
| Standalone agent (API/SDK) | Automated maintenance — see [automation-guide.md](automation-guide.md) |

## Acknowledgments

The memory classification system (type tagging, relevance scoring, and relationship types between memories) was inspired by [**Chetna**](https://github.com/vineetkishore01/Chetna), a Rust-based memory system for AI agents by [@vineetkishore01](https://github.com/vineetkishore01). Chetna implements these concepts as code — importance scoring, Ebbinghaus decay curves, typed relationships in a database. This project adapts the same ideas as pure Markdown conventions.

The memory hierarchy model, working context block, rolling session summaries, memory pressure protocol, and proactive update triggers were inspired by [**MemGPT**](https://research.memgpt.ai) (Packer et al., 2023), which demonstrated that LLMs benefit from OS-style tiered memory management — paging information between a small working context and larger archival storage. This project translates those patterns from code and databases into plain Markdown files and loading conventions.

---

*Developed through daily use with Claude Code. March 2026.*
