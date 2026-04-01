# ContextSummary — Memory

## Always load
- `glossary.md` — internal vocabulary and acronyms
- `context/professional.md` — role, lab setup, institutional context
- `context/personality.md` — how I work and how the AI should adapt
- `working-context.md` — current state snapshot (updated each session)

## Reactive loading and interaction modes
- `triggers.md` — formalized rules for when to load Tier 2 files and when to propose memory updates (keyword → file + mode)
- `modes.md` — interaction modes (research, writing, conservation, default) that calibrate AI tone and behavior. Activated by triggers or with `/mode [name]`

## Load on demand
- Consult `triggers.md` for the detailed keyword → file mapping
- `people/` — when a person is mentioned by name or nickname
- `projects/` — when a project is mentioned by codename
- `decisions/` — when the question is about *why* something was changed
- `recent-sessions.md` — when continuing prior work or catching up on recent activity

## Recent structural changes
- 2026-04-01: Added triggers.md and modes.md (DEC-016, inspired by Open-Her OS lorebook)
- 2026-03-17: Added working-context.md and recent-sessions.md (MemGPT-inspired)
- 2026-03-16: Added decision DEC-001 (Concordance data format)
- 2026-03-15: Initial memory system created
