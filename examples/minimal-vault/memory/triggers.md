# Triggers

Formalized rules for reactive file loading and proactive memory writing. The AI consults this file when it detects keywords or signals in the conversation.

## Loading triggers

When to load Tier 2 files automatically during conversation.

| Keywords / signal | Files to load | Suggested mode |
|---|---|---|
| Marcus, scientific illustration, Rijksmuseum | `people/marcus-hoekstra.md` | — |
| Dr. Petrov, Hermitage, lapis lazuli | `people/sofia-petrov.md` | — |
| Concordance, pigment, recipe, spectroscopy | `projects/concordance.md` | research |
| Cranach, Gallery 5, condition survey | `projects/gallery-work.md` | — |
| Strata, blog, micro.blog, post | — | writing |
| Strasbourg MS, manuscript, treatise | `projects/concordance.md`, Research/ ContextSummary | research |
| what did we decide, why this way, decision | `decisions/` | — |
| continue, catch up, last session | `recent-sessions.md` | — |

## Writing triggers

When to propose updating memory files during conversation.

| Signal detected | Action | Confirmation |
|---|---|---|
| New fact about a person | Propose adding to `people/[name].md` | Ask first |
| Decision made with rationale | Propose new DEC- entry in `decisions/` | Ask first |
| Project status changed | Propose updating `projects/[project].md` | Ask first |
| New term or codename introduced | Propose adding to `glossary.md` | Ask first |
| Task completed or created | Update `TASKS.md` directly | **No confirmation needed** |

> "Propose" means: state what would be updated and where, then do it if the user confirms. For `TASKS.md`, just do it.

## How to use this file

- The AI consults it implicitly when processing messages
- No need to read it fully at session start — knowing it exists is enough
- Update when new people, projects, or conventions are added

## Related

- [[memory/modes|Interaction modes]] — modes referenced in the "Suggested mode" column
- [[memory/glossary|glossary]] — internal vocabulary
- [[memory/ContextSummary|ContextSummary — Memory]] — operational index
