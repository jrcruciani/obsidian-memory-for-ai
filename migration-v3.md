# Migrating from v2 to v3

v2 to v3 is additive and manual-review-first. The stable v3.0 toolkit does not ship automatic migration tooling because converting prose into atomic facts is semantic work.

## 1. Bootstrap the v3 structure

Copy these from `examples/v3-minimal-vault/` into your vault:

```text
memory/schema/
memory/_views/
memory/_inbox/
memory/_claims/
memory/_ops/
memory/_archive/
tools/
```

Create or adapt:

```text
memory/entities.md
memory/schema/predicates.yaml
memory/schema/version.yaml
```

`version.yaml` must contain:

```yaml
spec_version: "3.0"
schema_status: stable
```

Do not run `tools/lint.py` before these bootstrap files exist.

## 2. Freeze old chronological logs

Keep existing v2 files such as `memory/log.md` as historical record. Do not rewrite them into v3 events in bulk.

From the cutover point forward, write new session history as append-only files under:

```text
memory/events/YYYY-MM-DD/{slug}.md
```

## 3. Start with new facts only

For new durable facts, write one file per tuple:

```text
memory/facts/{entity}/{predicate}.md
```

Add the entity to `memory/entities.md` and the predicate to `memory/schema/predicates.yaml` first. Then run:

```bash
python3 tools/lint.py
tools/rebuild-views.sh
```

For v3.1-style agentic workflows, prefer proposed operations over direct writes:

```bash
tools/ops.py create-fact --agent agent-local-1234abcd --entity elena-voss --predicate role --value "Art conservator" --reason "Backfill durable role fact."
tools/compact.sh
```

Operation receipts are preserved under `memory/_ops/applied/`.

## 4. Backfill only when useful

When an old prose page contains a fact you actively need, extract just that fact into `memory/facts/`. Leave the prose page intact and human-readable. The vault converges through use; there is no big-bang rewrite.

## 5. Switch reads to generated views

Once an entity has enough atomic facts, prefer:

```text
memory/_views/by-entity/{entity}.md
```

for factual agent reads. Keep `memory/people/`, `memory/projects/`, and `memory/context/` as human-facing narrative.

## 6. Validate before committing

Use deterministic dates when checking generated stale views:

```bash
MEMORY_TODAY=2026-05-11 tools/rebuild-views.sh
git diff -- memory/_views
python3 tools/lint.py
```

Private vaults may ignore `_views/`, but then views must be rebuilt locally before relying on them.
