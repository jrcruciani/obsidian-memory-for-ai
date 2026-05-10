# Obsidian Memory for AI

**Turn your Obsidian vault into persistent memory for any AI assistant.**

> **Version 2.1** — *The Compiled Wiki, situated.* Adds [State of the art (May 2026)](#state-of-the-art--may-2026) and [Honest limits](#honest-limits) sections to position this pattern within the now-crowded agent-memory landscape (Mem0, Zep, Letta, Cognee, Cloudflare Agent Memory, Anthropic Memory Tool, Obsidian Agent Skills). The architecture is unchanged — v2.0 already encoded what 2026 standardized.
>
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

**[photo-ingest-guide.md](photo-ingest-guide.md)** extends the Ingest operation for photography workflows — use multimodal AI to analyze your photo sessions, select the best shots, get specific editing recommendations, and improve your composition. Works with any RAW+JPEG camera.

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

## State of the art — May 2026

This repository was first published in early 2026, when "AI agent memory" was a research topic. Twelve months later it's an infrastructure category with venture funding, benchmarks, and a managed-service tier. This section maps where this pattern sits within that landscape, and which of the new ideas are worth borrowing.

### What 2026 standardized (and where this repo already was)

The three-layer split here (sources / wiki / schema) maps cleanly onto the **CoALA framework** (Sumers, Yao et al., *Cognitive Architectures for Language Agents*) which became the dominant reference vocabulary in 2026, and onto **Tulving's 1972 taxonomy** that CoALA builds on:

| This repo | CoALA / Tulving | What 2026 calls it |
|---|---|---|
| `memory/` (people, projects, decisions) | Semantic | "Facts" memory (Mem0, Cloudflare) |
| `memory/log.md` + `memory/insights/` | Episodic | "Events" memory (Cloudflare); "episodes" (Zep) |
| `CLAUDE.md` + `memory/schema.md` + `memory/triggers.md` | Procedural | "Instructions" memory (Cloudflare); "Skills" (Anthropic / Obsidian) |
| `sources/` | External / immutable | Document store; the input side of any RAG layer |

The four operations (`Ingest` / `Query` / `Lint` / `Log`) anticipated what **Cloudflare Agent Memory** (private beta, April 2026) shipped as a formal API: `ingest` / `remember` / `recall` / `forget` / `list`. The "file insights back" practice is what **Lance Martin's Claude Diary** (`/diary` + `/reflect`) and **Jesse Vincent's fsck.com episodic memory** turned into a named pattern: *reflect-after-session*.

### The 2026 landscape

| System | Architecture | License | Best for |
|---|---|---|---|
| **[Mem0](https://github.com/mem0ai/mem0)** | Vector + graph + KV; passive extraction | Apache 2.0 / managed | Personalization, returning end-users; chosen as exclusive memory provider for the AWS Agent SDK |
| **[Zep / Graphiti](https://github.com/getzep/graphiti)** | Bi-temporal knowledge graph | Open source / managed | Entity changes over time; "who owned X in March" queries |
| **[Letta](https://github.com/letta-ai/letta)** (formerly MemGPT) | Tiered RAM/disk; agent-managed | Apache 2.0 / managed | Long-horizon coding/research agents; multi-week sessions |
| **[Cognee](https://github.com/topoteretes/cognee)** | Vector + KG built from documents | Open core | Unstructured document ingestion |
| **Cloudflare Agent Memory** | Typed (Facts / Events / Instructions / Tasks) | Managed only (private beta, Apr 2026) | Teams already on Cloudflare Workers / Durable Objects |
| **[Anthropic Memory Tool](https://docs.claude.com/en/docs/agents-and-tools/tool-use/memory-tool)** | Client-side `/memories` directory; view/create/str_replace/insert/delete | Beta (`context-management-2025-06-27`) | Drop-in for any Claude-based agent; **+39% on agentic search, −84% tokens in 100-turn evals** |
| **[Obsidian Agent Skills](https://github.com/obsidianmd/obsidian-skills)** (Steph Ango, Jan 2026) | Markdown skill files Claude reads natively | Open source | Teaching agents to handle Obsidian's specific file conventions |
| **This repository** | Plain Markdown vault, conventions over code | MIT | Personal context (50–500 files), full ownership, copy-paste portability across providers |

A few benchmark numbers worth knowing when this question comes up:

- **Letta's filesystem benchmark: 74.0% on LoCoMo** by storing conversations as plain files — beating several specialized vector-store libraries. The naive markdown approach is not as naive as it sounds, and there is now empirical cover for it.
- **Mem0**: 66.9% LoCoMo at 0.71s with ~1.8K tokens/conversation, vs. full-context baseline at 72.9%, 9.87s, ~26K tokens. Roughly 14× cheaper for ~6 points of accuracy.
- **Zep / Graphiti**: 63.8% on LongMemEval (the strongest temporal score), 94.8% on DMR. Pays for itself when entities change over time; less interesting for static personal context.
- **Anthropic Memory Tool**: the headline numbers above (+39% / −84%) are from Anthropic's own evals; replicate before believing, but the direction matches everything else in the field.

### What's genuinely worth borrowing

If you're running this system today, four ideas from the 2026 wave are worth folding in without changing the architecture:

1. **Reflect-after-session as a named ritual.** Lance Martin's `/diary` + `/reflect` pattern formalizes what `log.md` + `memory/insights/` already does, but adds a discipline: a multi-diary review that only promotes a pattern to `CLAUDE.md` when it appears 2+ times (3+ for "strong"). This guards against single-session overfitting. Worth adopting verbatim.
2. **Bi-temporal frontmatter.** Zep's bi-temporal model (a fact has both `valid_from`/`valid_to` *and* `recorded_at`) is implementable as YAML frontmatter without changing anything else. It makes "what did I believe in March" answerable.
3. **Anthropic Memory Tool as a runtime.** If you use Claude, the `/memories` directory the Memory Tool exposes can be pointed at this vault's `memory/` folder. You get the file-level tool (view / create / str_replace / insert / delete / rename) for free, with the +39% / −84% numbers above. This vault becomes the *content*; the Memory Tool becomes the *interface*.
4. **Obsidian Agent Skills (Ango).** The official skill specs published by Obsidian's CEO in January 2026 are the right way to teach Claude / Copilot how to handle Obsidian's specific conventions (frontmatter, wikilinks, dataview blocks). Pair these skills with this vault — they solve different problems and compose cleanly.

### What this repo deliberately does *not* do

After watching twelve months of the field, the trade-offs in [Why plain Markdown instead of a vector database](#why-plain-markdown-instead-of-a-vector-database) still hold. This system is **not** trying to be Mem0, Zep, or Letta. Their job is *agent memory as managed infrastructure*; this system's job is *your memory, in files you own, that any agent can read*. Those are different problems. The honest comparison is below.

---

## Honest limits

A pointed critique of the broader "AI + Obsidian = second brain" trend appeared in [Limited Edition Jonathan, *Stop Calling It Memory*](https://limitededitionjonathan.substack.com/p/stop-calling-it-memory-the-problem) (March 2026). It's worth reading. Most of it lands. The rest of this section addresses each criticism directly, both to mark where this system genuinely breaks and to make the case for why — within those limits — it remains the right tool for the job it was designed for.

| Criticism | Where it lands | How this system holds up |
|---|---|---|
| **"No real querying"** — only "read file and hope" | Lands. There is no SELECT, no JOIN, no index. | True for arbitrary queries. Mitigated for the queries you actually run by `index.md`, `triggers.md`, and `ripgrep` over a small corpus. The system is built for the ~50–500 files of personal context, not for analytic workloads. If you need queries, this is the wrong layer. |
| **"No relationships"** — wikilinks make a pretty graph but you can't traverse it programmatically | Lands. `[[wikilinks]]` are a UX feature, not a graph database. | Accepted. For multi-hop entity traversal use Zep / Graphiti. The wikilinks here are for *humans* navigating the vault and for the *agent* loading adjacent context, not for graph queries. |
| **"Scale ceiling at 500–5,000 notes"** — token cost grows linearly | Lands at the upper end. The whole architecture assumes you never load everything. | Designed-in: `index.md` + `triggers.md` are the lazy-loading mechanism. `memory/` is hierarchical so the agent reads a handful of files per session, not the whole tree. The hard ceiling is real; this is explicitly a personal-context layer, not an enterprise knowledge base. |
| **"No schema enforcement"** — same contact written 3 different ways across sessions | Lands as written. Markdown alone doesn't enforce anything. | The unwritten answer in v2.0 is: the lint operation is *supposed* to catch this. v2.0 leaves linting to the human and the AI; v3 will ship a portable linter. Until then: the entropy is real. |
| **"No concurrent access"** — multi-agent writes silently corrupt files | Lands for true multi-agent setups. SQLite (WAL) handles this; flat files don't. | Accepted within this system's scope, which is **single-user, single-agent-at-a-time**. If you're orchestrating multiple agents writing concurrently to the same memory, this isn't the right substrate without an inbox/compactor pattern on top. |

### What this system gives up — and what it preserves

This is the trade Jonathan's critique correctly forces into the open:

| If you choose… | You get | You give up |
|---|---|---|
| **SQLite + Kuzu** (Jonathan's stack) | Real queries, real graph traversal, schema enforcement, concurrent writes, scaling past tens of thousands of records | Plain-text portability, zero infrastructure, "copy-paste your memory to any other provider", `git diff` as an audit log, the vault doubling as a human-readable second brain |
| **Mem0 / Zep / Letta / Cloudflare** (managed) | Mature retrieval, benchmarked accuracy, automatic decay, multi-tenant scoping, professional support | Vendor coupling (even with export commitments), opaque retrieval choices, your memory living behind an API you don't control |
| **This repository** | Full ownership; one folder you can `tar` and move; works offline; same files across Claude / Copilot / ChatGPT / Cursor / any future tool that reads text; `git log` as memory history; you can read it with your eyes | Real querying, real relationships, automatic decay, multi-agent concurrency, scaling past low thousands of files |

**Honest bottom line.** If your problem is "agents at organizational scale need queryable memory infrastructure", Jonathan is right and you should not use plain Markdown. Use SQLite + a graph DB, or pick one of Mem0 / Zep / Letta / Cloudflare. If your problem is *"I have a personal context — identity, preferences, projects, people, decisions — that I want any AI I use today and any AI I might use in 2028 to be able to read, that I can edit with my eyes and version with `git`, and that I never want to be hostage to a vendor's retrieval API"*, this system was designed for that exact problem and a year of daily use suggests it still does it well. The two problems are not in competition. Pick the layer for the job.

A v3 of this repository — markdown-only, but with atomic facts, YAML schemas, and materialized views — is in design and aims to push the upper bound on "queryable" without giving up plain-text portability. Issue thread to follow.

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

*Developed through daily use with Claude Code and GitHub Copilot. March 2026 – present. Last situated against the broader landscape: May 2026.*
