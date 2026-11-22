---
type: receipt
id: rcpt-publish-prop-record-20260903t100500z-ea9e37f0
mode: proposal_publish
status: committed
idempotency_key: publish-prop-record-concordance-p-20260902t140000z-e8852f69
actor_id: agent-owner-00000001
proposer_id: agent-curator-00000003
proposal_id: prop-record-concordance-p-20260902t140000z-e8852f69
review_ids:
  - rev-record-concordan-20260903t100000z-47e40b92
resolved_signals: []
created_at: "2026-09-03T10:05:00Z"
committed_at: "2026-09-03T10:05:00Z"
expected_revision: null
parent_revision: f87548aad314ab385d4784a618297e363b859238
ops:
  - op: create_fact
    entity: concordance
    predicate: primary-instrument
    value: Portable XRF analyzer
    valid_from: 2026-09-01
    observed_at: "2026-09-01T12:00:00Z"
    last_confirmed: 2026-09-03
    confidence: 0.85
    assertion: stated
    trust: external
    derived_from:
      - sources/2026-09-01-xrf-vendor-bulletin.md
    pinned: true
touched_files:
  - path: factory/proposals/prop-record-concordance-p-20260902t140000z-e8852f69.md
    action: updated
    before_hash: "sha256:d27509e8c1efe0d94d8dc113b0f25888f29df329fc99fe66c28f1df71fe0b4e2"
    after_hash: "sha256:8d1cdce68ec00c92d434fb0def7ade0879ab341764db26baa172b8f200474b6a"
  - path: knowledge/facts/concordance/primary-instrument.md
    action: created
    before_hash: null
    after_hash: "sha256:673b9e4d262cb55f252f716402ec95f9ec4b60a6368a5f3fa3125bc8d6713b00"
failure_reason: null
---

# Publication Receipt: `rcpt-publish-prop-record-20260903t100500z-ea9e37f0`

- **Proposal:** `prop-record-concordance-p-20260902t140000z-e8852f69` (by `agent-curator-00000003`)
- **Publisher:** `agent-owner-00000001`
- **Authorizing reviews:** `rev-record-concordan-20260903t100000z-47e40b92`
- **Resolved signals:** none
