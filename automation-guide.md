# Automating Memory Maintenance

## How to build agents that maintain your memory system without manual intervention

> **Prerequisites:** You already have a working memory system following the [main guide](guide.md). You understand the update protocol, proactive triggers, and maintenance cadence. You want a script — not a conversation — to handle some of that work.

---

## The problem this solves

The memory system described in the guide works well, but it depends on discipline. At the end of every session, someone needs to:

1. Rewrite `working-context.md` with the new state
2. Append a line to `recent-sessions.md`
3. Update `TASKS.md` with completed or new tasks
4. Propagate changes to `people/`, `projects/`, `decisions/` if relevant
5. Update `last_reviewed` only on files actually reviewed or changed

When you're inside a conversation with the AI, you can ask it to do this. But if you forget, the memory drifts. And for periodic maintenance — monthly audits, stale file detection, orphan link hunting — you need to remember to schedule it yourself.

This guide shows how to build a small agent that does these things as a standalone script. You run it from the terminal after a session (or on a cron job), and it updates your vault without needing an open chat.

---

## Two approaches, same goal

There are two practical ways to build this:

| Approach | What it is | Best for |
|----------|-----------|----------|
| **Anthropic API + tool use** | Direct API calls to Claude with file-system tools you define | Full control, no extra dependencies, works with any Claude model |
| **GitHub Copilot SDK** | GitHub's agentic SDK that wraps a battle-tested execution loop | Less code to write, built-in filesystem tools, multi-model routing |

Both produce the same result: an agent that reads your vault, reasons about what changed, and writes updated files. The difference is how much plumbing you write yourself.

**Which to choose:**

- If you already have an Anthropic API key and want minimal dependencies → **Anthropic API**
- If you have a GitHub Copilot subscription and prefer a pre-built agentic loop → **Copilot SDK**
- If you want maximum portability and no vendor lock-in → **Anthropic API** (the SDK requires Copilot CLI as a subprocess)

---

## Approach 1: Anthropic API with tool use

### Concept

You define file-system tools (`read_file`, `write_file`, `list_directory`) and pass them to the Claude API alongside instructions for the update protocol. Claude plans the steps, calls the tools, and you execute them locally. The conversation loop runs in your script — no chat UI needed.

### Dependencies

```bash
pip install anthropic
```

### The agent script

```python
#!/usr/bin/env python3
"""
memory-agent.py — Automated memory maintenance for Obsidian vaults.

Usage:
    python memory-agent.py update --vault ~/path/to/vault
    python memory-agent.py update --vault ~/path/to/vault --transcript session.txt
    python memory-agent.py audit  --vault ~/path/to/vault --level monthly
"""

import argparse
import json
from pathlib import Path
from anthropic import Anthropic

client = Anthropic()  # reads ANTHROPIC_API_KEY from environment

# --- Tool definitions ---

TOOLS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file relative to the vault root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to vault root (e.g. 'memory/working-context.md')"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Write content to a file relative to the vault root. Creates the file if it doesn't exist. Overwrites if it does.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to vault root"
                },
                "content": {
                    "type": "string",
                    "description": "Complete file content to write"
                }
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "list_directory",
        "description": "List files and subdirectories in a directory relative to the vault root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path relative to vault root (e.g. 'memory/people')"
                }
            },
            "required": ["path"]
        }
    }
]


def execute_tool(tool_name: str, tool_input: dict, vault_path: Path) -> str:
    """Execute a tool call and return the result as a string."""
    target = vault_path / tool_input["path"]

    if tool_name == "read_file":
        if not target.is_file():
            return f"Error: file not found: {tool_input['path']}"
        return target.read_text(encoding="utf-8")

    elif tool_name == "write_file":
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(tool_input["content"], encoding="utf-8")
        return f"Written: {tool_input['path']} ({len(tool_input['content'])} chars)"

    elif tool_name == "list_directory":
        if not target.is_dir():
            return f"Error: directory not found: {tool_input['path']}"
        entries = sorted(target.iterdir())
        return "\n".join(
            f"{'[DIR]' if e.is_dir() else '[FILE]'} {e.name}" for e in entries
        )

    return f"Error: unknown tool {tool_name}"


def build_update_prompt(transcript: str | None) -> str:
    """Build the system prompt for a memory update run."""
    base = """You are a memory maintenance agent for an Obsidian-based AI memory system.

Your job is to update the vault's memory files to reflect the current state.

## Loading sequence
1. Read memory/ContextSummary.md to understand the vault structure
2. Read memory/working-context.md for current state
3. Read memory/recent-sessions.md for recent history
4. Read TASKS.md for current tasks

## Update protocol
After understanding the current state, update these files:
1. memory/working-context.md — rewrite to reflect the current state
2. memory/recent-sessions.md — append a one-line entry if a session transcript is provided
3. TASKS.md — mark completed tasks, add new ones if mentioned
4. Any memory/ files (people, projects, decisions) that need updates
5. Update last_reviewed dates in YAML frontmatter of touched files — only when they were semantically reviewed or changed

## Rules
- Keep working-context.md under 40 lines. Facts, not narrative.
- recent-sessions.md is capped at ~10 entries. Drop the oldest if needed.
- Only update files where you have concrete information to add. Don't invent.
- Treat last_reviewed as a semantic-validation date, not a batch-audit stamp.
- Preserve existing YAML frontmatter structure.
- Preserve wikilink syntax ([[note]]) in all files.
- Report what you changed at the end.
"""
    if transcript:
        base += f"\n## Session transcript to process\n\n{transcript}\n"
    else:
        base += "\n## Mode: refresh\nNo transcript provided. Read the current state and verify consistency. Do not bulk-refresh last_reviewed; only update it on files you semantically validate or change.\n"

    return base


def build_audit_prompt(level: str) -> str:
    """Build the system prompt for a maintenance audit."""
    return f"""You are a memory maintenance agent for an Obsidian-based AI memory system.

Your job is to audit the vault's memory files and report issues.

## Audit level: {level}

{"## Monthly audit scope" if level == "monthly" else "## Quarterly audit scope"}

{"Scan all memory/ files. For each file:" if level == "monthly" else "Scan the entire vault. For each file:"}
1. Check if last_reviewed is older than {"30 days" if level == "monthly" else "90 days"} — flag as stale. Treat it as a semantic-validation date, not an audit timestamp.
2. Check if relevance is still accurate based on content
3. Look for redundant content across files
4. Verify that ContextSummary.md matches the actual directory structure
5. Check glossary.md for terms that appear in conversations but aren't registered
{"6. Find orphan notes (no incoming or outgoing wikilinks)" if level == "quarterly" else ""}
{"7. Check if CLAUDE.md is under 800 lines" if level == "quarterly" else ""}
{"8. Review decision coverage — any recent structural changes without a DEC- entry?" if level == "quarterly" else ""}

## Output format
Produce a structured report with severity levels:
- CRITICAL: something is broken or misleading
- WARNING: something is stale or inconsistent
- INFO: suggestion for improvement

Do NOT make changes. Only report findings. The user will decide what to fix.
"""


def run_agent(system_prompt: str, vault_path: Path, max_turns: int = 20):
    """Run the agentic loop: send messages, execute tools, repeat until done."""
    messages = [{"role": "user", "content": "Begin."}]

    for turn in range(max_turns):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

        # Collect tool calls and text from the response
        tool_calls = []
        text_parts = []

        for block in response.content:
            if block.type == "tool_use":
                tool_calls.append(block)
            elif block.type == "text":
                text_parts.append(block.text)

        # Add assistant response to history
        messages.append({"role": "assistant", "content": response.content})

        # If no tool calls, the agent is done
        if not tool_calls:
            final_text = "\n".join(text_parts)
            print(f"\n{'='*60}")
            print("Agent completed. Summary:")
            print(f"{'='*60}")
            print(final_text)
            return final_text

        # Execute tools and collect results
        tool_results = []
        for tc in tool_calls:
            print(f"  → {tc.name}({tc.input.get('path', '')})")
            result = execute_tool(tc.name, tc.input, vault_path)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

    print("Warning: max turns reached.")


def main():
    parser = argparse.ArgumentParser(description="Obsidian memory maintenance agent")
    parser.add_argument("action", choices=["update", "audit"])
    parser.add_argument("--vault", required=True, help="Path to Obsidian vault root")
    parser.add_argument("--transcript", help="Path to session transcript file (for update)")
    parser.add_argument("--level", default="monthly", choices=["monthly", "quarterly"],
                        help="Audit level (for audit action)")
    args = parser.parse_args()

    vault_path = Path(args.vault).expanduser().resolve()
    if not vault_path.is_dir():
        print(f"Error: vault path not found: {vault_path}")
        return

    if args.action == "update":
        transcript = None
        if args.transcript:
            transcript = Path(args.transcript).read_text(encoding="utf-8")
        prompt = build_update_prompt(transcript)
        run_agent(prompt, vault_path)

    elif args.action == "audit":
        prompt = build_audit_prompt(args.level)
        run_agent(prompt, vault_path)


if __name__ == "__main__":
    main()
```

### Usage

```bash
# Set your API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Update memory after a session (with transcript)
python memory-agent.py update --vault ~/obsidian/my-vault --transcript session.txt

# Update memory (refresh mode — no transcript, just verify consistency)
python memory-agent.py update --vault ~/obsidian/my-vault

# Monthly audit
python memory-agent.py audit --vault ~/obsidian/my-vault --level monthly

# Quarterly structural review
python memory-agent.py audit --vault ~/obsidian/my-vault --level quarterly
```

### How to get a session transcript

Most AI tools don't export transcripts natively. A few options:

- **Claude Code:** The conversation is stored locally. Check `~/.claude/` for session files.
- **Claude Desktop (Cowork):** No built-in export yet. Copy-paste is the pragmatic option.
- **Manual summary:** Instead of a full transcript, write a 5-line summary of what happened and what changed. The agent works with either.

### What the agent does on each run

```
$ python memory-agent.py update --vault ~/vault --transcript today.txt

  → read_file(memory/ContextSummary.md)
  → read_file(memory/working-context.md)
  → read_file(memory/recent-sessions.md)
  → read_file(TASKS.md)
  → read_file(memory/glossary.md)
  → read_file(memory/projects/wine-academy.md)
  → write_file(memory/working-context.md)
  → write_file(memory/recent-sessions.md)
  → write_file(TASKS.md)

============================================================
Agent completed. Summary:
============================================================
Updated 3 files:
- working-context.md: added Wine Academy MVP discussion to active focus
- recent-sessions.md: appended today's session entry
- TASKS.md: marked "review competitors" as completed
```

### Cost

At Sonnet pricing (~$3/M input, ~$15/M output as of March 2026), a typical update run reads ~3,000 tokens and writes ~1,500 tokens. That's roughly **$0.03 per run**. An audit reads more files but still stays under $0.10. At daily usage, expect ~$1/month.

---

## Approach 2: GitHub Copilot SDK

### Concept

The [Copilot SDK](https://github.com/github/copilot-sdk) (technical preview, January 2026) wraps the same agentic engine that powers Copilot CLI — planning, tool execution, error recovery, multi-step reasoning — and exposes it as a library. Instead of writing the agentic loop yourself, you configure the SDK and let it handle orchestration.

The SDK communicates with Copilot CLI running in server mode via JSON-RPC. It manages the CLI process lifecycle automatically.

### Requirements

- A GitHub Copilot subscription (Individual, Business, or Enterprise), **or** use BYOK (Bring Your Own Key) mode with your own API key (Anthropic, OpenAI, Azure, etc.)
- Node.js 18+ or Python 3.10+
- Copilot CLI installed (`gh extension install github/gh-copilot`)

### Dependencies

```bash
pip install github-copilot-sdk
```

### The agent script

```python
#!/usr/bin/env python3
"""
memory-agent-sdk.py — Memory maintenance using GitHub Copilot SDK.

Usage:
    python memory-agent-sdk.py update --vault ~/path/to/vault
    python memory-agent-sdk.py audit  --vault ~/path/to/vault --level monthly
"""

import argparse
from pathlib import Path
from copilot_sdk import CopilotClient, AgentConfig

def build_update_instructions(vault_path: str, transcript: str | None) -> str:
    """Build instructions for the update agent."""
    base = f"""You are a memory maintenance agent.

Working directory: {vault_path}

## Task: update memory files

1. Read memory/ContextSummary.md to understand the vault structure.
2. Read memory/working-context.md, memory/recent-sessions.md, and TASKS.md.
3. Based on the current state{" and the session transcript below" if transcript else ""},
   update the files following the update protocol:
   - Rewrite working-context.md (keep under 40 lines, facts not narrative)
   - Append to recent-sessions.md (cap at ~10 entries)
   - Update TASKS.md (mark completed, add new)
   - Update any relevant people/, projects/, or decisions/ files
   - Update last_reviewed dates in YAML frontmatter only for files semantically reviewed or changed
4. Report what you changed.

Preserve wikilink syntax ([[note]]) in all files.
"""
    if transcript:
        base += f"\n## Session transcript\n\n{transcript}\n"
    return base


def build_audit_instructions(vault_path: str, level: str) -> str:
    """Build instructions for the audit agent."""
    return f"""You are a memory maintenance agent.

Working directory: {vault_path}

## Task: {level} audit

Scan all files in memory/. For each file:
1. Check if last_reviewed is older than {"30" if level == "monthly" else "90"} days. Treat it as a semantic-validation date, not an audit timestamp.
2. Verify relevance is accurate
3. Look for redundant content across files
4. Check ContextSummary.md matches actual structure
{"5. Find orphan notes with no wikilinks" if level == "quarterly" else ""}

Output a structured report: CRITICAL / WARNING / INFO.
Do NOT modify any files. Report only.
"""


def run(action: str, vault_path: Path, transcript: str | None = None,
        level: str = "monthly"):
    """Run the Copilot SDK agent."""

    config = AgentConfig(
        working_directory=str(vault_path),
        # BYOK: use your own Anthropic key instead of Copilot subscription
        # model_provider="anthropic",
        # model="claude-sonnet-4-6",
    )

    client = CopilotClient(config)

    if action == "update":
        instructions = build_update_instructions(str(vault_path), transcript)
    else:
        instructions = build_audit_instructions(str(vault_path), level)

    # The SDK handles the full agentic loop:
    # planning, tool calls, error recovery, multi-turn reasoning
    result = client.run(instructions)

    print(f"\n{'='*60}")
    print(f"Agent completed ({result.turns} turns, {result.tool_calls} tool calls)")
    print(f"{'='*60}")
    print(result.final_message)


def main():
    parser = argparse.ArgumentParser(description="Memory maintenance (Copilot SDK)")
    parser.add_argument("action", choices=["update", "audit"])
    parser.add_argument("--vault", required=True)
    parser.add_argument("--transcript")
    parser.add_argument("--level", default="monthly", choices=["monthly", "quarterly"])
    args = parser.parse_args()

    vault_path = Path(args.vault).expanduser().resolve()

    transcript = None
    if args.transcript:
        transcript = Path(args.transcript).read_text(encoding="utf-8")

    run(args.action, vault_path, transcript, args.level)


if __name__ == "__main__":
    main()
```

### Key differences from the direct API approach

| Aspect | Anthropic API | Copilot SDK |
|--------|--------------|-------------|
| **Agentic loop** | You write it (the `for turn in range` loop) | SDK handles it internally |
| **Tool definitions** | You define them in JSON and write executors | Filesystem tools are built-in; you can add custom ones |
| **Error recovery** | You implement retry logic | SDK retries and re-plans on failure |
| **Auth** | Anthropic API key | GitHub OAuth, or BYOK with your own key |
| **Model choice** | Any Claude model directly | Default is Copilot's model; BYOK lets you choose |
| **Process model** | Pure Python, no subprocesses | Copilot CLI runs as a subprocess in server mode |
| **Billing** | Anthropic API usage | Copilot premium request quota (or BYOK) |

### When the SDK adds real value

The SDK's advantage is not in what it *can* do — both approaches achieve the same result. The advantage is in what you *don't have to build*:

- **Multi-step planning.** The SDK breaks complex instructions into steps, executes them in order, and adjusts the plan if a step fails. With the direct API, your loop handles this implicitly but less gracefully.
- **Built-in filesystem tools.** Read, write, list, search, git operations — all available without defining tool schemas.
- **Streaming.** The SDK supports real-time streaming of agent progress, useful if you want to build a UI around it.

For a vault with 50–200 files and straightforward update logic, the difference is marginal. For more complex maintenance tasks — say, a quarterly audit that needs to read dozens of files, cross-reference wikilinks, and generate a structured report — the SDK's built-in orchestration saves you from writing brittle loop logic.

---

## Running on a schedule

Either approach works as a cron job or launchd agent.

### Cron (Linux/Mac)

```bash
# Run a consistency check every Sunday at 9am
0 9 * * 0 cd ~/scripts && python memory-agent.py update --vault ~/obsidian/my-vault >> ~/logs/memory-agent.log 2>&1

# Monthly audit on the 1st at 10am
0 10 1 * * cd ~/scripts && python memory-agent.py audit --vault ~/obsidian/my-vault --level monthly >> ~/logs/memory-audit.log 2>&1
```

### macOS launchd

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.memory-agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/you/scripts/memory-agent.py</string>
        <string>update</string>
        <string>--vault</string>
        <string>/Users/you/obsidian/my-vault</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
        <key>Weekday</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/you/logs/memory-agent.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/you/logs/memory-agent.log</string>
</dict>
</plist>
```

Save as `~/Library/LaunchAgents/com.user.memory-agent.plist` and load with `launchctl load`.

---

## Safety considerations

An automated agent writing to your vault needs guardrails:

- **Git as a safety net.** If your vault is a git repo (it should be), you can always `git diff` after a run to review changes, and `git checkout -- .` to revert if something went wrong.
- **Dry run mode.** Modify the `write_file` tool to print changes instead of writing them. Add a `--dry-run` flag to the script.
- **File whitelist.** Limit which files the agent can write to. For routine updates, it only needs: `working-context.md`, `recent-sessions.md`, `TASKS.md`, and files in `memory/`. It should never touch `CLAUDE.md` or content folders without explicit permission.
- **Length guards.** Reject writes where the new content is less than 50% of the original file length — this catches cases where the agent accidentally truncates a file.
- **No deletion.** The agent should never delete files. Only write and overwrite.

---

## Comparison with the plugin approach

The [plugin guide](plugin-guide.md) describes how to package the memory system as a Cowork plugin with slash commands. That approach runs *inside* a conversation — you say `/memory-update` and the AI updates files as part of the chat.

The automation approach described here runs *outside* a conversation — a script that updates files independently. They complement each other:

| | Plugin (in-conversation) | Agent script (standalone) |
|---|---|---|
| **When** | During a chat session | After a session, or on a schedule |
| **Context** | Has the full conversation history | Needs a transcript or works from file state |
| **Interaction** | Interactive — can ask clarifying questions | Autonomous — runs to completion |
| **Best for** | Session-end updates with full context | Scheduled maintenance, consistency checks, catch-up |

The recommended workflow: use the plugin during sessions for real-time updates, and run the agent script periodically to catch anything that slipped through.

---

## Extending the agent

Once you have the basic agent working, natural extensions include:

- **Wikilink validation.** Check that all `[[wikilinks]]` in memory files resolve to actual files. Report broken links.
- **Glossary sync.** Scan recent session transcripts for repeated terms that aren't in `glossary.md` yet.
- **Decision detection.** Parse transcripts for phrases that signal decisions ("let's go with", "decided to", "from now on") and propose DEC- entries.
- **Relevance decay.** Automatically downgrade `relevance: high` to `medium` for files whose `last_reviewed` is older than 60 days, and `medium` to `low` after 120 days. Flag `low` relevance files for archival.
- **Cross-file consistency.** Verify that project status in `projects/` matches what `working-context.md` says, and that people mentioned in `working-context.md` have corresponding files in `people/`.

---

*Have ideas for improving the automation? Open an issue or PR on [obsidian-memory-for-ai](https://github.com/jrcruciani/obsidian-memory-for-ai).*
