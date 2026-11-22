---
type: decision
id: DEC-001-knowledge-factory-governance
title: Separate Executor Capture From Curator Proposals and Independent Review
status: accepted
decided_at: 2026-05-11
decided_by: agent-owner-00000001
domain: governance
summary: "Executors emit append-only signals and events; Curators author proposals; Reviewers publish."
entities:
  - concordance
  - strata
derived_from:
  - knowledge/events/2026-05-11/evt-vault-cutover.md
consequences:
  - Task-executing agents never mutate canonical knowledge mid-flight
  - Every external or agent-synthesized fact/skill carries full review lineage
supersedes: null
pinned: true
---

# DEC-001 — Knowledge Factory Governance

Separates low-friction runtime capture from deliberate offline curation and review.
