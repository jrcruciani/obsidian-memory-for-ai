# Open Product & Protocol Decisions (v5.0)

Rather than prematurely hard-coding speculative infrastructure into v5.0, the following product and governance trade-offs are explicitly declared open for future vault owners and protocol revisions:

---

## OD-001: Cryptographic Agent Signatures vs. Cooperative Local Agent IDs
- **Current v5.0 choice:** `policy.yaml` enforces role separation (`executor`, `curator`, `reviewer`, `owner`), self-approval bans, and SHA-256 `content_hash` binding using declared `agent-*` strings.
- **Why open:** In a single-owner local Git repo, cooperative IDs catch accidental agent drift with zero key-management friction. In multi-human team repos, any user with write access can pass `--reviewer agent-owner-00000001`.
- **Future option:** Optional SSH/GPG/Ed25519 detached signatures over `proposal_content_hash` in `factory/reviews/` verified against a public-key keyring in `factory/schema/policy.yaml` (or Git signed commits).

## OD-002: Multi-Vault Federation & Read-Only Shared Skill Packs
- **Current v5.0 choice:** One vault is a self-contained directory tree with globally unique record IDs and local `derived_from` paths.
- **Why open:** Owners operating both a personal vault and project-specific repositories may want to import read-only `skills/` and `guidance/` packs across vaults without duplicating canonical truth.
- **Future option:** A mounted `knowledge/imports/{pack}/` convention pinned by Git commit SHA in `manifest.yaml`, kept read-only by lint.

## OD-003: Character Budgets vs. Tokenizer-Specific Budgets in `bootstrap`
- **Current v5.0 choice:** `bootstrap.yaml` budgets exact Unicode character counts (`budget_chars`), guaranteeing 100% deterministic, model-independent output offline without bundling `tiktoken` or vendor tokenizers.
- **Why open:** CJK scripts and dense YAML/code blocks have higher token-per-character ratios than English prose.
- **Future option:** Keep `budget_chars` as the normative deterministic contract while allowing callers to pass conservative `--budget` overrides calibrated to their host model's context window.

## OD-004: Automated Compaction of Resolved Signals & Historical Receipts
- **Current v5.0 choice:** `factory/signals/`, `factory/proposals/`, `factory/reviews/`, and `factory/receipts/` remain in-tree indefinitely so `kf.py query why` can trace full Factory lineage offline without inspecting `git log`.
- **Why open:** Very high-throughput vaults accumulating tens of thousands of signals over multiple years may eventually want cold-archival rollups.
- **Future option:** An explicit owner-gated `kf.py archive-ledger --before YYYY-MM-DD` command that summarizes old closed signals/receipts into yearly cold bundles while preserving active lineage pointers.
