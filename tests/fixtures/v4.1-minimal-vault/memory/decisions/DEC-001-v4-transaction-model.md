---
type: decision
id: DEC-001
title: Use v4 transaction model for all multi-operation writes
status: accepted
decided_at: 2026-07-01
entities: [elena-voss]
sources: ["sources/README.md"]
---

# DEC-001 — Use v4 transaction model for all multi-operation writes

Multi-operation writes that touch more than one fact file must use the v4 transaction protocol so that failures leave the vault in a recoverable state rather than half-applied.

Single-operation edits may still use the v3 operation envelope workflow via the `_inbox/`.
