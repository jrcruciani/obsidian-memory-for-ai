# v4 minimal vault — reference implementation

**SPEC-v4.0 Transactional Atomic Markdown Memory**

This is the reference vault for the v4.0 protocol. It demonstrates all three new capabilities without introducing a database, daemon, server, or binary source of truth.

## Quick start

```bash
cd examples/v4-minimal-vault
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
python3 tools/lint.py
MEMORY_TODAY=2026-07-01 tools/rebuild-views.sh
python3 tools/rebuild_indexes.py
tools/query.sh facts --entity elena-voss
tools/query.sh search elena
tools/query.sh graph entity concordance
```

## v4 capabilities

### 1. Git-native transactions

```bash
python3 tools/transact.py begin --idempotency-key "add-language-es-2026-07" --agent agent-local-1234abcd
python3 tools/transact.py add --txn-id <txn-id> --op create_fact \
  --entity elena-voss --predicate language --value "Spanish"
python3 tools/transact.py commit --txn-id <txn-id> --yes
python3 tools/transact.py list
```

Replaying the same `--idempotency-key` is a no-op once committed.

### 2. Formal proposal/review lifecycle

```bash
# Create a proposal
python3 tools/propose.py create \
  --title "Add Obsidian tool fact" \
  --namespace facts \
  --proposer agent-local-1234abcd \
  --op create_fact \
  --entity elena-voss \
  --predicate tool \
  --value Obsidian

# Approve the proposal (must not be same agent as proposer)
python3 tools/review.py approve \
  --proposal-id <prop-id> \
  --reviewer agent-human-00000001 \
  --comment "Confirmed."

# Apply once approved
python3 tools/propose.py apply --proposal-id <prop-id> --yes
```

### 3. Deterministic indexes with fallback

```bash
# Build indexes
python3 tools/rebuild_indexes.py

# Search via index (automatic fallback to filesystem if index is missing)
tools/query.sh search "pigment"
tools/query.sh graph entity concordance

# Delete indexes and rebuild — output is byte-identical
rm -rf memory/_indexes
python3 tools/rebuild_indexes.py
```

## Directory structure

| Path | Purpose |
|------|---------|
| `memory/facts/` | Atomic typed facts (one per file) |
| `memory/events/` | Append-only episodic records |
| `memory/schema/` | YAML schemas, predicates, and role policy |
| `memory/_transactions/` | Transaction journals/receipts |
| `memory/_proposals/` | Formal proposals awaiting review |
| `memory/_reviews/` | Review records (cryptographically bound) |
| `memory/_staging/` | Isolated staging area (cleared after commit) |
| `memory/_views/` | Generated views — do not edit |
| `memory/_indexes/` | Generated lexical and graph indexes — do not edit |
| `memory/_inbox/` | Legacy v3-compatible operation envelopes |
| `memory/_ops/applied/` | Applied operation receipts |
