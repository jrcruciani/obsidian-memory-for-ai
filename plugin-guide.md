# From Memory System to Cowork Plugin

## How to turn your Obsidian AI memory into a portable, always-available plugin

> **Prerequisites:** You already have a working memory system following the [AI Memory System with Obsidian](https://github.com/Jrcruciani/obsidian-memory-for-ai) guide — a vault with `CLAUDE.md`, `memory/`, `TASKS.md`, and the associated structure. You use Claude Desktop (Cowork mode).
>
> **Naming note:** The original guide uses `ContextSummary.md` as the filename for semantic indexes. If you've localized yours (e.g., `ResumenContexto.md` in Spanish), that's fine — just be consistent throughout your plugin. This guide uses `ContextSummary.md` as the canonical English name.

---

## What you'll build

A Cowork plugin that packages your memory system into four slash commands and a skill that Claude can trigger automatically:

| Component | What it does |
|-----------|-------------|
| `/memory-load` | Loads context intelligently at session start |
| `/memory-update` | Updates memory files at session end |
| `/memory-audit` | Runs monthly or quarterly maintenance audits |
| `/memory-decide` | Registers a durable decision with full rationale |
| Skill: `memory-system` | Auto-triggers when you mention memory, vault, context, people, or projects by name |

Once installed, you invoke `/memory-load` at the start of any Cowork session and Claude knows who you are, what you're working on, and how you think. No pasting, no attaching, no re-explaining.

---

## Why a plugin instead of just CLAUDE.md

The memory system as described in the guide works well with Claude Code (CLI) because it auto-loads `CLAUDE.md` from the working directory. But in **Cowork mode** (Claude Desktop), that auto-loading doesn't happen the same way. A plugin solves this by:

- Making commands available in every session regardless of folder context
- Letting `CLAUDE.md` stay lean instead of stuffing loading heuristics and maintenance logic into Tier 0
- Encoding the loading strategy, update protocol, and maintenance checklist as executable instructions rather than prose the AI has to interpret
- Giving you explicit slash commands instead of relying on the AI to remember what to do

---

## Step-by-step: creating the plugin

### Step 1: Understand the plugin structure

A Cowork plugin is a directory with this layout:

```
obsidian-memory/
├── .claude-plugin/
│   └── plugin.json           # Manifest (required)
├── commands/                  # Slash commands
│   ├── memory-load.md
│   ├── memory-update.md
│   ├── memory-audit.md
│   └── memory-decide.md
├── skills/                    # Auto-triggering knowledge
│   └── memory-system/
│       ├── SKILL.md
│       └── references/
│           ├── maintenance-checklist.md
│           └── vault-structure.md
└── README.md
```

You'll create each of these files. The final step packages everything as a `.plugin` file that you install in Cowork with one click.

### Step 2: Create the manifest

Create `.claude-plugin/plugin.json`:

```json
{
  "name": "obsidian-memory",
  "version": "0.1.0",
  "description": "Persistent AI memory system backed by an Obsidian vault.",
  "author": {
    "name": "Your Name"
  }
}
```

The `name` field must be kebab-case. Everything else is descriptive.

### Step 3: Create the skill

The skill is the knowledge layer — it teaches Claude about your memory system's architecture, conventions, and loading strategy. It triggers automatically when conversations involve relevant topics.

Create `skills/memory-system/SKILL.md`:

```yaml
---
name: memory-system
description: >
  This skill should be used when the user mentions "memory", "vault", "context",
  "remember", "my notes", "CLAUDE.md", "ContextSummary", "glossary", "wikilinks",
  or refers to their Obsidian-based AI memory system. Also trigger when the user
  asks Claude to "load context", "update memory", "audit the vault", "register a
  decision", or uses short names for people/projects expecting Claude to already
  know them.
version: 0.1.0
---
```

After the frontmatter, write the skill body in Markdown. This should cover:

- **Vault location** — the absolute path to your Obsidian vault
- **Architecture** — the directory tree (memory/, people/, projects/, decisions/, etc.)
- **Frontmatter convention** — the type/relevance/last_reviewed fields and what they mean (`last_reviewed` = semantic validation date, not audit timestamp)
- **Context loading strategy** — what to load first (glossary, company, personality), what to load on demand (people, projects), what never to load all at once
- **Wikilink conventions** — the `## Links relacionados` pattern and relationship verbs (extends, supports, contradicts, source, applies, part_of, related)
- **Decision record format** — DEC-XXX naming, required sections
- **Update protocol** — what to update at session end
- **Maintenance cadence** — post-session micro-review, monthly, quarterly

Keep the skill body under 3,000 words. Put detailed reference material in `references/` files:

- `references/maintenance-checklist.md` — the full micro/monthly/quarterly checklist with checkbox items
- `references/vault-structure.md` — complete description of every folder and file in your vault

**Key adaptation point:** Replace the vault path with yours. Adjust the folder descriptions to match your actual vault contents.

#### What the reference files look like

The `references/` directory holds detailed content that the skill body references but doesn't include inline (to keep it lean).

**`references/maintenance-checklist.md`** — reusable checklist with three levels:

```markdown
# Maintenance Checklist

## Micro-review (after important sessions)
- [ ] Update notes affected during the session
- [ ] Update memory/ContextSummary.md if navigation changed
- [ ] Create decision note if rationale should persist
- [ ] Adjust `last_reviewed` only in files that were semantically reviewed or changed
- [ ] Update TASKS.md (mark completed, add new)
- [ ] Update CLAUDE.md if Tier 0 instructions or the high-level profile summary changed

## Monthly review
- [ ] Flag files where `last_reviewed` is older than 30 days
- [ ] Audit relevance distribution (if >60% are "high", it's lost meaning)
- [ ] Find redundant content across files and suggest merges
- [ ] Check for missing wikilinks between related files
- [ ] Verify ContextSummary.md matches actual structure
- [ ] Check glossary for unregistered terms from recent sessions

## Quarterly structural review
- [ ] Identify orphan notes (no incoming/outgoing links)
- [ ] Evaluate if memory/ needs new subfolders
- [ ] Check CLAUDE.md stays under 800 lines; migrate excess to memory/
- [ ] Review decision coverage for recent months
- [ ] Upgrade vague `related` links to specific verbs
```

**`references/vault-structure.md`** — a table describing every folder and file in the vault, organized by section. Include the type, relevance, and a one-line description for each `memory/` file. For content folders, describe what they contain and their current state (number of files, last major update). This file is vault-specific — there's no universal template, just describe what's actually in your vault.

### Step 4: Create the commands

Commands are Markdown files with YAML frontmatter. They're instructions *for Claude*, not documentation for you. Write them as directives.

**About `$ARGUMENTS`:** In command bodies, `$ARGUMENTS` is a variable that expands to whatever the user types after the slash command. For example, if the user types `/memory-load herensuge`, then `$ARGUMENTS` becomes `herensuge`. Use it to make commands context-sensitive.

#### `commands/memory-load.md`

```yaml
---
description: Load context from the Obsidian memory system
allowed-tools: Read, Glob, Grep
---
```

The body should instruct Claude to:

1. Read `memory/ContextSummary.md` first — this is the router. It tells Claude which files are always-relevant and which are on-demand. Don't dump the index itself; use it to *decide* what to read next.
2. Based on the index, read always-load files (typically: `glossary.md`, `context/company.md`, `context/personality.md`)
3. Read `TASKS.md` and summarize tasks due this week
4. If `$ARGUMENTS` contains a topic or person name, or if the user mentioned one earlier in conversation, load the corresponding file from `people/` or `projects/` using the glossary to resolve nicknames
5. Present a brief summary of loaded context — not a dump of every file

#### `commands/memory-update.md`

```yaml
---
description: Update memory files with changes from this session
allowed-tools: Read, Write, Edit, Glob, Grep
---
```

Instruct Claude to:

1. Review the conversation and identify what changed (profile, memory, tasks, structure, decisions)
2. Edit affected files: `CLAUDE.md` only for Tier 0/profile-summary changes, `memory/` files for domain changes, `TASKS.md` for completed/new tasks
3. Update `last_reviewed` only on files that were semantically validated or changed
4. Add new glossary terms if shorthand was established during the session
5. Add wikilinks if new thematic connections emerged
6. If a significant decision was made, suggest running `/memory-decide`
7. Report what was updated

#### `commands/memory-audit.md`

```yaml
---
description: Audit the memory system for staleness and structural issues
allowed-tools: Read, Write, Edit, Glob, Grep
argument-hint: [monthly|quarterly]
---
```

Instruct Claude to read the maintenance checklist from the skill's references, then execute the appropriate level based on the argument:

- **monthly** (default): scan frontmatter for stale `last_reviewed` (semantic validation date), audit relevance distribution, check for redundancy, find missing wikilinks, verify ContextSummary accuracy
- **quarterly**: all monthly checks plus orphan detection, category review, master doc balance check, decision coverage, link type quality
- **micro**: quick post-session check

Output should be a structured report with severity levels (critical/warning/info) and proposed changes that require confirmation before applying. Audits should **not** bulk-refresh `last_reviewed` after a mechanical scan.

#### `commands/memory-decide.md`

```yaml
---
description: Register a durable decision in the memory system
allowed-tools: Read, Write, Edit, Grep
argument-hint: [brief description of the decision]
---
```

Instruct Claude to:

1. Read `decisions/Timeline.md` to find the last DEC number and increment it
2. Gather decision details from `$ARGUMENTS` or by asking: context, decision, scope, alternatives, consequences
3. Create `DEC-XXX - Title.md` with the standard format (frontmatter + sections)
4. Add a row to `decisions/Timeline.md`
5. Update `decisions/ContextSummary.md` if the new decision changes how decisions are organized
6. Check for related updates (project files, CLAUDE.md, TASKS.md)

The `decisions/` folder uses two companion index files:

- **`Timeline.md`** — chronological log of all decisions (one row per DEC, with date, scope, status, and brief description). This is where `/memory-decide` looks to find the next ID number.
- **`ContextSummary.md`** — explains what belongs in decisions/ and what doesn't, so the AI knows when to suggest creating a decision vs. when it's overkill.

### Step 5: Create the README

Write a `README.md` that documents the plugin's purpose, components, vault location, and usage. This is for your own reference — Cowork displays it when you browse the plugin.

### Step 6: Package and install

From the plugin directory, create a `.plugin` file (which is just a zip):

```bash
cd /path/to/obsidian-memory
zip -r obsidian-memory.plugin . -x "*.DS_Store"
```

In Cowork, the `.plugin` file appears as an interactive card. Click "Copy to your skills" to install it. After installation, the commands and skill are available in every session.

---

## Adapting to your vault

The plugin as described assumes the architecture from the original guide. Here's what you need to customize:

| What to change | Where | Why |
|---------------|-------|-----|
| Vault path | SKILL.md body, all command bodies | Must point to your actual Obsidian vault |
| Folder names | SKILL.md body, vault-structure.md | Match your actual folder layout |
| Always-load files | SKILL.md, memory-load.md | Maybe your essential files are different |
| Frontmatter fields | SKILL.md | If you use different fields than type/relevance/last_reviewed |
| Language | Everywhere | The original system uses Spanish filenames (ResumenContexto, Links relacionados); adapt or keep |
| Relationship verbs | SKILL.md | Use whatever verbs make sense for your vault |

---

## Tips from real usage

**Start with `/memory-load` and `/memory-update` only.** The audit and decide commands are useful but not essential on day one. Get the load/update cycle working first.

**The skill description matters.** The `description` field in SKILL.md frontmatter controls when Claude auto-triggers the skill. Include specific phrases your users would actually say. If the skill never triggers, the description isn't matching.

**Commands are instructions, not documentation.** Write them as "do X, then Y, then Z" — not "this command does X." Claude follows them literally.

**Keep the skill body lean.** Under 3,000 words. Put detailed content in `references/` files. The SKILL.md is read every time the skill triggers; reference files are read only when needed.

**Test iteratively.** After installing, try `/memory-load` in a fresh session. Does Claude load the right files? Does the summary make sense? Adjust the command instructions based on what Claude actually does.

---

## For Claude Code users

If you also use Claude Code (CLI), the plugin and the `CLAUDE.md`-based approach complement each other:

- **Claude Code** auto-loads `CLAUDE.md` from the working directory and `~/.claude/CLAUDE.md` globally. The memory system works natively there without a plugin.
- **Cowork** (Claude Desktop) uses plugins for the same functionality. Install the plugin for Cowork sessions.

You don't need to choose — both can coexist pointing at the same vault.

---

*Guide based on real implementation of the obsidian-memory plugin, March 2026.*
