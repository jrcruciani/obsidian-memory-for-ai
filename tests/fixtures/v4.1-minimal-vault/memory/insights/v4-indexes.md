---
type: insight
id: insight-v4-separation
title: Index-first vs. scan-first retrieval
summary: Both lexical and graph indexes are derived and must produce identical results to direct filesystem scanning.
entities: [elena-voss]
sources: ["sources/README.md"]
recorded_at: 2026-07-01T10:00:00Z
tags: [protocol, design]
---

# Index-first vs. scan-first retrieval

The v4 protocol maintains both a lexical index and a graph index under `memory/_indexes/` for fast retrieval, but neither index is canonical. Any query tool must produce byte-identical results whether it reads from the index or scans the filesystem directly. This property is verified by the regression test suite.
