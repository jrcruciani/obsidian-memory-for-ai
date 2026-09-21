# v4.1 minimal vault

The self-contained reference for [SPEC-v4.1](../../SPEC-v4.1.md). All people
and scenarios are fictional. Python 3 + PyYAML only; offline, no model needed.
Read [AGENTS.md](AGENTS.md) before operating on the vault.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
source .venv/bin/activate
python3 tools/lint.py --strict
MEMORY_TODAY=2026-09-21 tools/rebuild-views.sh
tools/rebuild-indexes.sh
MEMORY_TODAY=2026-09-21 tools/query.sh bootstrap
```

## Demonstrations

| Feature | Try it |
|---|---|
| Current role | `tools/query.sh facts --entity elena-voss --predicate role` |
| Old role | `tools/query.sh facts --entity elena-voss --predicate role --as-of 2026-07-01` |
| All versions | `tools/query.sh facts --entity elena-voss --predicate role --history` |
| Role evidence | `tools/query.sh facts --why elena-voss role` |
| Reviewed external input | `tools/query.sh facts --why concordance tool` |
| Trust/confidence filtering | `tools/query.sh facts --trust external --min-confidence 0.7` |
| Aliases | `tools/query.sh resolve Voss` and `tools/query.sh search "Eléna Voss"` |
| Core memory | `tools/query.sh bootstrap` |
| Staleness | `python3 tools/lint.py --stale` (report only; `--strict` fails) |
| Consolidation | `python3 tools/consolidate.py --dry-run` (clean vault: no issues) |
| Structured output | `tools/query.sh facts --entity elena-voss --json` |

Elena's July 15 role supersedes the original role under
`memory/facts/elena-voss/role/2026-03-15.md`. The history filename uses its
recorded date because the old world-valid start is unknown.
The current role is pinned in bootstrap. The external tool claim links to
an immutable source and has an applied proposal, an independent review, and
a transaction receipt. Contradiction fixtures live only in tests, not here.

## Safe writes

```bash
python3 tools/transact.py begin --idempotency-key "add-elena-tool" --agent agent-local-1234abcd
python3 tools/transact.py add --txn-id <txn-id> --op create_fact \
  --entity elena-voss --predicate tool --value "Obsidian" --trust agent
python3 tools/transact.py commit --txn-id <txn-id> --yes
```

To change an existing value, use `supersede_fact --valid-from YYYY-MM-DD`.
For external or multi-agent writes use `propose.py create` with the same op
flags (or `--ops-file`), `review.py approve` by a different authorized actor,
then `propose.py apply --yes`. Direct external transactions are refused by
this vault's roles policy. Recovery uses `transact.py recover --yes`.

Do not edit generated `_views/` or `_indexes/`. Queries return the same data
without them; rebuilding twice with the same `MEMORY_TODAY` is byte-identical.
Never rewrite existing sources or events. New events use `create_event`.
Consolidation creates non-executable diagnostic drafts, never direct repairs.

From the repository root, run all regression tests and offline evaluations:

```bash
python3 -m unittest discover -s tests
python3 tests/eval/run_eval.py
```

The sibling v3/v4 reference vaults remain preserved for compatibility.
