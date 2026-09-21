# Decisions

- Work in the app-managed feature branch; do not rename it with Git. The
  attached brief's suggested branch name is superseded by the session's
  explicit branch-naming request.
- All implementation changes land in `examples/v4.1-minimal-vault/`.
  Preserve v3/v4 canonical files and tools. Add only an agent-guidance pointer
  to v4 if needed; never modify existing events or sources.
- `spec_version: "4.0"` keeps existing lint semantics. The new rules activate
  only for `"4.1"`.
- Keep legacy `confidence: high|medium|low` valid. Numeric confidence is
  optional; do not invent a numeric conversion for legacy labels.
- Keep `recorded_at`, `valid_to`, and `last_reviewed` valid. New observed time
  defaults to `created_at`, then the existing `recorded_at`. New validity
  uses half-open `[valid_from, valid_until)` windows; legacy `valid_to`
  retains its inclusive interpretation.
- A missing old `valid_from` uses the recorded date for a history filename,
  not as a fabricated validity assertion.
- Consolidation drafts describe issues, not guessed repairs. They have no
  executable operations until a person/agent supplies and reviews a fix.
- The optional LongMemEval adapter is deferred: external benchmark conversion
  is not needed for the deterministic protocol acceptance gate.
- Review and proposal application use the same recoverable publication path as
  fact writes. Review hashes bind proposer identity for new proposals, and
  apply counts actual authorized review records rather than an editable list.
- Staging is not a canonical query/view input. Missing/corrupt derived artifacts
  never change answers; corrupt/stale artifacts produce explicit diagnostics.
- The optional-ideas citation preserves the actual Letta result's caveat:
  its file-oriented experiment included semantic search. Do not claim it
  proves grep-only retrieval wins universally.
- The preserved v4 vault gets only an AGENTS navigation note. Its tools,
  canonical data, schemas, generated artifacts, and existing gates are intact.
