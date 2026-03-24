# Leveraging Obsidian CLI for Memory Maintenance

> **Requires:** Obsidian 1.12+ with CLI enabled (Settings → General → Command line interface). The Obsidian app must be running.

> [!tip] **CLI-first principle**
> If Obsidian is running and a CLI command can accomplish what you need — reading files, searching, updating properties, auditing links, toggling tasks — **always prefer it** over reading files into AI context, parsing YAML manually, or using grep/sed on raw Markdown. The CLI uses Obsidian's native index, resolves wikilinks correctly, and updates the graph automatically. Fall back to direct file I/O only when the CLI can't do the job (headless environments, remote access, bulk content rewrites).

Obsidian CLI lets you control Obsidian from the terminal. For memory systems, this means you can audit, query, and update your vault programmatically — without the AI reading every file into context, and without parsing YAML or resolving wikilinks manually.

This document covers three high-value recipes: a **health audit** you can run in seconds, a **property sweep** for inspecting and selectively updating frontmatter, and **quick capture** commands for appending to memory files from the terminal.

---

## Table of contents

1. [Why CLI instead of direct file access](#why-cli-instead-of-direct-file-access)
2. [Setup](#setup)
3. [Recipe 1: Vault health audit](#recipe-1-vault-health-audit)
4. [Recipe 2: Property sweep](#recipe-2-property-sweep)
5. [Recipe 3: Quick capture](#recipe-3-quick-capture)
6. [Reference: useful commands for memory systems](#reference-useful-commands-for-memory-systems)
7. [Limitations](#limitations)
8. [Integration with AI sessions](#integration-with-ai-sessions)

---

## Why CLI instead of direct file access

| Approach | Pros | Cons |
|----------|------|------|
| **Direct file I/O** (read/write `.md`) | Works everywhere, no dependencies | Doesn't resolve wikilinks, can't query backlinks/tags, must parse YAML manually |
| **GitHub API** | Works remotely, good for mobile shortcuts | Slow, needs auth, no Obsidian-native queries |
| **Obsidian CLI** | Native search index, backlinks, property management, wikilink resolution, rename updates links | Requires Obsidian running locally, not remote |

The CLI talks to the running Obsidian instance, so it uses the same index, link resolution, and property engine that the app does. When you `rename` or `move` a file through CLI, wikilinks update automatically. When you `search`, it uses Obsidian's index — faster and more accurate than grep for vault queries.

**Best used for:** local maintenance, scripted audits, quick capture from terminal, AI-assisted session workflows.

**Not a replacement for:** remote access (use the Memory Shortcut pattern from [optional-ideas.md](optional-ideas.md)), headless/CI pipelines (use direct file I/O or GitHub API).

---

## Setup

1. Update to Obsidian 1.12+ (installer 1.12.4+)
2. Go to **Settings → General → Enable CLI**
3. Follow the prompt to register the CLI
4. Restart your terminal

Verify it works:

```bash
obsidian version
# Should print something like: 1.12.7 (installer 1.11.7)

obsidian vault
# Should show your vault name, path, file count
```

If `obsidian` is not found, add this to your shell profile:

```bash
# macOS (zsh) — add to ~/.zprofile or ~/.zshrc
export PATH="$PATH:/Applications/Obsidian.app/Contents/MacOS"
```

### Target a specific vault

If your terminal is inside the vault folder, it's used automatically. Otherwise:

```bash
obsidian vault=jlrcodex search query="example"
```

---

## Recipe 1: Vault health audit

**What it does:** Checks structural integrity of your memory system in four commands — orphan files, dead ends, unresolved links, and tag distribution.

**When to run:** Monthly (as part of your maintenance cadence), or whenever you suspect link rot.

### The commands

```bash
# Files with no incoming links — candidates for pruning or linking
obsidian orphans

# Files with no outgoing links — possible stubs or isolated notes
obsidian deadends

# Broken wikilinks — references to files that don't exist
obsidian unresolved verbose

# Tag distribution — check your taxonomy health
obsidian tags counts sort=count
```

### As a one-liner

```bash
echo "=== ORPHANS ===" && obsidian orphans total && \
echo "\n=== DEAD ENDS ===" && obsidian deadends total && \
echo "\n=== UNRESOLVED ===" && obsidian unresolved total && \
echo "\n=== TOP TAGS ===" && obsidian tags counts sort=count | head -10
```

### As a reusable script

Save as `memory-audit.sh` (or wherever you keep scripts):

```bash
#!/bin/bash
# memory-audit.sh — Quick structural health check via Obsidian CLI
# Requires: Obsidian 1.12+ running with CLI enabled

export PATH="$PATH:/Applications/Obsidian.app/Contents/MacOS"

VAULT="${1:-}"  # optional: pass vault name as argument
VAULT_FLAG=""
[[ -n "$VAULT" ]] && VAULT_FLAG="vault=$VAULT"

echo "🔍 Memory System Health Audit"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

ORPHANS=$(obsidian $VAULT_FLAG orphans total 2>&1)
DEADENDS=$(obsidian $VAULT_FLAG deadends total 2>&1)
UNRESOLVED=$(obsidian $VAULT_FLAG unresolved total 2>&1)
FILES=$(obsidian $VAULT_FLAG files total 2>&1)

echo "📁 Total files:      $FILES"
echo "🔗 Orphans:          $ORPHANS (no incoming links)"
echo "🚫 Dead ends:        $DEADENDS (no outgoing links)"
echo "⚠️  Unresolved links: $UNRESOLVED (broken wikilinks)"
echo ""

if [[ "$UNRESOLVED" -gt 0 ]] 2>/dev/null; then
  echo "Broken links:"
  obsidian $VAULT_FLAG unresolved verbose
  echo ""
fi

echo "📊 Top 10 tags:"
obsidian $VAULT_FLAG tags counts sort=count | head -10
echo ""

# Memory-specific checks
echo "📂 Memory folder files:"
obsidian $VAULT_FLAG files folder=memory total
echo ""

echo "🔍 Backlinks to working-context:"
obsidian $VAULT_FLAG backlinks path="memory/working-context.md" total
```

### Interpreting results

| Metric | Healthy range | Action if high |
|--------|--------------|----------------|
| Orphans | <30% of total files | Review — some are fine (daily notes), but memory files should have links |
| Dead ends | <40% of total files | Add outgoing links to isolated notes |
| Unresolved | 0 | Fix broken links immediately — they indicate moved/deleted files |
| Top tags | Even distribution | If one tag dominates, consider splitting it into subtags |

---

## Recipe 2: Property sweep

**What it does:** Lets you inspect `last_reviewed` / `relevance` and update them selectively after real review — without opening each file.

**When to run:** After a maintenance session, or when you've semantically reviewed a specific note and want to record that fact.

### Individual commands

```bash
# Read a property
obsidian property:read name=last_reviewed path="memory/glossary.md"
# → 2026-03-23

# After semantically reviewing the file, update last_reviewed to today
obsidian property:set name=last_reviewed value=2026-03-24 path="memory/glossary.md"

# Check relevance
obsidian property:read name=relevance path="memory/people/valeria.md"

# Downgrade relevance
obsidian property:set name=relevance value=medium path="memory/projects/old-project.md"
```

### Safe pattern — do not batch-refresh `last_reviewed`

> [!WARNING] Avoid the common anti-pattern
> Don't set `last_reviewed` across every file in `memory/` just because you ran an audit. That turns the field into a maintenance timestamp instead of a semantic freshness signal.

Use the stale-file script below to generate a review queue. Then, after checking a file, update it explicitly:

```bash
obsidian property:set name=last_reviewed value=2026-03-24 path="memory/glossary.md"
```

### Targeted sweep — only files not reviewed in N days

```bash
#!/bin/bash
# memory-stale.sh — Find memory files with last_reviewed older than N days
# Usage: ./memory-stale.sh [days] [vault-name]
# Default: 30 days

export PATH="$PATH:/Applications/Obsidian.app/Contents/MacOS"

DAYS="${1:-30}"
VAULT="${2:-}"
VAULT_FLAG=""
[[ -n "$VAULT" ]] && VAULT_FLAG="vault=$VAULT"

CUTOFF=$(date -v-${DAYS}d +%Y-%m-%d 2>/dev/null || date -d "$DAYS days ago" +%Y-%m-%d)

echo "📅 Files in memory/ with last_reviewed before $CUTOFF ($DAYS+ days old)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

FILES=$(obsidian $VAULT_FLAG files folder=memory ext=md 2>&1)

while IFS= read -r filepath; do
  [[ -z "$filepath" ]] && continue

  REVIEWED=$(obsidian $VAULT_FLAG property:read name=last_reviewed path="$filepath" 2>&1)
  [[ -z "$REVIEWED" ]] && continue
  [[ "$REVIEWED" == *"not found"* ]] && continue

  if [[ "$REVIEWED" < "$CUTOFF" ]]; then
    RELEVANCE=$(obsidian $VAULT_FLAG property:read name=relevance path="$filepath" 2>&1)
    echo "  ⏰ $filepath — last: $REVIEWED — relevance: $RELEVANCE"
  fi
done <<< "$FILES"
```

---

## Recipe 3: Quick capture

**What it does:** Append content to memory files from the terminal without opening Obsidian's editor. Useful for session logs, quick notes, and task updates.

### Append to recent-sessions

```bash
obsidian append path="memory/recent-sessions.md" \
  content="| 2026-03-24 | Copilot | Memory system | Added CLI integration recipes to public guide |"
```

### Append to working-context

```bash
obsidian append path="memory/working-context.md" \
  content="\n- **New thread:** Obsidian CLI integration documented (DEC-014)"
```

### Create a new pulse entry

```bash
obsidian create path="memory/pulse/2026-03-24.md" \
  content="---\ndate: 2026-03-24\ntype: pulse\nweek: 13\n---\n\n# Pulse — 2026-03-24\n" \
  open
```

### Create a new decision file

```bash
obsidian create path="memory/decisions/DEC-014.md" \
  content="---\ntitle: Decision title\ndate: 2026-03-24\nstatus: Aceptada\n---\n\n# DEC-014 — Decision title\n" \
  open
```

### Search memory for context before a session

```bash
# Find files mentioning a person
obsidian search:context query="Héctor" path=memory

# Find all decisions
obsidian search query="DEC-" path=memory/decisions

# Read a specific file
obsidian read path="memory/working-context.md"
```

### Mark a task as done

```bash
# List tasks with line numbers
obsidian tasks path="TASKS.md" todo verbose

# Toggle a specific task
obsidian task path="TASKS.md" line=3 done
```

---

## Reference: useful commands for memory systems

| Command | What it does | Memory use case |
|---------|-------------|-----------------|
| `obsidian read path=<file>` | Read file contents | Load any memory file |
| `obsidian create path=<file> content=<text>` | Create a file | New pulse entry, decision, person |
| `obsidian append path=<file> content=<text>` | Append to file | Session log, working-context updates |
| `obsidian search:context query=<text> path=<folder>` | Search with line context | Find references in memory |
| `obsidian property:read name=<prop> path=<file>` | Read frontmatter property | Check last_reviewed, relevance |
| `obsidian property:set name=<prop> value=<val> path=<file>` | Set frontmatter property | Update last_reviewed, change relevance |
| `obsidian orphans` | Files with no incoming links | Find disconnected notes |
| `obsidian deadends` | Files with no outgoing links | Find stub notes |
| `obsidian unresolved` | Broken wikilinks | Fix link rot |
| `obsidian backlinks path=<file>` | Incoming links to a file | Check how connected a note is |
| `obsidian links path=<file>` | Outgoing links from a file | Verify a note links to what it should |
| `obsidian tags counts sort=count` | Tag distribution | Audit taxonomy health |
| `obsidian tasks todo` | List pending tasks | Quick task overview |
| `obsidian task path=<file> line=<n> done` | Complete a task | Mark tasks from terminal |
| `obsidian rename path=<old> name=<new>` | Rename (updates wikilinks) | Safe file renames |
| `obsidian move path=<file> to=<folder>` | Move (updates wikilinks) | Reorganize without breaking links |
| `obsidian eval code="<js>"` | Run JavaScript in Obsidian | Advanced queries via `app.vault` API |

### Power move: `eval` for complex queries

```bash
# Count memory files by subfolder
obsidian eval code="
  const files = app.vault.getFiles().filter(f => f.path.startsWith('memory/'));
  const byFolder = {};
  files.forEach(f => {
    const folder = f.path.split('/').slice(0,2).join('/');
    byFolder[folder] = (byFolder[folder] || 0) + 1;
  });
  JSON.stringify(byFolder, null, 2);
"

# Find files in memory/ not modified in 30 days
obsidian eval code="
  const cutoff = Date.now() - 30*24*60*60*1000;
  app.vault.getFiles()
    .filter(f => f.path.startsWith('memory/') && f.stat.mtime < cutoff)
    .map(f => f.path)
    .join('\n');
"
```

---

## Limitations

- **Obsidian must be running.** The CLI connects to the app process. For headless automation (CI, cron jobs without GUI), use direct file I/O or GitHub API instead. Obsidian offers a separate [Headless mode](https://obsidian.md/help/cli) for sync-only workflows.
- **Local only.** The CLI doesn't work remotely. For phone access, see the Memory Shortcut pattern in [optional-ideas.md](optional-ideas.md).
- **Early access feature.** As of March 2026, CLI requires Obsidian 1.12+ which is in early access. Commands and behavior may change.
- **One vault at a time** (default). Use `vault=<name>` to target a specific vault if you have multiple.

---

## Integration with AI sessions

The CLI is most powerful when combined with an AI assistant that can run shell commands (Claude Code, Copilot CLI, Cursor, etc.). Instead of the AI reading files one by one:

```
# AI runs this at session start instead of reading 5 files:
obsidian search:context query="active" path=memory/working-context.md
obsidian tasks path="TASKS.md" todo
obsidian property:read name=last_reviewed path="memory/working-context.md"
```

For AI tools that can't run shell commands (Claude.ai, ChatGPT web), the CLI doesn't help directly — but you can run the audit script yourself and paste the output into the conversation.

### Example: AI-driven maintenance session

An AI with shell access can run a complete audit in one turn:

```bash
# 1. Health check
obsidian orphans total && obsidian unresolved total

# 2. Find stale files
obsidian eval code="
  const cutoff = Date.now() - 30*24*60*60*1000;
  app.vault.getFiles()
    .filter(f => f.path.startsWith('memory/') && f.stat.mtime < cutoff)
    .map(f => f.path).join('\n');
"

# 3. Update reviewed dates after checking each file
obsidian property:set name=last_reviewed value=2026-03-24 path="memory/glossary.md"
```

This replaces the manual "open each file, check the date, edit the frontmatter" loop that makes maintenance tedious.

---

*See also: [guide.md](guide.md) for the full memory system architecture, [optional-ideas.md](optional-ideas.md) for more extensions, [plugin-guide.md](plugin-guide.md) for Claude Desktop integration.*
