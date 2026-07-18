# Documentation map

This repository is documentation-first. The current protocol is **v4.0 Transactional Atomic Markdown Memory**; v3.1 is retained as the previous stable generation.

## Canonical reading paths

| Audience | Start with | Then read |
|---|---|---|
| New user copying a vault | [`../README.md`](../README.md) | [`../examples/v4-minimal-vault/`](../examples/v4-minimal-vault/), then [`../SPEC-v4.md`](../SPEC-v4.md) as needed |
| Implementer building v4 tools | [`../SPEC-v4.md`](../SPEC-v4.md) | [`../examples/v4-minimal-vault/tools/`](../examples/v4-minimal-vault/tools/), [`../tests/`](../tests/) |
| v3 user migrating to v4 | [`../migration-v4.md`](../migration-v4.md) | [`../examples/v4-minimal-vault/`](../examples/v4-minimal-vault/) |
| v3 user staying on v3 | [`../SPEC-v3.md`](../SPEC-v3.md) | [`../examples/v3-minimal-vault/`](../examples/v3-minimal-vault/) |
| Existing v2 user | [`../migration-v3.md`](../migration-v3.md) | [`../examples/v3-minimal-vault/`](../examples/v3-minimal-vault/) |
| Agent/plugin author | [`../plugin-guide.md`](../plugin-guide.md) | [`../automation-guide.md`](../automation-guide.md) |
| Historian of the original pattern | [`../guide.md`](../guide.md) | [`../examples/minimal-vault/`](../examples/minimal-vault/) |

## Document status

| Document | Status | Role |
|---|---|---|
| [`../README.md`](../README.md) | Current | Landing page and short orientation |
| [`../SPEC-v4.md`](../SPEC-v4.md) | **Current, normative** | Stable v4.0 compatibility contract |
| [`../SPEC-v3.md`](../SPEC-v3.md) | Previous stable, normative | Stable v3.1 compatibility contract |
| [`../examples/v4-minimal-vault/README.md`](../examples/v4-minimal-vault/README.md) | **Current** | Working v4.0 reference implementation |
| [`../examples/v3-minimal-vault/README.md`](../examples/v3-minimal-vault/README.md) | Previous stable | Working v3.1 reference implementation |
| [`../migration-v4.md`](../migration-v4.md) | Current | Manual v3-to-v4 migration guide |
| [`../migration-v3.md`](../migration-v3.md) | Current | Manual v2-to-v3 migration checklist |
| [`../automation-guide.md`](../automation-guide.md) | Current, optional | Automation patterns |
| [`../plugin-guide.md`](../plugin-guide.md) | Current, optional | Host-agent command/skill packaging pattern |
| [`../obsidian-cli.md`](../obsidian-cli.md) | Optional integration | Local Obsidian CLI recipes |
| [`../photo-ingest-guide.md`](../photo-ingest-guide.md) | Optional integration | Domain-specific ingest workflow |
| [`../optional-ideas.md`](../optional-ideas.md) | Experimental | Non-protocol ideas |
| [`../guide.md`](../guide.md) | Legacy v2 | Original compiled-wiki guide |
| [`../examples/minimal-vault/README.md`](../examples/minimal-vault/README.md) | Legacy v2 | Original compiled-wiki example |

## Maintenance rules

1. Keep `README.md` short and navigational; move deep explanations to focused docs.
2. Treat `SPEC-v4.md` as the source of truth for v4 behavior; treat `SPEC-v3.md` as the source of truth for v3 behavior.
3. Mark v2 content as legacy and v3 content as previous stable wherever they appear.
4. Avoid adding new top-level guides unless they are broadly useful.
5. When a guide describes optional tooling, state whether it is required for v4 compatibility. Most integrations are optional.
6. Do not bulk-refresh date examples unless the semantic guidance changes.

