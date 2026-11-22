---
type: proposal
id: prop-publish-non-destruct-20260903t110000z-ce01bd92
title: Publish Non-Destructive XRF Pigment Scan skill
namespace: skills
proposer_id: agent-curator-00000003
status: published
created_at: "2026-09-03T11:00:00Z"
rationale: Closes executor gap signal using DEC-002 and vendor calibration spec.
resolves_signals:
  - sig-missing-standardized-20260902t093000z-e3d79bbc
derived_from: []
ops:
  - op: create_skill
    slug: xrf-pigment-scan
    title: Non-Destructive XRF Pigment Scan
    domain: conservation
    triggers:
      - xrf scan
      - pigment analysis
      - panel spectroscopy
    inputs:
      - panel region coordinates
      - ambient RH reading
    outputs:
      - calibrated keV peak table
      - capture event record
    verification:
      - Verify 120s tube warmup completed
      - "Confirm copper K-alpha reference within +/- 0.02 keV"
      - "Confirm zero contact distance >= 2 mm from varnish surface"
    entities:
      - concordance
      - elena-voss
    derived_from:
      - sources/2026-09-01-xrf-vendor-bulletin.md
      - factory/signals/2026-09-02/sig-missing-standardized-20260902t093000z-e3d79bbc.md
    trust: agent
    confidence: 0.94
    pinned: true
    body: "## Trigger\n\nLoad before running or interpreting handheld XRF scans on painted panels.\n\n## Procedure\n\n1. Warm XRF tube for 120 seconds.\n2. Validate copper K-alpha calibration standard (`8.04 keV +/- 0.02 keV`).\n3. Maintain >= 2 mm standoff from surface; acquire 60s spectrum.\n\n## Verification\n\n- Calibration offset logged in SI units (`keV`).\n- Raw spectrum cited via `capture event`."
required_approvals: 1
content_hash: "sha256:d4ed58763fb3b6ab7aa8a5fd460b3870f351ccf9b0b8f5ce628ea13b1726a94a"
idempotency_key: null
published_at: "2026-09-03T15:10:00Z"
receipt_id: rcpt-publish-prop-publish-20260903t151000z-51b8ff2b
---

# Proposal: Publish Non-Destructive XRF Pigment Scan skill

- **Status:** `published`
- **Namespace:** `skills`
- **Proposer:** `agent-curator-00000003`
- **Content hash:** `sha256:d4ed58763fb3b6ab7aa8a5fd460b3870f351ccf9b0b8f5ce628ea13b1726a94a`

## Rationale

Closes executor gap signal using DEC-002 and vendor calibration spec.
