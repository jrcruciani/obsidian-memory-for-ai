---
type: skill
id: skill-xrf-pigment-scan-v1
slug: xrf-pigment-scan
title: Non-Destructive XRF Pigment Scan
status: active
version: 1
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
observed_at: "2026-09-03T15:10:00Z"
last_confirmed: 2026-09-03
review_after: null
supersedes: null
pinned: true
---

## Trigger

Load before running or interpreting handheld XRF scans on painted panels.

## Procedure

1. Warm XRF tube for 120 seconds.
2. Validate copper K-alpha calibration standard (`8.04 keV +/- 0.02 keV`).
3. Maintain >= 2 mm standoff from surface; acquire 60s spectrum.

## Verification

- Calibration offset logged in SI units (`keV`).
- Raw spectrum cited via `capture event`.
