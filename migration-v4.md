# Migration guide: v3 → v4

> **Pre-reading:** This guide assumes familiarity with the v3 protocol described in [`SPEC-v3.md`](SPEC-v3.md). Read that first if you are new to the repository.

---

## Overview

v4 is a **strict superset** of v3. Every valid v3 vault is compatible with the v4 tooling. The migration is incremental — you can adopt each v4 capability independently and keep the rest of your vault on v3 idioms until you are ready.

The only mandatory change to unlock v4 validation is bumping `spec_version` to `"4.0"` in `memory/schema/version.yaml`.

---

## Step 1: Bump the spec version

```bash
# In your vault root:
sed -i '' 's/spec_version: "3.0"/spec_version: "4.0"/' memory/schema/version.yaml
```

Then add the three new schemas to `memory/schema/`:

```bash
# Copy from the v4 reference vault:
cp examples/v4-minimal-vault/memory/schema/transaction.schema.yaml  memory/schema/
cp examples/v4-minimal-vault/memory/schema/proposal.schema.yaml     memory/schema/
cp examples/v4-minimal-vault/memory/schema/review.schema.yaml       memory/schema/
```

And copy the new tools:

```bash
cp examples/v4-minimal-vault/tools/transact.py        tools/
cp examples/v4-minimal-vault/tools/propose.py          tools/
cp examples/v4-minimal-vault/tools/review.py           tools/
cp examples/v4-minimal-vault/tools/rebuild_indexes.py  tools/
cp examples/v4-minimal-vault/tools/query_impl.py       tools/
cp examples/v4-minimal-vault/tools/rebuild-indexes.sh  tools/
chmod +x tools/rebuild-indexes.sh
```

Validate:

```bash
python3 tools/lint.py  # should pass
```

---

## Step 2: Add role policy (for proposal governance)

Create `memory/schema/roles.yaml`. This is optional for single-agent vaults but required to use `tools/propose.py` with namespace enforcement.

Minimal example:

```yaml
namespaces:
  - id: facts
    required_approvals: 1
    allowed_proposers: [agent-local-1234abcd]
    allowed_reviewers: [agent-human-00000001]

agents:
  - id: agent-human-00000001
    display_name: Human reviewer
    roles: [reviewer, admin]
  - id: agent-local-1234abcd
    display_name: Local AI assistant
    roles: [proposer]
```

---

## Step 3: Create new directories

```bash
mkdir -p memory/_transactions
mkdir -p memory/_proposals
mkdir -p memory/_reviews
mkdir -p memory/_staging
mkdir -p memory/_indexes
```

---

## Step 4: Rebuild indexes

```bash
python3 tools/rebuild_indexes.py
```

This creates `memory/_indexes/lexical.md` and `memory/_indexes/graph.md`. Commit these alongside the rest of your vault.

---

## Step 5: Update your quality gates

Add the new gates:

```bash
# v4 lint
python3 tools/lint.py

# v4 view rebuild
MEMORY_TODAY=$(date +%Y-%m-%d) tools/rebuild-views.sh

# v4 index rebuild
tools/rebuild-indexes.sh
```

If you have CI, add a drift check:

```bash
git diff --exit-code -- memory/_views memory/_indexes
```

---

## Step 6: Migrate multi-operation writes to transactions

Previously, multi-op writes went through multiple `_inbox/` operations processed by `compact.py`. In v4, prefer:

```bash
python3 tools/transact.py begin --idempotency-key "describe-what-changed" --agent agent-local-1234abcd
# <returns txn-id>

python3 tools/transact.py add --txn-id <txn-id> --op create_fact \
  --entity my-entity --predicate my-predicate --value "my value"

python3 tools/transact.py commit --txn-id <txn-id> --yes
```

Existing `_inbox/` operations continue to work through `compact.py` with no changes.

---

## Step 7 (optional): Adopt formal proposals for governed writes

If your vault has multiple writers or requires human review before applying changes:

```bash
# Create a proposal
python3 tools/propose.py create \
  --title "Add language fact for Elena" \
  --namespace facts \
  --proposer agent-local-1234abcd \
  --op create_fact \
  --entity elena-voss \
  --predicate language \
  --value "Spanish"

# Review it (different agent)
python3 tools/review.py approve \
  --proposal-id <prop-id> \
  --reviewer agent-human-00000001 \
  --comment "Confirmed."

# Apply once approved
python3 tools/propose.py apply --proposal-id <prop-id> --yes
```

---

## What does NOT change

| v3 feature | v4 status |
|---|---|
| `memory/facts/{entity}/{pred}.md` layout | Unchanged |
| `memory/events/YYYY-MM-DD/{id}.md` layout | Unchanged |
| `memory/schema/predicates.yaml` | Unchanged |
| `memory/entities.md` | Unchanged |
| `_inbox/` operation envelopes | Still supported via `compact.py` |
| `_claims/` advisory claims | Unchanged |
| `_views/` generated views | Extended with `proposals.md` and `transactions.md` |
| `tools/lint.py` | Extended (now validates v4 types too) |
| `tools/compact.py` | Unchanged for v3-style operations |
| `tools/query.sh` | Extended with `search` and `graph` sub-commands |

---

## Rollback

If you need to roll back to v3 after migrating:

1. Change `spec_version` back to `"3.0"` in `memory/schema/version.yaml`.
2. Remove the new v4 schemas: `transaction.schema.yaml`, `proposal.schema.yaml`, `review.schema.yaml`, `roles.yaml`.
3. Remove `memory/_transactions/`, `memory/_proposals/`, `memory/_reviews/`, `memory/_indexes/`.
4. Use the v3 tools only.

v3 validation will ignore any `type: transaction`, `type: proposal`, or `type: review` files if you left them in place, but it is cleaner to remove them.
