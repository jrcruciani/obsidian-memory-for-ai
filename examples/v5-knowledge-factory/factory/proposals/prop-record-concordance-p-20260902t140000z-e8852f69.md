---
type: proposal
id: prop-record-concordance-p-20260902t140000z-e8852f69
title: Record Concordance primary XRF instrument from vendor bulletin
namespace: facts
proposer_id: agent-curator-00000003
status: published
created_at: "2026-09-02T14:00:00Z"
rationale: "Vendor bulletin confirms handheld XRF unit assignment; external trust requires review."
resolves_signals: []
derived_from: []
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
required_approvals: 1
content_hash: "sha256:e69b01bf5e416b4e1d70f1445881c9db6729c8f26c4819c0bd3b4ee4f149be17"
idempotency_key: null
published_at: "2026-09-03T10:05:00Z"
receipt_id: rcpt-publish-prop-record-20260903t100500z-ea9e37f0
---

# Proposal: Record Concordance primary XRF instrument from vendor bulletin

- **Status:** `published`
- **Namespace:** `facts`
- **Proposer:** `agent-curator-00000003`
- **Content hash:** `sha256:e69b01bf5e416b4e1d70f1445881c9db6729c8f26c4819c0bd3b4ee4f149be17`

## Rationale

Vendor bulletin confirms handheld XRF unit assignment; external trust requires review.
