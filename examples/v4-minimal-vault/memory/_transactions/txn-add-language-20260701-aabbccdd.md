---
type: transaction
transaction_id: txn-add-language-20260701-aabbccdd
idempotency_key: add-elena-voss-language-german-2026-07
agent_id: agent-local-1234abcd
created_at: 2026-07-01T09:00:00Z
status: committed
expected_revision: null
committed_revision: null
committed_at: 2026-07-01T09:01:15Z
failure_reason: null
ops:
  - op: create_fact
    target_path: memory/facts/elena-voss/language.md
    entity: elena-voss
    predicate: language
    value: German
---

# Transaction: add language fact for Elena Voss

Atomically created `memory/facts/elena-voss/language.md`. Idempotency key `add-elena-voss-language-german-2026-07` — replaying this key will be a no-op as long as this journal entry exists with `status: committed`.
