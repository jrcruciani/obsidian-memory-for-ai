# Migration guide: v4.0 to v4.1

v4.1 is additive. Keep your existing facts, events, sources, and stable IDs.
Legacy `confidence: high|medium|low`, `recorded_at`, and inclusive `valid_to`
remain valid. A vault marked `"4.0"` keeps its original lint semantics.

**Tooling prerequisite:** install the self-contained `tools/` directory from
[`examples/v4.1-minimal-vault/`](examples/v4.1-minimal-vault/) in a copy of your
vault first. Python 3 and PyYAML are still the only runtime requirements.
Never replace your `memory/` or `sources/` with the example data. You may copy
the extended schema descriptions, but existing schemas need no mandatory edits.

## 1. Bump the version

Change only this field in `memory/schema/version.yaml`:

```yaml
spec_version: "4.1"
```

Run `python3 tools/lint.py`. New checks are version-gated. Do not mechanically
convert confidence labels or invent validity/observation dates. Future value
changes use `supersede_fact`; existing events and sources stay untouched.

## 2. Optionally inspect drift

```bash
python3 tools/consolidate.py --dry-run
python3 tools/consolidate.py       # emits diagnostic drafts, never applies repairs
python3 tools/lint.py --stale
tools/rebuild-views.sh
tools/rebuild-indexes.sh
```

Duplicate current facts or misplaced expired facts may be pre-existing drift.
Review diagnostic drafts and create separate repair proposals. Empty diagnostic
drafts cannot be approved/applied. New trust caps and external review policy are
optional entries in `roles.yaml`; see [the spec](SPEC-v4.1.md#9-temporal-facts-and-evidence).
Bootstrap uses a 6000-character default without a configuration file.
Pin `MEMORY_TODAY` when checking deterministic generated output in CI.

## 3. Optionally add aliases

Add names to existing declarations in `memory/entities.md`, for example
`aliases: [Elena, Voss]`. Aliases are case/accent-insensitive and must not
collide with another entity's ID or aliases.

```bash
tools/query.sh resolve Voss
tools/query.sh bootstrap
tools/query.sh facts --why elena-voss role
```

No other data migration is required. Read [AGENTS.md](examples/v4.1-minimal-vault/AGENTS.md)
for the bootstrap-first workflow. After creating v4.1 history, do not simply
lower the marker: older tools do not understand the new layout.
