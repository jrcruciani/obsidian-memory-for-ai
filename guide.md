# AI Memory System with Obsidian
## A guide to building a persistent, compounding wiki for AI sessions

> **Who this is for:** Anyone who uses AI (Claude, Copilot, ChatGPT, etc.) regularly and wants the AI to "know you" without having to re-explain yourself every time.
>
> **Version 2.0** — *The Compiled Wiki.* Three layers, four operations. The AI does the bookkeeping; you direct the inquiry.

---

## Table of contents

1. [The problem this solves](#the-problem-this-solves)
2. [General architecture: three layers](#general-architecture-three-layers)
3. [Memory hierarchy](#memory-hierarchy)
4. [Layer 1: Sources](#layer-1-sources)
5. [Layer 2: The Wiki](#layer-2-the-wiki-memory)
   - [`schema.md` — Wiki operating manual](#schemamd--wiki-operating-manual)
   - [`index.md` — Content catalog](#indexmd--content-catalog)
   - [`log.md` — Operations log](#logmd--operations-log)
   - [`glossary.md` — Internal vocabulary](#glossarymd--internal-vocabulary)
   - [`working-context.md` — Mutable session state](#working-contextmd--mutable-session-state)
   - [`people/` — People profiles](#people--people-profiles)
   - [`projects/` — Active projects](#projects--active-projects)
   - [`decisions/` — Decision memory](#decisions--decision-memory)
   - [`insights/` — Filed-back knowledge](#insights--filed-back-knowledge)
   - [`context/` — Stable structural context](#context--stable-structural-context)
   - [Memory classification and relevance](#memory-classification-and-relevance)
6. [Layer 3: The Schema](#layer-3-the-schema-claudemd)
7. [Four operations](#four-operations)
   - [Ingest](#ingest)
   - [Query + File-back](#query--file-back)
   - [Lint](#lint)
   - [Log](#log)
8. [Reactive loading: triggers and modes](#reactive-loading-triggers-and-modes)
   - [Triggers](#formalized-triggers-triggersmd)
   - [Interaction modes](#interaction-modes-modesmd)
9. [Supporting components](#supporting-components)
   - [`TASKS.md`](#tasksmd)
   - [`ContextSummary.md` per folder](#contextsummarymd-per-folder)
   - [Wikilinks and the knowledge graph](#wikilinks-and-the-knowledge-graph)
10. [How it integrates with AI tools](#how-it-integrates-with-ai-tools)
11. [Update protocol](#update-protocol)
12. [Context pressure and progressive loading](#context-pressure-and-progressive-loading)
13. [Maintenance cadences](#maintenance-cadences)
14. [Implementation recommendations](#implementation-recommendations)
15. [Compatible tools](#compatible-tools)
16. [Why Obsidian and not something else](#why-obsidian-and-not-something-else)
17. [Philosophy: how the system evolves](#philosophy-how-the-system-evolves)

---

## The problem this solves

AI assistants have no memory between sessions. Every conversation starts blank. If you have complex projects, a rich life, and well-defined preferences, this forces you to constantly repeat context — or settle for generic responses.

Most solutions look like RAG: upload documents, let the AI retrieve relevant chunks at query time. This works, but the AI rediscovers knowledge from scratch on every question. There's no accumulation. Ask a question that requires synthesizing five documents, and it has to find and piece together the fragments every time.

The idea here is different. Instead of just retrieving from raw documents at query time, the AI **incrementally builds and maintains a persistent wiki** — a structured, interlinked collection of Markdown files that sits between you and the raw sources. When you add a new source, the AI reads it, extracts key information, and integrates it into the existing wiki. The knowledge is compiled once and kept current, not re-derived on every query.

**The wiki is a persistent, compounding artifact.** The cross-references are already there. The contradictions have already been flagged. The synthesis already reflects everything you've read. It gets richer with every source you add and every question you ask.

---

## General architecture: three layers

```
vault/
├── CLAUDE.md              ← Layer 3: Schema (identity, rules, loading instructions)
├── COPILOT.md             ← Same content, for VS Code Copilot
├── TASKS.md               ← Active, recurring, upcoming, and someday tasks
│
├── sources/                    ← Layer 1: Raw inputs (immutable)
│   ├── articles/               ← Web clips, research articles
│   ├── notes/                  ← Podcast notes, book highlights, meeting transcripts
│   └── assets/                 ← Images, screenshots referenced by sources
│
└── memory/                     ← Layer 2: The Wiki (LLM-maintained)
    ├── schema.md               ← Wiki operating manual
    ├── index.md                ← Content catalog (every page, one-line summary)
    ├── log.md                  ← Chronological operations log (parseable)
    ├── glossary.md             ← Acronyms, internal terms, nicknames
    ├── working-context.md      ← Mutable state: what matters right now
    ├── triggers.md             ← Keyword → file loading rules
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

**Layer 1 — Sources**: Your curated collection of raw inputs. Articles, papers, podcast notes, book highlights. These are immutable — the AI reads from them but never modifies them. This is your source of truth.

**Layer 2 — The Wiki**: A directory of AI-maintained Markdown files. Entity pages, concept pages, summaries, decisions, insights. The AI owns this layer: it creates pages, updates them when new sources arrive, maintains cross-references, and keeps everything consistent. You read it; the AI writes it.

**Layer 3 — The Schema**: A document (`CLAUDE.md` / `COPILOT.md`) that tells the AI how the wiki is structured, what the conventions are, and what workflows to follow. This is the key configuration — it's what makes the AI a disciplined wiki maintainer rather than a generic chatbot.

---

## Memory hierarchy

The system organizes context into loading tiers — a pattern inspired by [MemGPT](https://research.memgpt.ai) (Packer et al., 2023), which showed that LLMs benefit from OS-style tiered memory management.

| Tier | What it contains | When it loads | Analogy |
|------|-----------------|---------------|---------|
| **Tier 0 — System prompt** | `CLAUDE.md` | Always, automatically | CPU registers |
| **Tier 1 — Working memory** | `glossary.md`, `company.md`, `personality.md`, `working-context.md` | Always, at session start | RAM |
| **Tier 1.5 — Reactive** | `triggers.md`, `modes.md` | Referenced implicitly, consulted on demand | L2 cache |
| **Tier 2 — Reference memory** | `people/`, `projects/`, `decisions/`, `insights/`, `log.md` | On demand, when the topic requires it | Disk |
| **Sources** | `sources/` | Only during Ingest operations | External storage |

**Tier 0** is read-only during a session — identity basics, interaction rules, loading instructions. Think of it as a **router**, not a warehouse.

**Tier 1** is the active working set. Small, dense, always relevant. `working-context.md` is the one piece of Tier 1 that the AI *writes to* at session end.

**Tier 2** is everything else. The AI doesn't load it unless the conversation requires it. `index.md` acts as the catalog that tells the AI *which* Tier 2 files to pull in.

This hierarchy matters because context windows are finite. Loading everything wastes tokens. Loading nothing forces guessing. The tier model gives a middle path: always-on identity, always-on working state, and structured access to everything else.

---

## Layer 1: Sources

The `sources/` directory holds raw inputs that the AI reads but never modifies. When you add a source here, the AI processes it through the **Ingest** operation — extracting information and integrating it into wiki pages.

### Structure

```
sources/
├── README.md              ← What goes here, how ingest works
├── articles/              ← Web clips, articles, PDFs converted to Markdown
├── notes/                 ← Podcast notes, book highlights, meeting transcripts
└── assets/                ← Images, screenshots referenced by sources
```

### Source frontmatter

```yaml
---
title: "Article or source title"
date: 2026-04-05
source_url: "https://..."
source_type: article | podcast | book | video | conversation | other
processed: false
tags:
  - topic/relevant-tag
---
```

Set `processed: true` after the AI has ingested the source into the wiki.

### Tips

- **Obsidian Web Clipper** converts web articles to Markdown — clip directly into `sources/articles/`.
- **Download images locally:** Set Obsidian's attachment folder to `sources/assets/`.
- Sources are excluded from memory loading (they're not wiki pages). The AI only reads them during Ingest.
- You don't *need* sources to use the system. If all your information comes through conversations, light ingest works without any files in `sources/`.

---

## Layer 2: The Wiki (`memory/`)

This is the heart of the system — the AI-maintained knowledge base. Every file here is a wiki page that the AI creates, updates, and cross-references.

### `schema.md` — Wiki operating manual

The single source of truth for how the wiki operates: conventions, page formats, operation protocols, and maintenance rules. This is where you document your wiki's "rules of the game."

Think of it as an `AGENTS.md` or `CONTRIBUTING.md` but for your memory system. It tells the AI:
- How the three layers work
- What the four operations are and how to execute them
- Page format templates (frontmatter fields, section structure)
- Proactive writing rules (when to update without asking)
- Maintenance cadences

You and the AI co-evolve this file over time as you figure out what works for your domain.

### `index.md` — Content catalog

A content-oriented catalog of everything in the wiki — each page listed with a link, a one-line summary, and its type. Organized by category (core context, entities, knowledge, operational).

The AI reads this first to navigate. When answering a query, it scans the index to find relevant pages, then drills into them. This works surprisingly well at moderate scale (~100 pages) and avoids embedding-based RAG.

```markdown
# Index — memory wiki catalog

## Tier 1 — always load
| Page | Summary | Type |
|------|---------|------|
| glossary | Acronyms, nicknames, codenames | fact |
| context/company | Role, tools, processes | fact |
| context/personality | Personality profile, interaction implications | preference |
| working-context | Current focus, open threads, recent decisions | fact |

## Tier 2 — load on demand
| Page | Summary | Type |
|------|---------|------|
| people/marcus | Colleague, scientific illustration specialist | person |
| projects/concordance | Pigment recipe mapping project | project |
| insights/uv-thresholds | UV exposure limits need revision | insight |
| ... | ... | ... |
```

Update this file whenever pages are created, renamed, or retired.

### `log.md` — Operations log

A structured, chronological record of what happened and when — ingests, sessions, lint passes, decisions. Each entry starts with a consistent prefix so the log is parseable with simple tools.

```markdown
# Log

## [2026-04-05] ingest | Venetian pigment degradation study
Source: sources/articles/venetian-pigment-study.md
UV thresholds need revision. Created insight page. Updated Dr. Fischer profile.

## [2026-04-03] session | Weekly project review
Claude Code. Reviewed altarpiece timeline. Updated working-context.

## [2026-03-30] lint | Monthly audit
14 files reviewed. 0 critical, 1 warning. Fixed outdated profile.
```

**Format:** `## [YYYY-MM-DD] operation | topic`

**Operations:** `session`, `ingest`, `lint`, `decision`, `update`, `insight`

**Parseable:** `grep "^## \[" memory/log.md | tail -10` gives the last 10 entries.

The log is append-only. Prune oldest entries when the file exceeds ~50 entries.

### `glossary.md` — Internal vocabulary

```markdown
# Glossary

## Acronyms
| Term  | Meaning       | Context                        |
|-------|---------------|-------------------------------|
| PX    | [Project X]   | Short name for main project   |
| vault | Obsidian repo | My personal knowledge base    |

## Internal terms
| Term        | Meaning                        |
|-------------|-------------------------------|
| [code name] | [what it means in your context] |

## Nicknames → Full names
| Nickname | Person                  |
|----------|------------------------|
| [nick]   | [real name, relationship] |
```

When you say "what's the status of [nickname] and [project]", the AI already knows what you mean.

### `working-context.md` — Mutable session state

The most MemGPT-inspired component. Where `index.md` is structural (what's in the wiki), `working-context.md` is temporal — it captures *what matters right now*.

Think of it as a whiteboard the AI updates at session end. It's Tier 1: always loaded, always compact, always fresh.

```markdown
# Working context

Last updated after session on 2026-04-05.

## Active focus
- Project X: finalizing architecture, pipeline integration
- Novel: paused at chapter 10

## Open threads
- Job interview: results expected June 2026
- Family: trip planned for mid-April

## Recent decisions
- DEC-017: Memory System v2.0

## Stale / resolved
- (items here get pruned on next review)
```

**Key constraints:**
- **Keep it under 40 lines.** Longer content should move to the proper file.
- **Facts, not narrative.** State snapshot, not session diary.
- **The AI writes it, you review it.** Glance occasionally to catch drift.

### `people/` — People profiles

One file per relevant person. Include only what helps the AI contextualize mentions.

```yaml
---
type: person
relevance: high
last_reviewed: 2026-03-15
---
# Full Name

**Also known as:** [nickname]
**Relationship:** [relationship to you]
**Context:** [what they do, where they live]

## Details relevant for the AI
- Shared interests, communication style

## Shared projects or topics
- [list of joint projects]
```

**What NOT to include:** Passwords, sensitive data, legal documents. Only what helps the AI.

**Optional but powerful:** If you've done personality tests (HEXACO, Big Five), adding a profile summary helps the AI understand relational dynamics significantly better.

### `projects/` — Active projects

One file per active project:

```yaml
---
type: project
relevance: high
last_reviewed: 2026-03-15
---
# Project Name

**Codename:** [short name]
**Status:** Active / On hold / Completed
**Repo / Location:** [where the files live]
**Stack:** [technologies, tools]

## What it is
[description in 2–3 sentences]

## Current status
[progress, last milestone, next steps]

## Notes for the AI
- Conventions, architecture decisions, what not to touch
```

### `decisions/` — Decision memory

For decisions whose rationale should survive the session where they were made. Not every choice — only the ones where future-you would ask *"why did we do it this way?"*

```markdown
# DEC-001 - Decision title

**Status:** Accepted
**Date:** 2026-03-15
**Scope:** [memory system / project / workflow]

## Context
[Why a decision was needed]

## Decision
[What was chosen]

## Alternatives considered
- [Option A — why rejected]

## Consequences
- [Outcomes and tradeoffs]
```

Include a `ContextSummary.md` inside `decisions/` listing all decisions by date and scope.

### `insights/` — Filed-back knowledge

**New in v2.0.** This is where valuable conversation outputs go to live permanently. A comparison you asked for, an analysis, a connection you discovered — these shouldn't disappear into chat history.

```yaml
---
type: insight
source: session | ingest | analysis
source_date: 2026-04-05
relevance: high
last_reviewed: 2026-04-05
---
# Insight title

[The insight itself, with wikilinks to related pages]
```

Insights are created through the **file-back** mechanism: at session end, the AI asks "Any insight from this session worth filing?" Good answers become persistent wiki pages.

### `context/` — Stable structural context

- `company.md` — Professional environment: tools, role, processes, recurring workflows.
- `personality.md` — Personality profile (HEXACO recommended). Applied interpretations, not just scores. Implications for AI interaction.

These rarely change. They calibrate the AI's tone, level, and collaboration style.

### Memory classification and relevance

Every file in `memory/` should have YAML frontmatter:

```yaml
---
type: fact | preference | rule | project | person | decision | insight
relevance: high | medium | low
last_reviewed: 2026-03-15
---
```

| Type | What it captures |
|------|-----------------|
| `fact` | Stable information |
| `preference` | How you like things done |
| `rule` | Instructions the AI must follow |
| `project` | An active or past project |
| `person` | Someone relevant to your context |
| `decision` | Durable rationale for a meaningful change |
| `insight` | Valuable synthesis from a conversation or analysis |

**`last_reviewed`** is a semantic freshness signal. It marks when a note was **actually validated or meaningfully updated**, not when an audit script touched it. This is the manual equivalent of importance scoring and memory decay — without running code.

---

## Layer 3: The Schema (`CLAUDE.md`)

This loads automatically at session start (Claude Code reads it from the working directory; for other tools, attach it). It's the heart of Tier 0.

### What to include

```markdown
# Context for AI sessions

## Who I am
- Name, role, location
- Only identity facts needed in most sessions

## Where my memory lives
- Vault path
- Key entry points: memory/index.md, memory/glossary.md, TASKS.md
- Instruction to load from memory/, not duplicate here

## How to interact with me
- Preferred tone, language, values
- Things to avoid

## Operating rules
- Security, tool preferences
- Four operations: ingest, query+file-back, lint, log
- Reference memory/schema.md for detailed conventions

## Update protocol
(instructions for session end — see Update Protocol section)
```

### Golden rule

**Use Tier 0 as a router, not a warehouse.** 50–200 lines is enough. If you're pasting detailed bios or project state here, move them to `memory/` and load on demand.

---

## Four operations

### Ingest

Process new sources into wiki pages. A single source can touch 10+ pages.

**Heavy ingest** (file-based):
1. Drop a file in `sources/` (or point to an existing one)
2. AI reads the source thoroughly
3. AI discusses key takeaways with you
4. AI creates/updates wiki pages: people, projects, insights, glossary
5. AI updates `index.md` with new/modified pages
6. AI appends entry to `log.md`: `## [date] ingest | Source title`
7. AI marks source as `processed: true`

**Light ingest** (conversation-based):
1. Paste text or share information in conversation
2. AI identifies extractable entities, concepts, facts
3. AI proposes which wiki pages to create/update
4. AI updates index.md and log.md
5. No source file created — the conversation is the source

Personally, I prefer to ingest sources one at a time and stay involved — I read the summaries, check the updates, and guide the AI on what to emphasize. But you could also batch-ingest many sources at once with less supervision. Document the workflow that fits your style in your `schema.md`.

### Query + File-back

Standard query flow:
1. AI reads `index.md` to find relevant pages
2. AI loads and reads relevant pages (following progressive retrieval)
3. AI synthesizes an answer with citations to wiki pages

**File-back** (new in v2.0): good answers become wiki pages.

- **At session end:** The AI asks: "Any insight from this session worth filing?"
- **Mid-conversation:** When the AI detects a valuable synthesis: "This analysis seems worth preserving. File it as an insight?"
- **During ingest:** When processing a source reveals a connection worth documenting independently.

Filed insights go to `insights/` with wikilinks to related pages. This is how your explorations compound in the knowledge base just like ingested sources do.

### Lint

Periodically health-check the wiki. Beyond checking for stale information:

- **Contradictions** between pages (dates, facts, states that conflict)
- **Stale claims** superseded by newer sources or conversations
- **Orphan pages** with no inbound wikilinks
- **Missing concept pages** — topics frequently mentioned but lacking their own page
- **Missing cross-references** between obviously related pages
- **Investigation gaps** — areas where a web search or new source could fill a hole
- **Source coverage** — files in `sources/` still marked `processed: false`

The AI is good at suggesting new questions to investigate and new sources to look for. This keeps the wiki healthy as it grows.

### Log

Append structured entries to `log.md` for every operation. This gives you a timeline of the wiki's evolution and helps the AI understand what's been done recently.

See the [`log.md` section](#logmd--operations-log) above for format details.

---

## Reactive loading: triggers and modes

### Formalized triggers: `triggers.md`

Once your context grows beyond a handful of files, extract the loading logic into its own file. This idea is inspired by the *lorebook* concept from [Open-Her OS](https://github.com/kitfoxs/open-her-os) — keyword-activated entries that modulate AI behavior.

```markdown
# Triggers

## Loading triggers

| Keywords / signal | Files to load | Suggested mode |
|---|---|---|
| Marcus, illustration | `people/marcus.md` | — |
| Concordance, pigment | `projects/concordance.md` | research |
| blog, Strata, post | — | writing |
| /ingest, process this | `sources/README.md`, `schema.md` | ingest |
| insights, synthesis | `insights/README.md` | — |

## Writing triggers

| Signal detected | Action | Confirmation |
|---|---|---|
| New fact about a person | Propose adding to `people/` | Ask first |
| Decision with rationale | Propose new DEC- entry | Ask first |
| Task completed or created | Update TASKS.md directly | No confirmation |
| Valuable synthesis detected | Propose insight page in `insights/` | Ask first |
| Session ending | Ask "Any insight worth filing?" | Ask first |
| Operation completed | Append to `log.md` | No confirmation |
```

**Benefits:** Auditable (scan the table to see if someone is missing), single source of truth, extensible (add a row, not edit three files), mode-aware.

Keep triggers as Tier 1.5: the AI knows the file exists and consults it on demand.

### Interaction modes: `modes.md`

Without explicit guidance, AI adapts tone poorly. Modes make calibration explicit. Inspired by *companion modes* from [Open-Her OS](https://github.com/kitfoxs/open-her-os).

```markdown
# Interaction modes

## research
- **When:** Data analysis, source texts, hypothesis work
- **Tone:** Precise, technical, hypothesis-driven
- **Behavior:** Cite sources, flag uncertainty, propose next steps

## writing
- **When:** Blog posts, documentation, narrative work
- **Tone:** Clear, engaging, collaborative
- **Behavior:** Suggest structure, the author decides

## ingest
- **When:** /ingest, processing sources, integrating new material
- **Tone:** Analytical, methodical, collaborative
- **Behavior:** Read source fully, identify extractables, propose updates, update index+log

## logistics
- **When:** Tasks, travel, appointments
- **Tone:** Direct, efficient
- **Behavior:** Checklists, confirm dates/times

## default
- **When:** Everything else
- **Tone:** Collegial, natural
- **Behavior:** Detect context; if another mode fits, transition smoothly
```

Modes connect to triggers via the "Suggested mode" column. Can also be activated manually: `/mode research`.

**Design principles:** Keep them few (3–6). Each should have a clear tone shift. Modes are advisory, not rigid.

---

## Supporting components

### `TASKS.md`

A task list structured by time horizon:

```markdown
## This week
- [ ] **Task name** — description, due date

## Upcoming
- [ ] **Task name** — due date

## Someday
- [ ] Idea or project with no date

## Completed
- [x] **Done task** — completion date
```

Move completed tasks to the bottom — don't leave them inline.

### `ContextSummary.md` per folder

Each vault folder (outside `memory/`) gets a semantic index:

```markdown
# Context Summary — [Folder Name]

This folder contains [description]. [How it fits your workflow].

## What's here
### [File 1]
[Description]
```

When you ask the AI to work on a specific folder, point to its ContextSummary first.

### Wikilinks and the knowledge graph

`[[wikilinks]]` are the connective tissue that turns files into a navigable graph. At the end of each page, add links with relationship verbs:

```markdown
## Links

- [[Note A]] — extends: develops the same argument
- [[Note B]] — contradicts: opposing view
- [[Note C]] — supports: evidence for same thesis
```

| Verb | Meaning |
|------|---------|
| `extends` | Develops the same idea further |
| `supports` | Provides evidence |
| `contradicts` | Opposing view (flag for resolution) |
| `source` | Raw material |
| `applies` | Where a concept is used in practice |
| `supersedes` | Replaces older information |

**Let the AI build the graph:** Ask it to audit your vault for missing connections. A single session can add hundreds of links.

---

## How it integrates with AI tools

### Claude Code (CLI)
Place `CLAUDE.md` in the working directory. Claude loads it automatically. For cross-directory access, use `~/.claude/CLAUDE.md` as a lightweight global pointer.

### Working from a different project directory

**Option 1: Global instructions** — `~/.claude/CLAUDE.md` with your identity and a pointer to the vault path. Takes two minutes, covers 90% of cases.

**Option 2: Cowork plugin** — Package as a plugin with slash commands (`/memory-load`, `/memory-update`, `/memory-audit`). See [plugin-guide.md](plugin-guide.md).

**Option 3: Standalone agent** — Automated maintenance on a schedule using the Anthropic API or GitHub Copilot SDK. See [automation-guide.md](automation-guide.md).

**Option 4: MCP server** — Expose `memory_read`, `memory_search`, `memory_update` as tools. Most powerful, requires code.

### VS Code + GitHub Copilot
`COPILOT.md` in the root directory with the same semantics as `CLAUDE.md`.

### Claude.ai / ChatGPT (web)
Paste or attach `CLAUDE.md` at session start. For intensive sessions, include relevant memory files.

---

## Update protocol

Include this in your `CLAUDE.md`:

```markdown
## Update protocol

At the end of each relevant session:

1. Ask: "Any insight from this session worth filing in insights/?"
2. Update working-context.md to reflect current state
3. Append to log.md: ## [date] session | topic
4. Update index.md if new pages were created
5. Update affected ContextSummary.md files
6. Update memory/ files (people, projects, glossary, decisions) if applicable
7. Update TASKS.md — mark completed, add new
8. Update CLAUDE.md/COPILOT.md — only if Tier 0 instructions changed
```

### Proactive triggers during the session

Don't wait for session end. MemGPT showed that the most effective memory systems update *during* the conversation:

- **New fact about a person** → Propose adding to `people/`
- **Decision with rationale** → Propose new DEC- entry
- **Project status change** → Propose updating project file
- **New term or codename** → Propose adding to glossary
- **Task completed or created** → Update TASKS.md immediately (no confirmation)
- **Valuable synthesis** → Propose filing as insight

"Propose" means: say what you'd update and where, then do it if confirmed. For TASKS.md and log.md, act without confirmation.

---

## Context pressure and progressive loading

### Memory pressure: when to stop

```
If you have loaded more than 5 files from memory/ in this session:
1. Stop loading more.
2. Summarize what you've learned so far.
3. Ask which thread to deepen.
4. Only then load additional files for that thread.

Never load all of people/, projects/, and decisions/ in the same session
unless explicitly asked.
```

### Progressive retrieval: search → scan → load

When the AI needs information:
1. **Search** — Read `index.md` to identify candidate files
2. **Scan** — If uncertain, read only frontmatter and first heading to confirm relevance
3. **Load** — Read the full file only when confirmed relevant

This is the Markdown equivalent of MemGPT's paginated archival search.

---

## Maintenance cadences

### Post-session micro-review
When a session changed structure, conventions, or project direction:
- Update affected notes and index.md
- Create a decision if rationale should persist
- Append to log.md

### Monthly audit
- Review notes with oldest `last_reviewed`
- Confirm `high` relevance is still justified
- Merge small, overlapping notes
- Verify index.md matches actual structure
- Consolidate decisions (keep ≤8-10 active)
- Run expanded lint checklist
- Check source coverage (unprocessed sources)

### Quarterly structural review
- Detect orphan pages and underlinked notes
- Identify missing categories or oversized ones
- Verify CLAUDE.md isn't absorbing context that belongs in memory/
- Deep-clean decisions
- Evaluate if the schema still fits your workflow

**Tip:** Keep the lint checklist in `schema.md` so the AI follows the same pattern every time.

**Tip:** If you use Obsidian 1.12+, the CLI can automate many audit tasks. See [obsidian-cli.md](obsidian-cli.md).

---

## Implementation recommendations

### Start simple

Don't build the whole system at once:

1. Write a basic `CLAUDE.md` (who you are, your projects, how you want to be addressed)
2. Add `TASKS.md`
3. Add `memory/glossary.md`
4. Add project files one by one as you use them
5. Add people profiles as they become relevant
6. Add `memory/working-context.md` once session continuity matters
7. Add `memory/index.md` once you have enough files that navigation matters
8. Add `memory/decisions/` once changes need durable rationale
9. Add `sources/` once you start ingesting external material
10. Add `memory/insights/` once conversations produce knowledge worth preserving
11. Add `memory/schema.md` once your conventions stabilize

### Design principles

- **Each file must be readable independently** — don't rely on the AI having read another file
- **Be specific, not exhaustive** — "use direct responses" beats three paragraphs on communication philosophy
- **Absolute dates, not relative** — "due 2026-04-15" instead of "in two weeks"
- **Consistent codenames** across all files

### What NOT to include

- Passwords, API keys, tokens, or credentials — ever
- Financial account numbers, government IDs, legal documents
- Information that changes too frequently (use TASKS.md with dates)
- Routine code decisions derivable from the code itself

### Security note

Your vault will contain personal information — that's the point. But draw a hard line:

- **Never store credentials** in any memory file. Use a password manager.
- **Be aware of what you share.** When you paste `CLAUDE.md` into a web session, everything is sent to a third party.
- **If your vault syncs to the cloud**, ensure you trust the sync service.

Rule of thumb: if losing access to information would cause financial, legal, or personal harm, it doesn't belong in the memory system.

---

## Compatible tools

| Tool | How it works |
|------|-------------|
| Claude Code (CLI) | Native — `CLAUDE.md` in working directory + `~/.claude/CLAUDE.md` global |
| Claude Desktop (Cowork) | Plugin with slash commands — see [plugin-guide.md](plugin-guide.md) |
| VS Code + GitHub Copilot | `COPILOT.md` with same Tier 0 semantics |
| Obsidian CLI (1.12+) | Vault commands for auditing and maintenance — see [obsidian-cli.md](obsidian-cli.md) |
| Claude.ai / ChatGPT | Paste or attach at session start |
| Cursor | `.cursorrules` or context files |
| Any AI with file access | Attach the relevant `.md` files |
| Standalone agent | Automated maintenance — see [automation-guide.md](automation-guide.md) |

---

## Why Obsidian and not something else

- **Plain Markdown files** — no vendor lock-in, work in any editor
- **Sync via iCloud / Syncthing / etc.** — available on all your devices
- **Human-readable vault** — it's your second brain first, AI memory second
- **Graph view** — visualize the shape of your wiki: clusters, orphans, bridges
- **Wikilinks** — the connective tissue that makes files a knowledge graph
- **Plugins** — Dataview for dynamic queries, Smart Connections for AI integration
- **Git-friendly** — version history, branching, collaboration for free

---

## Philosophy: how the system evolves

**This is a foundation, not the one correct method.** Take what works, ignore what doesn't, build something better. There are many valid approaches to giving AI context; this one optimizes for transparency, portability, and human readability.

The tedious part of maintaining a knowledge base is not the reading or thinking — it's the bookkeeping. Updating cross-references, keeping summaries current, noting when new data contradicts old claims. Humans abandon wikis because the maintenance burden grows faster than the value. LLMs don't get bored, don't forget to update a cross-reference, and can touch 15 files in one pass. The wiki stays maintained because the cost of maintenance is near zero.

Your job is to curate sources, direct the analysis, ask good questions, and think about what it all means. The AI's job is everything else.

The signal that the system is working: you open a session with "continue with [project]" and the AI picks up exactly where you left off, with the right tone, without asking who you are.

---

*System developed through daily use with Claude Code and GitHub Copilot. Inspired by [MemGPT](https://research.memgpt.ai), [Chetna](https://github.com/vineetkishore01/Chetna), [Open-Her OS](https://github.com/kitfoxs/open-her-os), and [Andrej Karpathy](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). April 2026.*
