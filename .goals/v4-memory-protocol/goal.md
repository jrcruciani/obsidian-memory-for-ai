# Goal: Ship the v4 memory protocol

## User Request

Perfecto, trabaja en implementar los tres para hacer el bump a v4.0, manten el espiritu y la documentacion que tenemos en el repo.

The three agreed ideas are:

1. Robust Git-native transactions with expected revisions, idempotency, journals, recovery, and isolated staging.
2. A formal proposal and review lifecycle with roles, namespaces, and prevention of self-approval.
3. Deterministic rebuildable lexical and graph indexes with guaranteed filesystem fallback and optional accelerators.

## Refined Goal

Release a complete, documentation-first v4.0 protocol and reference vault that incorporates the three capabilities above without changing the project's core promise: Markdown/YAML and Git remain the only canonical state, and the vault remains usable offline without a daemon, database, model, network service, or binary index. Preserve the v3 implementation and migration path, add a v4 reference implementation with portable Python/Bash tooling, and prove the new behavior through deterministic regression tests and CI-equivalent validation.

## Acceptance Criteria

- [ ] Criterion 1: The repository presents v4.0 as the current stable protocol through a complete `SPEC-v4.md`, updated README/documentation map, and a v3-to-v4 migration guide; v3 documentation and the v3 reference vault remain available and are clearly identified as the previous stable generation.
- [ ] Criterion 2: A self-contained `examples/v4-minimal-vault/` demonstrates all v4 capabilities while preserving atomic facts, append-only events, typed YAML frontmatter, immutable sources, deterministic generated views, and the human/agent audience split.
- [ ] Criterion 3: V4 operations support atomic multi-operation transactions, stable transaction and idempotency identifiers, expected Git revision checks when Git is available, isolated staging before publication, Markdown journal/receipt records, and deterministic recovery after an interrupted or failed transaction. Replaying an already-applied idempotency key does not duplicate canonical changes or receipts. Any Git-integrated mode must refuse unsafe publication rather than overwrite unrelated or dirty work.
- [ ] Criterion 4: V4 proposals implement documented and schema-validated lifecycle states including draft/proposed, changes requested, approved, rejected, conflict, and applied. Reviews are durable Markdown/YAML records cryptographically bound to the reviewed proposal content. Namespace/role policy is stored in portable YAML, self-approval is rejected, unauthorized reviews are rejected, and compaction cannot apply a proposal until the configured policy is satisfied.
- [ ] Criterion 5: V4 provides deterministic, human-readable lexical and graph indexes derived entirely from canonical Markdown. Search and graph queries use valid indexes when available but return equivalent results through direct filesystem scanning when indexes are missing, stale, disabled, or corrupt. Deleting all indexes and rebuilding produces byte-identical output for the same canonical input.
- [ ] Criterion 6: Derived indexes, optional accelerators, Git integration, and review automation are never canonical or required for basic reads. No mandatory daemon, server, database, embedding model, remote API, Git LFS asset layer, or binary source of truth is introduced.
- [ ] Criterion 7: Tooling reports validation and operational failures explicitly, does not silently convert failures into success, does not rewrite immutable source files or append-only events, and maintains compatibility with Python 3.11 plus the repository's existing PyYAML-only runtime dependency.
- [ ] Criterion 8: Regression tests cover successful and failed transactions, idempotent replay, stale revision/CAS rejection, interrupted recovery, review approval and rejection, self-approval and namespace denial, deterministic index rebuilds, stale/corrupt/missing-index fallback parity, lint/schema validation, and v3 regression compatibility.
- [ ] Criterion 9: All repository quality gates pass: v3 lint and deterministic views, v4 lint and deterministic views/indexes, and the complete unittest suite. CI is updated to enforce both supported reference vaults and generated-artifact drift checks.

## Scope Boundaries

**In scope:**
- A new v4 protocol specification and migration/documentation updates.
- A portable v4 reference vault and its schemas, tools, examples, generated views, policies, journals, reviews, receipts, and textual derived indexes.
- Git-aware transactional behavior that is safe and optional, with a fully portable non-networked workflow.
- Formal review governance and lexical/graph retrieval implemented with Markdown/YAML plus Python/Bash tooling.
- Backward compatibility and regression coverage for the existing v3 reference implementation.

**Out of scope:**
- Replacing Markdown/YAML or Git as canonical durable knowledge.
- A mandatory long-running service, MCP server, database, vector store, embedding model, remote API, or authentication server.
- Enterprise multi-user OLTP guarantees, distributed locking, cloud synchronization correctness, or unattended background scheduling.
- Git LFS skill/asset packs, model fine-tuning, semantic-answer generation, and binary indexes.
- Destructive recovery commands that discard unrelated user changes.

## Applicable Project Conventions

**Quality gate commands:**
- `python3 -m pip install PyYAML`
- `cd examples/v3-minimal-vault && python3 tools/lint.py`
- `cd examples/v3-minimal-vault && MEMORY_TODAY=2026-05-11 tools/rebuild-views.sh`
- `python3 -m unittest discover -s tests`
- Add and run equivalent v4 lint, deterministic view/index rebuild, and generated-artifact drift gates.

**Commit convention:**
- Conventional commits where practical; preserve the required goal-agent `[B]`/`[I]` marker.
- Builder commits require `Assisted-by: Claude:Sonnet-4.6`.
- Inspector commits require `Assisted-by: Claude:Haiku-4.5`.
- Also include repository-required Copilot trailers:
  `Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>`
  `Copilot-Session: 3abdbf28-501a-493c-802c-f1b9a5ba3715`

**Guidelines:**
- `.github/copilot-instructions.md`
- `examples/v3-minimal-vault/CLAUDE.md`
- Root repository instructions supplied by the workspace.

**Rules:**
- This is a documentation-first repository; the example vault is the executable reference.
- One fact per file remains canonical; facts use controlled predicates and declared entities.
- Human narrative and agent-readable records remain separated.
- `valid_from`/`valid_to` describe world validity; `recorded_at` describes capture time.
- Generated views and indexes are derived and must never be hand-edited.
- Files under `sources/` are immutable; events are append-only.
- Date-dependent output must honor `MEMORY_TODAY`.
- Prefer precise, portable tools and explicit errors; no broad exception swallowing or silent fallback.
