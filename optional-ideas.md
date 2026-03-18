# Optional Ideas

> Extras you can add to your memory system. None of these are required — think of them as house rules for a board game. Pick what fits your workflow, ignore the rest.

---

## 🔭 Horizon Strip — Visual task + event timeline at session start

**What it does:** Generates a compact visual timeline at the beginning of every memory load, showing your upcoming tasks *and* time-blocked events (trips, deadlines, meetings) sorted by date. You see at a glance what's urgent and when you're actually available.

**Why it's useful:** A flat task list hides availability. If you have 4 tasks due "next week" but you're traveling all week, that context is invisible. The horizon strip interleaves tasks with time blocks so the AI (and you) can gauge real urgency.

**Example output:**
```
📋 HORIZON — 18 Mar 2026
──────────────────────────────────────────────────
🔴  1d   📌 Dentist appointment · 19/3 10:00
🟠  2d   🚗 Weekend trip to coast (20–22) ······
🟡  4d   📌 Call accountant · 22/3
🟡  5d   ✈️ Work trip Brussels (23–25) ··········
            📌 Submit expense report · 23/3
🟡  8d   📌 Renew passport · 26/3
🟢  9d   🚗 Easter road trip (27/3–6/4) ········
            📌 Pay rent · 1/4
🟢 20d   ✈️ Family visit Lima (7–15/4) ·········
            📌 Schedule meeting · 10/4
──────────────────────────────────────────────────
          +3 future · 2 someday
```

**Color scheme:**
| Emoji | Days until event | Meaning |
|-------|-----------------|---------|
| 🔴 | 0–2 days | Immediate |
| 🟠 | 3–4 days | This week |
| 🟡 | 5–9 days | Next week |
| 🟢 | 10+ days | Comfortable |

**Design rules:**
- **Tasks** appear with 📌 and their due date
- **Trips/events** appear as context blocks with transport emoji (🚗 car, ✈️ flight, 🏢 office) and trailing dots `···` to signal duration
- **Tasks during a trip** are indented under the trip — this shows what you need to handle while traveling
- **Tasks outside trips** stay at root level — these are your "free day" tasks
- Only show items within the next ~30 days
- Items beyond 30 days and "someday" items are collapsed into a count line

**How to implement:**

1. **Create a travel/events file** (e.g., `memory/travel.md` or `memory/events.md`) that lists upcoming time blocks with date ranges:
   ```markdown
   ## Coast weekend
   - Dates: 20–22 March 2026
   - Transport: car
   
   ## Work trip Brussels
   - Dates: 23–25 March 2026
   - Transport: flight
   ```

2. **Modify your memory-load command** to also read `TASKS.md` + your events file, then instruct the AI to generate the horizon strip by:
   - Parsing all dated items from both sources
   - Calculating days-until for each
   - Sorting chronologically
   - Nesting tasks under overlapping trips
   - Applying the color scheme
   - Collapsing items beyond 30 days

3. **Add it to your load report** — place the horizon strip at the top of the memory-load output, before the context summary.

**Customization ideas:**
- Add more event types: 🏥 medical, 🎓 school, 🎉 social
- Change color thresholds to match your planning style
- Add recurring events from a `recurring.md` file
- Include a "free days" count: days in the next 30 not covered by any trip

---

## 📱 Memory Shortcut — Query your memory from your phone

**What it does:** A Cloudflare Worker that lets you query (and update) your Obsidian memory system from your phone using iOS Shortcuts, Android Tasker, or any HTTP client. Ask a question in natural language, get an answer grounded in your memory files — no apps to install.

**Why it's useful:** Your memory system lives on your computer, but questions pop up everywhere. "What do I have this week?", "When is that appointment?", "What was the decision about X?" — now you can ask from your phone and get an answer in seconds, even hands-free via Siri.

**Architecture:**
```
Phone (Shortcut / Tasker / HTTP)
    │
    │  POST /query   { "q": "What do I have this week?" }
    ▼
Cloudflare Worker (free tier)
    │
    ├─► GitHub API → reads .md files from a private repo
    │   (Tier 1 always, Tier 2 based on keywords in the question)
    │
    └─► Claude API → generates answer with loaded context
    │
    ▼
JSON response { "answer": "..." }
```

**How it works:**

1. **Your memory files live in a private GitHub repo.** You can either:
   - Initialize git directly in your vault with a `.gitignore` that only tracks `memory/` and your task file
   - Use a separate repo and sync periodically

2. **A Cloudflare Worker** receives questions and:
   - **Always loads Tier 1** files (glossary, personality, company context, working context)
   - **Detects keywords** in the question to load Tier 2 files:
     - People's names → their profile from `people/`
     - Project names → their file from `projects/`
     - Task-related words ("this week", "tasks", "appointments") → your task file
     - Decision-related words ("why did we", "when did we decide") → your decisions timeline
   - Sends the loaded context + question to Claude API
   - Returns a clean plain-text answer (Markdown stripped for voice assistants)

3. **Optionally, a `/update` endpoint** lets you modify memory from your phone:
   - "Add task: buy birthday gift for Maria, April 20" → updates your task file
   - "Note on Maria: prefers dark chocolate" → appends to the person's file
   - Safeguards: only whitelisted files are editable, content validation prevents corruption

**Setup overview:**

1. Push your memory files to a private GitHub repo
2. Deploy the Worker to Cloudflare (free tier is sufficient)
3. Set three secrets: `MEMORY_TOKEN` (random string you generate), `CLAUDE_API_KEY`, `GITHUB_TOKEN` (read-only PAT)
4. Create a Shortcut on your phone:
   - Ask for input → POST to Worker URL with auth header → Show result

**iOS Shortcut steps (Spanish UI: Atajos):**

| Step | Action | Config |
|------|--------|--------|
| 1 | Ask for Input | Prompt: "What do you want to ask?" |
| 2 | URL | `https://your-worker.workers.dev/query` |
| 3 | Get Contents of URL | POST, headers: `Content-Type: application/json` + `Authorization: Bearer <token>`, body JSON: key `q` → Provided Input |
| 4 | Get Dictionary Value | Key: `answer` |
| 5 | Show Result | Dictionary Value |

For voice mode: replace step 1 with **Dictate Text** and step 5 with **Speak Text**.

**Keeping memory in sync:**

If your vault is on a different machine than where you edit, you need sync between vault ↔ GitHub:
- **Simplest:** Initialize git in your vault root with a selective `.gitignore`. A cron job or launchd agent runs `git pull && git add -A && git commit && git push` every 30 minutes
- **Alternative:** Use Obsidian Git plugin if your vault is already a git repo
- Phone updates (via `/update`) arrive at the vault on the next pull cycle

**Keyword detection for Tier 2 loading:**

Map keywords to files in your Worker code. Example:

```javascript
const PEOPLE_MAP = {
  'maria': 'memory/people/maria.md',
  'john':  'memory/people/john.md',
};

const TASK_KEYWORDS = ['week', 'tasks', 'todo', 'pending', 'appointment'];
const DECISION_KEYWORDS = ['decided', 'decision', 'why did', 'when did'];
```

**Update endpoint safeguards:**
- Whitelist of editable files (e.g., only tasks and people files)
- People files: append-only (never rewrite)
- Task file: rewrite with Claude, but abort if result is <50% of original length
- Empty content is rejected

**Cost:** Effectively free for personal use — Cloudflare Workers free tier (100K requests/day), GitHub API (5K requests/hour), Claude Haiku (~$0.001 per query).

**Customization ideas:**
- Add a `/status` endpoint that returns your horizon strip or weekly summary without a question
- Cache Tier 1 files in Cloudflare KV with a 1-hour TTL to reduce GitHub API calls
- Add more action verbs for better task detection ("buy", "cancel", "book", "call")
- Support multiple languages in keyword detection
- Add a confirmation step for `/update` — return the proposed change and require a second call to confirm

---

## 💓 Pulse System — Structured emotional check-in

**What it does:** A weekly, structured emotional review that creates a persistent log of your internal state over time. Five canonical questions — designed to bypass automatic "I'm fine" responses — generate an entry that the AI stores and summarizes across sessions.

**Why it's useful:** Memory systems capture facts, projects, and decisions, but not how you actually feel. If your personality profile includes low emotional expressiveness (e.g., low Emotionality on HEXACO) combined with moderate anxiety, internal tension accumulates invisibly. Pulse creates a channel for naming what you don't name by default — not therapy, just structured registration.

**The five canonical questions:**

| # | Question | What it targets |
|---|----------|----------------|
| P1 | "What are you carrying this week that you haven't said out loud?" | Presupposes something exists — avoids "I'm fine" |
| P2 | "Was there something you wanted to do and didn't? Lack of time, energy, or something less clear?" | Non-linear execution pattern without framing it as failure |
| P3 | "Which project or task generated the most internal resistance? Do you know why?" | Resistance as disguised emotional signal |
| P4 | *(Rotating — see below)* | Relational awareness |
| P5 | "If this week were a mood, what would it be? One word or an image." | Intuitive capture beyond analysis |

**P4 rotation** — one relational question per week, cycling through three variants:

| `week_number % 3` | Question |
|--------------------|----------|
| 0 | "How's the dynamic with [partner] this week? Anything left unsaid?" |
| 1 | "How are things with [children/family]? Anything worrying or especially enjoyable?" |
| 2 | "Is anyone in your life (work, family, friends) occupying more mental space than usual?" |

**File structure:**

```
memory/
└── pulse/
    ├── README.md              ← canonical questions + rotation logic + AI protocol
    ├── YYYY-MM-DD.md          ← one entry per pulse session
    └── pulse-summary.md       ← rolling summary of last ~8 entries (Tier 2)
```

**Entry format:**

```markdown
---
date: 2026-03-23
type: pulse
week: 12
---

# Pulse — 2026-03-23

**P1 — What are you carrying this week that you haven't said out loud?**
[response]

**P2 — Was there something you wanted to do and didn't?**
[response]

**P3 — What generated the most internal resistance?**
[response]

**P4 — [this week's relational question]**
[response]

**P5 — If this week were a mood...**
[response]

---
*Free notes (optional):*
[anything that doesn't fit the questions]
```

**`pulse-summary.md`** — the file the AI loads in Tier 2 when emotional context matters:

```markdown
---
type: pulse-summary
last_updated: 2026-03-23
---

# Pulse summary — recent entries

## Observed trends
[2–4 lines on recurring patterns: persistent themes, resistances, improvements]

## Latest entry — 2026-03-23
[3–5 line summary]

## Previous entries (compressed)
| Date | General state | Main resistance | Relationships | Mood |
|------|--------------|-----------------|---------------|------|
| ...  | ...          | ...             | ...           | ...  |
```

**AI protocol for conducting a pulse session:**

1. Read `pulse/README.md` to determine which P4 is due based on the current week number.
2. Ask questions **one at a time** — wait for a response before continuing.
3. **Do not interpret or comment** during the session. Just listen and register. At the end, offer a brief synthesis only if the user wants it.
4. If the user responds with a single word or evasively, the AI may ask **one** follow-up question — but only one, and without insisting.
5. On close, create the entry file and update `pulse-summary.md` automatically — it's part of the protocol.

**Tone:** Direct, no therapeutic artifice. The user doesn't need validation or performative empathy — they need a space to name what they don't name by default.

**Frequency:** Weekly, preferably Sunday afternoon or Monday morning. Not before a stressful trip or event (the response will be biased). Duration: 5–8 minutes.

**How to integrate:**

1. **Create the file structure** (`memory/pulse/`, `README.md`, `pulse-summary.md`)
2. **Add to your memory index** — include `pulse/pulse-summary.md` in your Tier 2 loading criteria: *"load if the session touches emotional state, wellbeing, resistance to projects, burnout, or the user mentions how they feel"*
3. **Add proactive triggers** to your AI instruction file:
   - If the user mentions exhaustion, resistance, tension, or wellbeing → load `pulse-summary.md` before responding
   - If the user says `/pulse` or asks for the weekly review → read `pulse/README.md` and conduct the session
4. **Add to glossary** — `pulse` → structured weekly emotional review

**Design notes:**

- The questions are calibrated for someone with **low Emotionality + moderate Anxiety without external channels**. Adapt them if your profile is different.
- P4 rotation prevents the relational question from becoming routine and easy to answer on autopilot.
- The system **does not attempt therapy** — it attempts registration. That distinction matters for buy-in.
- If responses are consistently evasive across multiple sessions, that *is* data worth noting in the summary trends.

**Customization ideas:**
- Add a P6 for body/health awareness ("How's your body feeling this week?")
- Track a numeric energy score (1–10) alongside each entry for trend graphing
- Create a quarterly "pulse retrospective" that synthesizes patterns across ~12 entries
- Integrate with the Horizon Strip — show upcoming stressors next to the pulse prompt for context

---

*Have an idea for this list? Open an issue or PR on [obsidian-memory-for-ai](https://github.com/jrcruciani/obsidian-memory-for-ai).*
