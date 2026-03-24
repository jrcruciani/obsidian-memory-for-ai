# AI Memory System with Obsidian
## A guide to replicating persistent context across AI sessions

> **Who this is for:** Anyone who uses AI (Claude, Copilot, ChatGPT, etc.) regularly and wants the AI to "know you" without having to re-explain yourself every time.

---

## Table of contents

1. [The problem this solves](#the-problem-this-solves)
2. [General architecture](#general-architecture)
3. [Memory hierarchy](#memory-hierarchy)
4. [Component 1: The master document (`CLAUDE.md`)](#component-1-the-master-document-claudemd)
5. [Component 2: The `memory/` folder](#component-2-the-memory-folder)
   - [Memory classification and relevance](#memory-classification-and-relevance)
   - [`ContextSummary.md` — Operational memory index](#contextsummarymd-inside-memory--operational-memory-index)
   - [`working-context.md` — Mutable session state](#working-contextmd--mutable-session-state)
   - [`recent-sessions.md` — Rolling session log](#recent-sessionsmd--rolling-session-log)
   - [`glossary.md` — Internal vocabulary](#glossarymd--internal-vocabulary)
   - [`people/` — People profiles](#peoplenamedmd--people-profiles)
   - [`projects/` — Active projects](#projectsprojectmd--active-projects)
   - [`decisions/` — Decision memory](#decisionsdecisionmd--decision-memory)
   - [`context/company.md` — Professional environment](#contextcompanymd--professional-environment)
   - [`context/personality.md` — Personality profile](#contextpersonalitymd--personality-profile-optional)
6. [Component 3: `ContextSummary.md` in each folder](#component-3-contextsummarymd-in-each-folder)
7. [Component 4: `TASKS.md`](#component-4-tasksmd)
8. [Component 5: Wikilinks and the knowledge graph](#component-5-wikilinks-and-the-knowledge-graph)
9. [How it integrates with AI tools](#how-it-integrates-with-ai-tools)
   - [Working from a different project directory](#working-from-a-different-project-directory)
10. [Update protocol](#update-protocol-instructions-for-the-ai)
    - [Proactive memory triggers](#proactive-memory-triggers)
    - [Periodic maintenance](#periodic-maintenance-let-the-ai-audit-the-vault)
    - [Maintenance cadence](#turn-maintenance-into-a-real-routine)
11. [Typical workflow](#typical-workflow)
12. [Context pressure and progressive loading](#context-pressure-and-progressive-loading)
    - [Memory pressure](#memory-pressure-when-to-stop-loading)
    - [Progressive retrieval](#progressive-retrieval-search--scan--load)
13. [Implementation recommendations](#implementation-recommendations)
    - [Security](#a-note-on-security)
14. [Compatible tools](#compatible-tools)
15. [Why Obsidian and not something else](#why-obsidian-and-not-something-else)
16. [How the system evolves](#how-the-system-evolves)

---

## The problem this solves

AI assistants have no memory between sessions. Every conversation starts blank. If you have complex projects, a rich life, and well-defined preferences, this forces you to constantly repeat context — or settle for generic responses.

This system turns Obsidian into an "externalized memory" that you can inject into any AI session.

---

## General architecture

```
vault/
├── CLAUDE.md              ← Master context document (auto-loaded by Claude Code)
├── COPILOT.md             ← Identical copy for VS Code Copilot (or any other AI)
├── TASKS.md               ← Active, recurring, upcoming, and someday tasks
│
├── memory/                     ← Structured memory by domain
│   ├── ContextSummary.md       ← Operational index: what to load first vs. on demand
│   ├── working-context.md      ← Mutable state: what matters right now (updated each session)
│   ├── recent-sessions.md      ← Rolling log of last ~10 sessions
│   ├── glossary.md             ← Acronyms, internal terms, nicknames
│   ├── people/                 ← One .md per relevant person
│   │   ├── person1.md
│   │   └── person2.md
│   ├── projects/               ← One .md per active project
│   │   ├── project-a.md
│   │   └── project-b.md
│   ├── decisions/              ← Durable decisions and their rationale
│   │   ├── ContextSummary.md
│   │   └── DEC-001 - Example decision.md
│   └── context/                ← Stable structural context
│       ├── company.md          ← Professional environment, tools, processes
│       └── personality.md      ← Personality profile (optional but powerful)
│
├── FolderA/
│   ├── ContextSummary.md  ← Semantic index of the folder for the AI
│   └── (regular notes)
│
├── FolderB/
│   ├── ContextSummary.md
│   └── (regular notes)
│
└── ...
```

---

## Memory hierarchy

The system organizes context into three loading tiers — a pattern inspired by how operating systems manage memory between fast registers, RAM, and disk. The idea comes from [MemGPT](https://research.memgpt.ai) (Packer et al., 2023), which showed that LLMs benefit from the same kind of hierarchical memory management that CPUs use. We adapt the concept to plain files instead of code.

| Tier | What it contains | When it loads | Analogy |
|------|-----------------|---------------|---------|
| **Tier 0 — System prompt** | Master document (`CLAUDE.md`) | Always, automatically | CPU registers |
| **Tier 1 — Working memory** | `glossary.md`, `company.md`, `personality.md`, `working-context.md` | Always, at session start | RAM |
| **Tier 2 — Reference memory** | `people/`, `projects/`, `decisions/`, `recent-sessions.md` | On demand, when the topic requires it | Disk |

**Tier 0** is read-only during a session — it's your identity basics, interaction rules, and loading instructions. Think of it as a **router**, not a warehouse. The AI reads it once and doesn't modify it mid-session.

**Tier 1** is the active working set. These files are small, dense, and always relevant. The `working-context.md` file (described below) is the one piece of Tier 1 that the AI *writes to* at session end — a mutable snapshot of what matters right now.

**Tier 2** is everything else. The AI doesn't load it unless the conversation requires it. `ContextSummary.md` files act as the index that tells the AI *which* Tier 2 files to pull in — like a page table that maps virtual addresses to physical storage.

This hierarchy matters because context windows are finite. Loading everything wastes tokens on information that isn't relevant to the current session. Loading nothing forces the AI to guess. The tier model gives a middle path: always-on identity, always-on working state, and structured access to everything else.

---

## Component 1: The master document (`CLAUDE.md`)

This is the heart of the system. It loads automatically at the start of each Claude Code session (if placed in the working directory). For other AI tools, paste it at the beginning of the chat or attach it as context.

### What to include

```markdown
# Context for AI sessions

## Who I am
- Name, role, place of residence
- Only the identity facts the AI genuinely needs in most sessions

## Where my memory lives
- Absolute vault path
- Key entry points: `memory/ContextSummary.md`, `memory/glossary.md`, `TASKS.md`
- Instruction to load detailed people/project context from `memory/`, not from this file

## How to interact with me
- Preferred tone (formal / peer / technical)
- Primary language
- Things I value: complexity, citations, connections across disciplines
- Things to avoid: disclaimers, oversimplification, condescension

## Operating rules
- Security / privacy constraints
- Tool preferences
- Update protocol

## Update protocol
(instructions to the AI about what to update at the end of each session)
```

### Golden rule of the master document

**Use Tier 0 as a router, not a warehouse.** The AI reads it in full at the start. In practice, smaller is better: often **50–200 lines** is enough. If you find yourself pasting detailed biographies, project state, or long preference lists here, move them into `memory/` and load them on demand.

---

## Component 2: The `memory/` folder

Divide memory into these layers:

### Memory classification and relevance

Every file in `memory/` should have YAML frontmatter with these core fields:

```yaml
---
type: fact | preference | rule | project | person | decision
relevance: high | medium | low
last_reviewed: 2026-03-15
---
```

**Type** classifies what kind of memory it is:

| Type | What it captures | Example |
|------|-----------------|---------|
| `fact` | Stable information about the world | Professional context, glossary |
| `preference` | How you like things done | Communication style, tool choices |
| `rule` | Instructions the AI must follow | Update protocol, security rules |
| `project` | An active or past project | Code projects, creative work |
| `person` | Someone relevant to your context | Family, collaborators, clients |
| `decision` | Durable rationale for a meaningful change | System change, project direction |

**Relevance** signals how important this file is for current sessions:

| Level | Meaning | AI behavior |
|-------|---------|-------------|
| `high` | Essential for most sessions | Always load when relevant |
| `medium` | Useful in specific contexts | Load when the topic comes up |
| `low` | Historical or rarely needed | Candidate for archival |

**Last reviewed** is a semantic freshness signal. It marks when a note was **actually validated or meaningfully updated**, not just when an audit script touched it. During periodic maintenance, ask the AI: *"Review all memory/ files and flag any where `last_reviewed` is older than 3 months."*

This is the manual equivalent of importance scoring and memory decay in automated systems — without running any code. The AI reads the frontmatter, prioritizes `high` relevance files, and you periodically prune `low` relevance entries to keep context lean.

---

### `ContextSummary.md` inside `memory/` — Operational memory index

This file tells the AI how to navigate the memory layer efficiently:

- What to load first (always-relevant files)
- What to load only when a topic comes up
- Where durable decisions live
- What has changed structurally in the memory system

Think of it as a router between the master document and the detailed memory files. Without it, the AI tends to over-read or guess. With it, context loading becomes intentional.

```markdown
# ContextSummary — Memory

## Always load
- glossary.md — internal vocabulary
- context/company.md — professional environment
- context/personality.md — personality profile and interaction preferences

## Load on demand
- people/ — when a person is mentioned by name or nickname
- projects/ — when a project is mentioned by codename
- decisions/ — when the question is about *why* something was changed

## Recent structural changes
- [date]: [what changed and why]
```

---

### `working-context.md` — Mutable session state

This is the most MemGPT-inspired addition to the system. Where `ContextSummary.md` is structural (it describes *what's in the folder*), `working-context.md` is temporal — it captures *what matters right now*.

Think of it as a small whiteboard that the AI updates at the end of each session with the most important current facts. It's Tier 1: always loaded, always compact, always fresh.

```markdown
---
type: fact
relevance: high
last_reviewed: 2026-03-17
---
# Working context

Last updated by AI after session on 2026-03-17.

## Active focus
- Wine Academy: finalizing Cloudflare architecture, Héctor's content pipelines replace Paperclip+NanoClaw
- Herensuge: paused at chapter 10, picking up chapter 11 when bandwidth allows

## Open threads
- Austria interview: results expected June 2026
- Gabriel: first therapy appointment Thursday 19/3

## Recent decisions
- DEC-007: Content pipelines replace Paperclip+NanoClaw for Wine Academy
- DEC-006: Cloudflare-first architecture for Wine Academy

## Stale / resolved
- (items here get pruned on next review)
```

**How it works in practice:**

1. The AI reads `working-context.md` at session start (Tier 1, always loaded)
2. During the session, if something important changes — a decision is made, a project shifts, a thread resolves — the AI notes it
3. At session end, the AI rewrites this file to reflect the updated state
4. Old items move to "Stale / resolved" and get pruned next session

**Key constraints:**
- **Keep it under 40 lines.** If it grows beyond that, information should move to the proper file (project, person, decision) instead.
- **Facts, not narrative.** This is a state snapshot, not a session diary.
- **The AI writes it, you review it.** Glance at it occasionally to make sure the AI isn't drifting.

---

### `recent-sessions.md` — Rolling session log

This file gives the AI temporal continuity — a compressed record of what happened in recent sessions. Without it, every session starts from a structural snapshot but has no sense of *sequence* or *momentum*.

Inspired by MemGPT's recursive summarization of evicted conversation history. Instead of storing full transcripts, you store a one-liner per session that captures the key outcome.

```markdown
---
type: fact
relevance: medium
last_reviewed: 2026-03-17
---
# Recent sessions

Rolling log of the last ~10 sessions. Oldest entries get pruned.

| Date | Tool | Topic | Key outcome |
|------|------|-------|-------------|
| 2026-03-17 | Copilot | Memory system | Added MemGPT-inspired hierarchy, working-context, session log |
| 2026-03-16 | Claude Code | Memory system | Added decision layer, maintenance protocol, ResumenContexto |
| 2026-03-15 | Claude Code | Wine Academy | Defined Cloudflare architecture, evaluated content pipelines |
| 2026-03-14 | Claude Code | Blog | Published post on impermanence and digital memory |
```

**Rules:**
- **Cap at ~10 entries.** When a new session is logged, the oldest entry drops off. This is not an archive — it's a recency buffer.
- **One line per session.** Resist the urge to write paragraphs. The AI can always load the relevant project or decision file for details.
- **The AI appends, you prune.** At session end, the AI adds a row. During maintenance, you can remove entries that are no longer useful.

**When to load it:** Tier 2 — load it when the AI needs to understand what happened recently (e.g., "continue where we left off", "what did we decide last time?", "catch me up"). Don't load it for sessions where temporal context doesn't matter.

---

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

**Why it works:** When you later say "what's the status of [nickname] and [project]", the AI already knows what you mean without you having to explain.

---

### `people/[name].md` — People profiles

One file per relevant person (partner, children, collaborators, frequent clients, etc.).

```markdown
---
type: person
relevance: high
last_reviewed: 2026-03-15
---
# Full Name

**Also known as:** [nickname]
**Relationship:** [relationship to you]
**Context:** [what they do, where they live, etc.]

## Details relevant for the AI
- Shared interests
- Personality / communication style
- Important notes for interaction

## Shared projects or topics
- [list of joint projects]
```

**What NOT to include:** Sensitive data, passwords, legal documents. Only what helps the AI contextualize mentions of that person.

**Optional but powerful:** If you've done personality tests (MBTI, Big Five, HEXACO), adding a profile summary helps the AI understand relational dynamics significantly better.

---

### `projects/[project].md` — Active projects

```markdown
---
type: project
relevance: high
last_reviewed: 2026-03-15
---
# Project Name

**Codename:** [short name for use in conversations]
**Status:** Active / On hold / Completed
**Repo / Location:** [where the code or files live]
**Stack:** [technologies, tools]

## What it is
[description in 2–3 sentences]

## Current status
[progress, last milestone, next steps]

## Notes for the AI
- Project conventions
- Relevant architecture decisions
- What it should not touch / change
```

---

### `decisions/[decision].md` — Decision memory

Use this folder for decisions whose rationale should survive the session where they were made. Not every choice needs a record — only the ones where future-you (or the AI) would ask *"why did we do it this way?"*

```markdown
---
type: decision
relevance: high
last_reviewed: 2026-03-15
---
# DEC-001 - Decision title

**Status:** Accepted
**Date:** 2026-03-15
**Scope:** [memory system / project / workflow]

## Context
[Why a decision was needed]

## Decision
[What was chosen]

## Alternatives considered
- [Option A — why it was rejected]
- [Option B — why it was rejected]

## Consequences
- [Positive outcomes]
- [Tradeoffs accepted]
```

**When to create one:** Only when future sessions would lose important reasoning without it. This is not a diary — it's for durable rationale. Good examples: changing your memory system structure, choosing a tech stack for a project, deciding to drop or restructure a creative project.

**Recommended companion:** A `ContextSummary.md` inside `decisions/` that lists all decisions by date and scope, so the AI can find them without reading every file.

---

### `context/company.md` — Professional environment

```markdown
# Professional context

## Tools and systems
| Tool   | Use          | Notes  |
|--------|-------------|--------|
| [tool] | [what for]  | [notes] |

## Current role
- Company, position, specialization
- Type of clients / projects

## Recurring processes
| Process  | What it means in practice |
|----------|--------------------------|
| [name]   | [description]            |
```

---

### `context/personality.md` — Personality profile (optional)

This is the most powerful and most personal file. If you've done a personality test (HEXACO is recommended for its scientific validity), document the results with applied interpretations:

```markdown
# Personality profile

**Test:** [test name]
**Date:** [when you took it]

## Main traits

### [Trait 1] — [score / level]
[interpretation in your specific context]

### [Trait 2] — [score / level]
[interpretation]

...

## Implications for AI interaction
- [list of how the AI should adapt its behavior]
```

**Why this is useful:** The AI can calibrate how much validation it offers, how it frames criticism, whether to ask questions or give direct answers, and whether to assume you need emotional support or not.

---

## Component 3: `ContextSummary.md` in each folder

Each vault folder has a file that acts as a **semantic index** for the AI.

```markdown
# Context Summary — [Folder Name]

This folder contains [brief description]. [How it fits in your workflow].

## What's here

### [File or subfolder 1]
[Description of what it contains and what it's for]

### [File or subfolder 2]
[Description]

...

## Current status
[Progress, last relevant change, notes for the AI]
```

**When to use it:** When you ask the AI to work on a specific folder ("review my research notes on X"), point it to the `ContextSummary.md` first. It doesn't need to read every file.

---

## Component 4: `TASKS.md`

A task list structured by time horizon. Recommended format:

```markdown
## Active
- [ ] **[Name]** — brief description

## Recurring
- [ ] **[Name]** — description — due [date] 🔁 [frequency]

## Upcoming
- [ ] **[Name]** — due [date]

## Someday
- [ ] [idea or pending project with no date]
```

**AI use:** "Review my TASKS.md and tell me what I have due this week" works perfectly when you have explicit dates.

---

## Component 5: Wikilinks and the knowledge graph

Obsidian's `[[wikilinks]]` are not just a navigation convenience — they are the connective tissue that turns a collection of files into a **navigable knowledge graph**. Both you and the AI benefit from explicit links between notes.

### The `## Links relacionados` pattern

At the end of each content note, add a section with links to related notes. Each link should include a **relationship verb** that tells the AI (and you) *how* the notes connect, not just *that* they connect:

```markdown
## Links relacionados

- [[Note A]] — extends: develops the same argument further
- [[Note B]] — contradicts: presents an opposing view
- [[Note C]] — supports: provides evidence for the same thesis
- [[Note D]] — source: research that feeds this note
- [[Note E]] — applies: where this concept is used in practice
```

### Relationship types

Use these verbs to classify links. You don't need to be rigid — a brief annotation is always better than none — but consistent verbs make the graph meaningful:

| Verb | Meaning | Example |
|------|---------|---------|
| `extends` | Develops the same idea further | A philosophy essay linking to a deeper treatment |
| `supports` | Provides evidence or backing | Research linking to the thesis it supports |
| `contradicts` | Presents an opposing or tension view | Two notes with incompatible conclusions |
| `source` | Raw material that feeds this note | Research → creative writing chapter |
| `applies` | Where a concept is used in practice | A theory → a character who embodies it |
| `part_of` | Component of a larger whole | A chapter → the novel it belongs to |
| `related` | General thematic connection | Default when the relationship is loose |

The brief annotation after each link is important. It tells both you and the AI *why* the connection exists, not just *that* it exists. A link without context is noise; a link with a one-line reason is signal.

### What to link

- **Thematic connections** — notes that explore the same idea from different angles
- **Cross-folder bridges** — these are the most valuable: a research note linking to a creative writing chapter, a philosophy essay linking to a character profile
- **Source → application** — research that feeds into a project, a concept that informs a decision

### Let the AI build the graph for you

One of the most powerful uses of this system is asking the AI to **audit your vault for missing connections**. A prompt like:

> "Review all my vault files and find relationships between documents that exist but aren't linked. Create the wikilinks so I can see them in Obsidian's graph view."

The AI can read every file, identify thematic overlaps you missed, and add hundreds of links in one session. This is particularly effective for vaults that have grown organically over time — the connections are there, they just haven't been made explicit.

### Graph view as a thinking tool

Once the links exist, Obsidian's graph view becomes a map of your intellectual landscape. Clusters reveal where your thinking is dense. Isolated nodes reveal notes that should be connected but aren't. Bridge nodes — notes that connect otherwise separate clusters — reveal your most integrative ideas.

---

## How it integrates with AI tools

### Claude Code (CLI)
Place `CLAUDE.md` in the project's working directory. Claude loads it automatically at the start of every session. For coding projects, this is the most seamless integration.

### Working from a different project directory

Claude Code has a limitation: it loads `CLAUDE.md` from the current working directory. If you're working on a coding project in `~/projects/my-app/`, it won't automatically read your vault's `CLAUDE.md`.

There are three ways to solve this, from simplest to most powerful:

**Option 1: Global instructions (no code, works today)**

Create `~/.claude/CLAUDE.md` — a lightweight global instructions file that Claude Code loads in *every* session regardless of working directory. Keep it short (30–50 lines) with:

- Your identity basics (name, role, location)
- The absolute path to your vault
- An instruction to read vault files when context is needed
- Your interaction preferences

```markdown
# Global context

## Identity
- [Name], [role], [location]

## Obsidian vault (memory system)
My knowledge base and AI memory lives at:
`~/path/to/your/obsidian/vault/`

When I mention "the vault", "my notes", or reference people/projects by short names,
read the relevant files from that path. Key entry points:
- CLAUDE.md — Tier 0 context and loading rules
- memory/ContextSummary.md — what to load first
- memory/glossary.md — internal vocabulary
- TASKS.md — current tasks

## Interaction preferences
- [Your preferences here]
```

The vault's full `CLAUDE.md` stays in the vault for sessions where the vault *is* the working directory. The global file is a pointer that says "my memory lives over there — go read it when you need it."

**Option 2: Symlinks (simple, slightly fragile)**

Create a symlink from each project to your vault's `CLAUDE.md`:

```bash
ln -s ~/path/to/vault/CLAUDE.md ~/projects/my-app/CLAUDE.md
```

The downside: symlinks can break if paths change, and you'll have a `CLAUDE.md` in every project directory.

**Option 3: Cowork plugin (best for Claude Desktop)**

Package the memory system as a Cowork plugin with slash commands (`/memory-load`, `/memory-update`, `/memory-audit`, `/memory-decide`) and an auto-triggering skill. Once installed, the commands are available in every Cowork session regardless of context. See the full step-by-step in **[plugin-guide.md](plugin-guide.md)**.

**Option 4: MCP server (most powerful, requires code)**

Package the memory system as a local MCP server that exposes tools like `memory_read`, `memory_search`, `memory_update`. Any AI tool that supports MCP (Claude Code, Cursor, etc.) could then access your vault's memory from any working directory, automatically. This is essentially what projects like [Chetna](https://github.com/vineetkishore01/Chetna) do with a database backend — the same idea could be built on top of your Markdown files.

**Option 5: Standalone automation agent (runs outside conversations)**

Build a script that maintains your memory files autonomously — session-end updates, scheduled audits, consistency checks — without needing an open chat session. Works with the Anthropic API (direct tool use) or the GitHub Copilot SDK (pre-built agentic loop). See the full guide in **[automation-guide.md](automation-guide.md)**.

**Recommendation:** Start with Option 1. It takes two minutes, works immediately, and covers 90% of use cases. If you use Claude Desktop (Cowork) heavily, Option 3 gives you the best experience there. If you want automated maintenance that runs on a schedule, Option 5 is the way to go. Move to Option 4 only if you need programmatic memory access from custom tools.

### VS Code + GitHub Copilot
Use `COPILOT.md` in the root directory with the **same Tier 0 semantics** as `CLAUDE.md`. Keep one as the source of truth or sync them deliberately — don't let them drift into two different master documents.

### Claude.ai / ChatGPT (web)
Create a **custom system instruction** (in Settings → Custom Instructions or equivalent) using a condensed version of the master document. For intensive sessions, paste the full `CLAUDE.md` at the start of the chat.

### Any AI with file access
Attach `CLAUDE.md` + the `ContextSummary.md` of the relevant folder + the corresponding project file. If the question is about *why* something was changed, attach the relevant file from `memory/decisions/` too.

---

## Update protocol (instructions for the AI)

Include this at the end of your `CLAUDE.md`:

```markdown
## Update protocol

Mandatory rule: at the end of each relevant session, update:

1. **CLAUDE.md / COPILOT.md** — only if Tier 0 instructions or the high-level profile summary changed
2. **ContextSummary.md** of the affected folder — reflect changes made
3. **memory/ContextSummary.md** — if the structure or loading logic of memory changed
4. **memory/** — update people, project, or decision files if applicable
5. **`last_reviewed`** — update it only on files whose content you semantically validated or changed
6. **TASKS.md** — mark completed tasks or add new ones
7. **memory/working-context.md** — rewrite to reflect current state
8. **memory/recent-sessions.md** — append a one-line entry for this session
```

### Proactive memory triggers

Don't wait for session end. MemGPT showed that the most effective memory systems update *during* the conversation, not just at the end. Include these trigger rules in your master document:

```markdown
## Proactive memory triggers

During the session, if any of these happen, propose the update immediately:

- **New fact about a person** → Propose adding it to their people/ file
- **Decision made with rationale** → Propose a new DEC- entry in decisions/
- **Project status changes** → Propose updating the project file
- **New term or codename introduced** → Propose adding it to glossary.md
- **Task completed or created** → Update TASKS.md right away, don't wait

"Propose" means: tell me what you'd update and where, then do it if I confirm.
For TASKS.md updates, just do it — no confirmation needed.
```

**Why proactive beats reactive:** At session end, the AI has to reconstruct what happened from its conversation history. Mid-session, the context is fresh and the update is precise. This is the plain-text equivalent of MemGPT's self-directed working context edits — the AI manages its own memory as the conversation evolves.

This turns the AI into a co-maintainer of the system. At the end of any working session you can ask: "Update the relevant memory files with what we did today."

### Periodic maintenance: let the AI audit the vault

Beyond session-by-session updates, schedule occasional full-vault reviews. Ask the AI to:

- **Find missing wikilinks** — connections between notes that should exist but don't
- **Update `ContextSummary.md` files** — especially after adding new notes to a folder
- **Review decision coverage** — ensure important workflow or structural changes are captured in `memory/decisions/`
- **Flag stale information** — projects marked "active" that haven't been touched in months
- **Identify orphan notes** — files with no incoming or outgoing links
- **Review memory relevance** — check `last_reviewed` dates in `memory/` frontmatter, treat them as semantic freshness signals (not audit timestamps), downgrade `relevance` for entries that haven't been relevant in months, and archive or remove `low` relevance files that no longer serve current context
- **Strengthen link types** — upgrade vague `related` links to more specific verbs (`extends`, `supports`, `contradicts`, etc.) as the AI learns more about your vault

This kind of structural maintenance is tedious for humans but trivial for an AI with file access. A single session can add hundreds of links and bring every summary file up to date.

### Turn maintenance into a real routine

Don't treat maintenance as an occasional vague intention. Give it explicit cadence:

- **After an important session** — run a micro-review if the session changed structure, conventions, or project direction
- **Monthly** — do a light audit of `memory/`
- **Quarterly** — do a structural review of the whole context system

| Cadence | Scope | Typical actions |
|---------|-------|-----------------|
| Post-session | Affected files only | Update notes, adjust `last_reviewed` on files actually reviewed, update `memory/ContextSummary.md`, record a decision if rationale should persist |
| Monthly | `memory/` | Review stale notes, downgrade `relevance`, merge redundancies, add missing links |
| Quarterly | Whole system | Archive low-value memory, review all summaries, check master doc balance, review decision coverage |

**Tip:** Keep a dedicated checklist note inside `memory/` so the AI can follow the same review pattern every time you ask for maintenance.

**Tip:** If you use Obsidian 1.12+, the CLI can automate many audit tasks — orphan detection, broken links, property sweeps — in seconds from the terminal. See **[obsidian-cli.md](obsidian-cli.md)** for ready-to-use scripts.

---

## Typical workflow

**At the start of a session:**
1. The AI loads `CLAUDE.md` automatically (or you attach it)
2. If the work is on a specific folder, point to its `ContextSummary.md`
3. If the work involves specific people, projects, or prior decisions, point to the relevant files in `memory/`

**During the session:**
- The AI operates with full context
- You can refer to projects, people, and terms by their short names

**At the end of the session:**
- Ask the AI to update the relevant files
- Or do it manually if you prefer full control

---

## Context pressure and progressive loading

Context windows are finite. Even the largest models have limits, and filling a window with context leaves less room for the actual work. These two protocols — adapted from MemGPT's memory pressure warnings and paginated retrieval — help the AI manage context efficiently without your intervention.

### Memory pressure: when to stop loading

Include this instruction in your master document or ContextSummary:

```markdown
## Memory pressure rule

If you have loaded more than 5 files from memory/ in this session,
stop loading more. Instead:
1. Summarize what you've learned so far from the loaded files.
2. Ask me which thread to go deeper on.
3. Only then load additional files for that specific thread.

Never load all of people/, projects/, and decisions/ in the same session
unless explicitly asked.
```

**Why this matters:** Without this rule, an eager AI will read every file it finds referenced in a ContextSummary, quickly consuming the context window with information that may not be relevant. The pressure rule forces prioritization.

### Progressive retrieval: search → scan → load

When the AI needs information from the vault, it should follow this sequence instead of loading files speculatively:

1. **Search** — Read the relevant `ContextSummary.md` to identify which files *might* contain the answer
2. **Scan** — If uncertain, read only the frontmatter and first heading of candidate files to confirm relevance
3. **Load** — Read the full file only when confirmed relevant

This is the Markdown equivalent of MemGPT's paginated archival search. Instead of dumping an entire database into context, the AI navigates the index, narrows candidates, and loads only what it needs.

```
Example: User asks "what did we decide about the data format for Concordance?"

Step 1 — Read decisions/ContextSummary.md
         → Finds: "DEC-001 - Concordance data format"
Step 2 — Load decisions/DEC-001 - Concordance data format.md
         → Answer found. No other files needed.

NOT: Load all of decisions/, projects/, and people/ "just in case."
```

**Teach the AI in your master document:**

```markdown
## How to find information

When you need information from my vault:
1. Read the ContextSummary.md of the relevant folder first.
2. Load only the files that match the current question.
3. If you're unsure which file has the answer, ask me rather than loading everything.
```

---

## Implementation recommendations

### Start simple
Don't try to build the whole system at once. Recommended order:
1. Write a basic `CLAUDE.md` (who you are, your projects, how you want to be addressed)
2. Add `TASKS.md`
3. Add `glossary.md`
4. Add project files one by one as you use them
5. Add people profiles as they become relevant
6. Add `ContextSummary.md` files in folders as needed
7. Add `memory/decisions/` once you start making changes whose rationale should persist
8. Add `memory/working-context.md` once you have enough context that session continuity matters
9. Add `memory/recent-sessions.md` once you want the AI to know what you've been working on recently

### Design principles
- **Each file must be readable independently** — don't rely on the AI remembering another file from the same session
- **Be specific, not exhaustive** — "use direct responses without disclaimers" beats three paragraphs about your communication philosophy
- **Absolute dates, not relative** — "due 2026-04-15" instead of "in two weeks"
- **Consistent codenames** — using the same name across all files makes it easier for the AI to connect references

### What NOT to put in the memory system
- Passwords or credentials (even if they exist elsewhere in plain text, don't reference them here)
- Information that changes very frequently (use `TASKS.md` with dates instead)
- Routine code or architecture decisions derivable from the code itself
- Git history or who changed what (use `git log` for that)

### A note on security

Your vault will inevitably contain personal information — names, relationships, professional context, personality traits. That's the point. But draw a hard line:

- **Never store passwords, API keys, tokens, or credentials** in any memory file. Not even "for convenience." Use a password manager (Bitwarden, 1Password, etc.) instead.
- **Never store financial account numbers, government IDs, or legal documents** in files that the AI reads. If you need these in your vault for personal reference, keep them in a separate folder that is explicitly excluded from AI context.
- **Be aware of what you share.** When you paste `CLAUDE.md` into a web AI session, everything in that file is sent to a third-party server. Write it assuming it could be read by someone other than you.
- **If your vault syncs to the cloud** (iCloud, Syncthing, etc.), ensure the sync service is one you trust. Plain Markdown files are readable by anyone with access to the storage.

The rule of thumb: if losing access to a piece of information would cause you financial, legal, or personal harm, it doesn't belong in the memory system.

---

## Compatible tools

| Tool                    | Compatibility | Method                              |
|-------------------------|--------------|-------------------------------------|
| Claude Code (CLI)       | Native       | CLAUDE.md in working directory + `~/.claude/CLAUDE.md` global |
| Claude Desktop (Cowork) | Native       | Plugin with slash commands — see [plugin-guide.md](plugin-guide.md) |
| VS Code Copilot         | High         | COPILOT.md + context files          |
| Claude.ai               | Manual       | Attach or paste at start            |
| ChatGPT                 | Manual       | Custom Instructions + attach        |
| Cursor                  | High         | .cursorrules or context files       |
| Obsidian + AI plugins   | Native       | Inside the vault                    |

---

## Why Obsidian and not something else

- **Plain Markdown files** — no vendor lock-in, work in any editor
- **Sync via iCloud / Syncthing / etc.** — available on all your devices
- **Human-readable vault** — it's not just for the AI, it's your second brain
- **Graph view** — visualize connections between notes
- **Plugins** — direct AI integration if you want to go further (Smart Connections, etc.)

The closest alternative is Notion, but as a proprietary database it's significantly harder to inject as context into AI tools in a fluid way.

---

## How the system evolves

This system grows organically. It's not a one-time setup. Over time:

- `ContextSummary.md` files get enriched with cross-folder analysis
- The decision log grows into a usable rationale timeline
- People profiles gain more nuance
- The glossary grows with terms you use repeatedly with the AI
- The master document reflects who you are now, not who you were when you wrote it

The signal that the system is working: when you open a session with "continue with [project]" and the AI picks up exactly where you left off, with the right tone, without asking who you are or what you want.

---

*System developed and refined through real-world use with Claude Code. Last updated: March 2026.*
