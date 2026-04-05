# Obsidian Memory for AI

**Turn your Obsidian vault into persistent memory for any AI assistant.**

> **Version 2.0** — *The Compiled Wiki.* Incorporates lessons from daily use since March 2026, plus ideas from [Andrej Karpathy's LLM wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

---

## The problem

AI assistants forget everything between sessions. Every conversation starts from zero. If you have complex projects, a rich personal context, and specific preferences, you're stuck re-explaining yourself — or getting generic responses.

## The solution

A system of Markdown files inside your Obsidian vault that any AI can read at the start of a session. The AI doesn't just read your files — it **incrementally builds and maintains a persistent wiki** that gets richer with every session and every source you add.

**This is not the only correct way to do this.** It's a foundation — a pattern that emerged from daily use. Take what works, ignore what doesn't, build something better on top. There are many valid approaches to giving AI context; this one optimizes for transparency, portability, and human readability.

### Three layers

| Layer | What | Who owns it |
|-------|------|-------------|
| **Sources** (`sources/`) | Raw inputs: articles, clips, podcast notes, book highlights | You add them; the AI reads but never modifies |
| **Wiki** (`memory/`) | Structured knowledge: people, projects, decisions, insights, glossary | The AI writes and maintains; you read and direct |
| **Schema** (`CLAUDE.md`) | Identity, interaction rules, loading instructions | You and the AI co-evolve this over time |

### Four operations

| Operation | What it does |
|-----------|-------------|
| **Ingest** | Process a new source → extract entities, facts, concepts → update wiki pages |
| **Query** | Ask questions against the wiki → get answers → **file valuable insights back** as new pages |
| **Lint** | Health-check: contradictions, stale claims, orphan pages, missing cross-references, gaps |
| **Log** | Structured chronological record of all operations (`grep`-able) |

### Start simple

You don't need all of this on day one. Start with just `CLAUDE.md` and `TASKS.md`. Add `memory/` when you want persistence. Add `sources/` when you start ingesting external material. The system grows with you.

## See it in action

The [`examples/minimal-vault/`](examples/minimal-vault/) directory contains a complete working example — a fictional art conservator with research projects, collaborators, a glossary, a decision record, and sample sources. Copy the structure, replace the content with yours.

## Read the full guide

**[guide.md](guide.md)** covers architecture, every component in detail, the four operations, integration with different AI tools, the update protocol, and maintenance routines.

**[plugin-guide.md](plugin-guide.md)** explains how to package the system as a Cowork plugin with slash commands and auto-triggering skills for Claude Desktop.

**[automation-guide.md](automation-guide.md)** shows how to build standalone agents that maintain your memory files automatically — session-end updates, scheduled audits, consistency checks.

**[obsidian-cli.md](obsidian-cli.md)** shows how to use the Obsidian CLI (1.12+) for vault health audits, property sweeps, and quick capture from the terminal.

**[optional-ideas.md](optional-ideas.md)** has extras: horizon strip (visual task timeline), memory shortcut (query from your phone), pulse system (structured emotional check-in).

---

## Architecture

```
vault/
├── CLAUDE.md              ← Schema: identity, rules, loading instructions
├── COPILOT.md             ← Same content, for VS Code Copilot
├── TASKS.md               ← Active, recurring, upcoming, and someday tasks
│
├── sources/                    ← Layer 1: Raw inputs (immutable)
│   ├── articles/
│   ├── notes/
│   └── assets/
│
└── memory/                     ← Layer 2: The Wiki (LLM-maintained)
    ├── schema.md               ← Wiki operating manual: conventions, operations, formats
    ├── index.md                ← Content catalog: every page with summary and link
    ├── log.md                  ← Chronological operations log (parseable)
    ├── glossary.md             ← Acronyms, internal terms, nicknames
    ├── working-context.md      ← Mutable state: what matters right now
    ├── triggers.md             ← Keyword → file loading rules + proactive writing rules
    ├── modes.md                ← Interaction modes (research, writing, logistics...)
    ├── context/                ← Stable structural context
    │   ├── company.md
    │   └── personality.md
    ├── people/                 ← One .md per relevant person
    ├── projects/               ← One .md per active project
    ├── decisions/              ← Durable decisions and their rationale
    ├── insights/               ← Filed-back conversation knowledge
    └── pulse/                  ← Structured emotional check-in (optional)
```

---

## Why plain Markdown instead of a vector database

This is the question I get asked most. The short answer: because the trade-offs favor Markdown for this use case, and the things you give up don't matter as much as they seem.

### What you get

- **Full transparency.** Every piece of context is a file you can read, edit, and version-control. There is no black box deciding what the AI "remembers." When the AI says something wrong, you open the file and fix it.
- **Zero infrastructure.** No database to host, no embeddings to recompute, no server to keep running. The system works on a plane with no internet.
- **Portability across AI tools.** The same Markdown files work with Claude Code, Copilot, ChatGPT, Cursor, or any tool that can read text. A vector database locks you into whatever retrieval API it exposes.
- **Human-readable memory.** Your vault is your second brain *first*, and the AI's memory *second*. You browse it, link it, search it, think with it. A vector store is opaque to you.
- **Version control.** `git log` shows you exactly what changed, when, and why. Try that with embeddings.
- **Composable loading.** The `index.md` catalog and `triggers.md` rules let you control exactly what the AI reads and in what order. You're the retrieval algorithm, and you're smarter than cosine similarity at knowing what's relevant to your session.

### What you give up

- **Semantic search over large corpora.** If you have 10,000 notes and need to find "that thing about Byzantine trade routes" without knowing where it is, a vector database will find it faster. This system relies on explicit structure (index, glossary, wikilinks) instead of embeddings. At vault sizes under ~500 notes, grep and good organization are faster than any retrieval pipeline. For larger vaults, consider [qmd](https://github.com/tobi/qmd) for local hybrid search.
- **Automatic relevance scoring.** Vector databases rank results by similarity. Here, you mark relevance manually (`high`/`medium`/`low` in frontmatter) and maintain it through periodic reviews. This is more work. It's also more accurate, because *you* know what's relevant better than an embedding model does.
- **Automatic memory decay.** Systems like [Chetna](https://github.com/vineetkishore01/Chetna) implement Ebbinghaus-style decay curves in code. Here, decay is manual: you review `last_reviewed` dates and downgrade or archive stale entries. Treat `last_reviewed` as the date of **semantic validation**, not as a batch-audit stamp.
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

The formalized trigger tables (keyword → file + action) and explicit interaction modes were inspired by [**Open-Her OS**](https://github.com/kitfoxs/open-her-os), an open-source AI companion framework by Kit & Ada Marie. Open-Her OS uses a *lorebook* (character book) with keyword-activated behavioral entries and *companion modes* that modulate AI behavior contextually. This project adapts both concepts as Markdown tables — `triggers.md` for reactive file loading and proactive memory writing, and `modes.md` for explicit tone and priority calibration across different session types.

The three-layer architecture (sources → wiki → schema), the four operations model (ingest, query, lint, log), and the practice of filing conversation insights back into the wiki as persistent pages were inspired by [**Andrej Karpathy**](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)'s pattern for building personal knowledge bases using LLMs (April 2026). Karpathy articulated that the key insight is making the wiki a *compounding artifact* — where the LLM handles the tedious bookkeeping (cross-referencing, maintaining consistency, noting contradictions) so the human can focus on sourcing, exploration, and asking the right questions.

---

*Developed through daily use with Claude Code and GitHub Copilot. March–April 2026.*
