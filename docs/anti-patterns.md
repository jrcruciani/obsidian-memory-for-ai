# Knowledge Factory Anti-Patterns & Failure Modes

Even with plain Markdown and strict schemas, poor operational habits degrade an AI knowledge base. Avoid these nine anti-patterns in v5.0 vaults.

---

## 1. Mid-Task Canonical Mutation by Executors
- **Anti-pattern:** Giving a task-executing coding or research agent `owner` credentials so it writes directly to `knowledge/facts/` or `knowledge/skills/` while solving a user prompt.
- **Why it fails:** Under task pressure, agents conflate temporary hypotheses with durable truth and skip verification steps.
- **Do instead:** Run task agents as `executor` (`direct_transact: false`), emit `capture signal` or `capture event`, and curate in a separate pass.

## 2. Hand-Editing `_generated/` Views or Indexes in Obsidian
- **Anti-pattern:** Editing `_generated/views/catalog.md` or `_generated/views/by-entity/elena-voss.md` directly in Obsidian.
- **Why it fails:** `_generated/` is a disposable projection; the next `kf.py rebuild` overwrites manual edits, and `kf.py lint --strict` immediately flags `content_sha256 mismatch`.
- **Do instead:** Propose changes to `knowledge/` or write free-form human commentary in `knowledge/notes/`.

## 3. Treating `knowledge/notes/` Prose as Hidden Truth
- **Anti-pattern:** Burying critical constraints, credentials, or role changes inside narrative paragraphs in `knowledge/notes/` without creating canonical `facts`, `skills`, or `guidance`.
- **Why it fails:** Deterministic queries and budgeted `bootstrap` read canonical structured records, not unstructured essays; `notes/` explicitly carries `authoritative: false`.
- **Do instead:** Keep human essays in `notes/`, and distill durable facts, procedures, and rules into `facts/`, `skills/`, and `guidance/`.

## 4. Polluting `factory/proposals/` With Unexecutable Placeholders
- **Anti-pattern:** Opening proposals with guessed dummy values or empty operations just to track an open question.
- **Why it fails:** Proposals represent candidate mutations ready for cryptographic review.
- **Do instead:** Record open questions, contradictions, and gaps as `signals` (`factory/signals/`).

## 5. Fabricating Numeric Confidence Scores
- **Anti-pattern:** Assigning `confidence: 0.95` to unverified inferences or mechanically mapping legacy `"high"` labels to `0.9`.
- **Why it fails:** Downstream `--min-confidence` filters treat fabricated numbers as calibrated certainty.
- **Do instead:** Leave `confidence: null` when unassessed, or score conservatively alongside explicit `derived_from` lineage.

## 6. Self-Approval via Identity Aliasing
- **Anti-pattern:** Having the same automated LLM pipeline call `propose create` as `agent-curator-00000003` and immediately call `review approve` as `agent-reviewer-00000002` in the same uninspected prompt without independent verification.
- **Why it fails:** Defeats the epistemic purpose of independent review even if IDs differ syntactically.
- **Do instead:** Bind `reviewer` / `owner` identities to human review or a genuinely independent verification harness checking raw `sources/`.

## 7. Treating External Sources as Executable Instructions (Prompt Injection)
- **Anti-pattern:** Ingesting web clips or vendor documents into `sources/` and letting a Curator copy imperative instructions inside them into `skills/` or `guidance/` without human review.
- **Why it fails:** Untrusted documents can smuggle adversarial tool instructions into `bootstrap-executor.md`.
- **Do instead:** Keep `external_requires_review: true` on all namespaces and require human `owner`/`reviewer` inspection before publishing `skills` or `guidance` derived from external inputs.

## 8. Mechanical `last_confirmed` Touching to Silence Staleness
- **Anti-pattern:** Running a batch script to bump `last_confirmed` on every stale fact or skill without checking whether the world changed.
- **Why it fails:** Destroys the signal value of `curate scan` and `_generated/views/stale.md`.
- **Do instead:** Use `confirm_fact` only after genuine human or primary-source verification.

## 9. Overwriting History Instead of Superseding
- **Anti-pattern:** Editing `knowledge/facts/{entity}/{pred}.md` or `knowledge/skills/{slug}.md` with a text editor when a value or procedure changes.
- **Why it fails:** Destroys `--as-of` temporal queries, breaks `supersedes` chains, and bypasses `factory/receipts/`.
- **Do instead:** Use `supersede_fact`, `supersede_skill`, `supersede_guidance`, or `supersede_decision`.
