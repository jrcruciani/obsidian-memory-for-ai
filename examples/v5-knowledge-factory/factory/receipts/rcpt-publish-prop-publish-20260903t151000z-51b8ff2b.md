---
type: receipt
id: rcpt-publish-prop-publish-20260903t151000z-51b8ff2b
mode: proposal_publish
status: committed
idempotency_key: publish-prop-publish-non-destruct-20260903t110000z-ce01bd92
actor_id: agent-reviewer-00000002
proposer_id: agent-curator-00000003
proposal_id: prop-publish-non-destruct-20260903t110000z-ce01bd92
review_ids:
  - rev-publish-non-dest-20260903t150000z-4b5b1c0e
resolved_signals:
  - sig-missing-standardized-20260902t093000z-e3d79bbc
created_at: "2026-09-03T15:10:00Z"
committed_at: "2026-09-03T15:10:00Z"
expected_revision: null
parent_revision: f87548aad314ab385d4784a618297e363b859238
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
touched_files:
  - path: factory/proposals/prop-publish-non-destruct-20260903t110000z-ce01bd92.md
    action: updated
    before_hash: "sha256:5d40a861abcf361d16d14271ff5c02775fef730ba1155d39a3483ae24b8ab717"
    after_hash: "sha256:8f0216b9e715bb162b9fb44d56a819caebba8144edc687898da409a4e8d226ed"
  - path: factory/signals/2026-09-02/sig-missing-standardized-20260902t093000z-e3d79bbc.md
    action: updated
    before_hash: "sha256:f2f739457445b22204ac294317658f2e9e77b8c98dc44ea87caf7909b27188d5"
    after_hash: "sha256:f154fd7b336da653ac2505386eea6cf1c09064608c9751728a7d784d97f59c63"
  - path: knowledge/skills/xrf-pigment-scan.md
    action: created
    before_hash: null
    after_hash: "sha256:4ff3da086d7b124f318a761f2249fe34feeb59b2c562c0dedfd9ba42b83c9b29"
failure_reason: null
---

# Publication Receipt: `rcpt-publish-prop-publish-20260903t151000z-51b8ff2b`

- **Proposal:** `prop-publish-non-destruct-20260903t110000z-ce01bd92` (by `agent-curator-00000003`)
- **Publisher:** `agent-reviewer-00000002`
- **Authorizing reviews:** `rev-publish-non-dest-20260903t150000z-4b5b1c0e`
- **Resolved signals:** `sig-missing-standardized-20260902t093000z-e3d79bbc`
