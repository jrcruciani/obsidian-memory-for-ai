---
type: proposal
id: prop-add-tempera-relative-20261014t110000z-c43bc8bd
title: Add tempera relative humidity ceiling guidance
namespace: guidance
proposer_id: agent-curator-00000003
status: proposed
created_at: "2026-10-14T11:00:00Z"
rationale: Codifies Venice panel RH observation into an executor guardrail.
resolves_signals:
  - sig-need-explicit-rh-cei-20261013t090000z-9e82b5d3
derived_from: []
ops:
  - op: create_guidance
    slug: tempera-humidity-ceiling
    title: "Halt Panel XRF Scans Above 55% Ambient Relative Humidity"
    domain: conservation
    scope: executor
    priority: high
    policy_rule: "Suspend panel spectroscopy when ambient RH exceeds 55% unless climate-controlled enclosure is active."
    anti_patterns:
      - "Scanning hygroscopic azurite tempera in unconditioned rooms above 58% RH"
    entities:
      - concordance
    derived_from:
      - sources/2026-10-12-venice-panel-field-notes.md
      - factory/signals/2026-10-13/sig-need-explicit-rh-cei-20261013t090000z-9e82b5d3.md
    trust: agent
    pinned: true
required_approvals: 1
content_hash: "sha256:8649117e7516449a0a9746f52e9813ce2731f77d2e576bbebb5e398cf7820202"
idempotency_key: null
published_at: null
receipt_id: null
---

# Proposal: Add tempera relative humidity ceiling guidance

- **Status:** `proposed`
- **Namespace:** `guidance`
- **Proposer:** `agent-curator-00000003`
- **Content hash:** `sha256:8649117e7516449a0a9746f52e9813ce2731f77d2e576bbebb5e398cf7820202`

## Rationale

Codifies Venice panel RH observation into an executor guardrail.
