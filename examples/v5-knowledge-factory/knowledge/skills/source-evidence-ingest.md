---
type: skill
id: skill-source-evidence-ingest-v1
slug: source-evidence-ingest
title: Primary Source Evidence Ingest
status: active
version: 1
domain: vault-ops
triggers:
  - ingest source
  - archive field notes
  - new vendor bulletin
inputs:
  - raw markdown note
  - capture date
outputs:
  - immutable file under sources/
  - captured event or signal
verification:
  - Confirm file resides under sources/ with YYYY-MM-DD prefix
  - Run kf.py lint --strict
entities:
  - concordance
derived_from:
  - knowledge/events/2026-05-11/evt-vault-cutover.md
trust: owner
confidence: 0.95
observed_at: "2026-05-11T09:06:00Z"
last_confirmed: 2026-05-11
review_after: null
supersedes: null
pinned: true
---

## Trigger

Use when adding raw transcripts, bulletins, or field notes.

## Procedure

1. Save immutable Markdown under `sources/`.
2. Record an append-only event via `kf.py capture event`.

## Verification

- Confirm `kf.py lint --strict` passes.
