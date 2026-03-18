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

*Have an idea for this list? Open an issue or PR on [obsidian-memory-for-ai](https://github.com/jrcruciani/obsidian-memory-for-ai).*
