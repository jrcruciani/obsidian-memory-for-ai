# V4 Memory Protocol Goal Summary

## Outcome

The repository now ships v4.0 as the current stable Transactional Atomic
Markdown Memory protocol while retaining v3.1 as the previous supported
generation.

## Acceptance Criteria

1. **Protocol and migration documentation:** `SPEC-v4.md`, `migration-v4.md`,
   the root README, documentation map, and changelog present v4 and preserve
   the v3 path.
2. **Reference implementation:** `examples/v4-minimal-vault/` demonstrates
   atomic facts, append-only events, typed schemas, generated views,
   transactions, proposals, reviews, roles, and indexes.
3. **Transactions:** stable transaction and idempotency IDs, isolated staging,
   expected Git revision checks, Markdown journals, rollback, and recovery are
   implemented and tested.
4. **Governance:** proposals and reviews have a formal lifecycle, content-hash
   binding, namespace/role policy, approval thresholds, and self-approval and
   authorization enforcement.
5. **Retrieval:** deterministic human-readable lexical and graph indexes are
   rebuildable from canonical Markdown, with equivalent filesystem fallback.
6. **Essence preserved:** no daemon, server, database, model, remote API,
   binary index, or Git LFS layer is required.
7. **Safety and portability:** failures are explicit, sources and events retain
   their immutability rules, and Python 3.11 with PyYAML remains sufficient.
8. **Regression coverage:** 45 v4 tests complement the 17 existing v3 tests.
9. **Continuous validation:** GitHub Actions enforces v3 and v4 lint, tests,
   deterministic views, v4 indexes, and generated-artifact drift checks.

## Iteration History

| Iteration | Verdict | Outcome |
|---|---|---|
| 1 | PASS | Initial implementation satisfied the functional and local quality gates. |
| 2 | FAIL | Reinspection found that GitHub Actions still enforced only v3. |
| 3 | PASS | CI was updated for v4 and every quality gate passed with a clean worktree. |

## Inspector Findings and Resolution

The substantive issue was a mismatch between local validation and automated
enforcement: v4 lint, deterministic views, indexes, and drift checks worked but
were absent from the GitHub Actions workflow. Iteration 3 added a dedicated v4
validation job while preserving the v3 job and full regression suite.

## Recommendations

- Keep derived accelerators optional and require parity tests against direct
  filesystem reads.
- Treat future proposal policy changes as protocol changes with migration
  guidance and adversarial authorization tests.
- Add live cross-platform Git transaction evidence if v4 is later promoted
  beyond the local, owner-controlled vault use case.
