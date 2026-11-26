# Personal Memory Mode (v5.1)

**Personal Memory Mode** adapts the Knowledge Factory v5.0 protocol for a single owner working daily with Obsidian and local AI assistants (Hermes, Claude Code, Codex, Cursor, or MCP clients). It eliminates four-step ceremony for routine personal memory while keeping strict review gates on high-risk writes (`skills`, `guidance`, and any `trust: external` source).

---

## 1. Quick Start

```bash
# Initialize a personal memory vault
python3 tools/kf.py init ~/MyPersonalMemory --profile personal
cd ~/MyPersonalMemory

# Remember or update personal facts in 1 atomic command (auto-creates entity + bitemporal history + receipt)
python3 tools/kf.py remember --entity me --predicate city --value "Madrid" --pinned --entity-kind person --entity-display "Owner"
python3 tools/kf.py remember --entity me --predicate favorite-editor --value "Obsidian + Neovim" --pinned

# Capture free-form narrative notes in Obsidian (non-authoritative)
python3 tools/kf.py note --slug memory-design --title "Memory Architecture" --body "Testing hybrid FTS5 search." --entities me --tags ai memory

# Build the disposable SQLite FTS5 (+ optional Ollama embeddings) search index
python3 tools/kf.py index build
# Optional local semantic embeddings via Ollama (default nomic-embed-text at http://127.0.0.1:11434):
# python3 tools/kf.py index build --embeddings

# Search via zero-dependency BM25 or disposable FTS5+RRF hybrid index
python3 tools/kf.py query search "editor neovim" --include-notes
python3 tools/kf.py query search "hybrid memory obsidian" --hybrid

# Load token-budgeted personal context
python3 tools/kf.py bootstrap --profile personal --max-tokens 1200

# Non-destructively forget a fact (retracted from active queries & search, preserved in history)
python3 tools/kf.py forget --entity me --predicate favorite-editor --reason "Switched tools"
```

---

## 2. Risk-Tiered Governance

| Operation / Namespace | Personal Mode Path | Security Invariant |
|---|---|---|
| Owner/trusted `facts` | 1-command `kf.py remember` / `kf.py forget` | Full bitemporal supersession + `receipt`; custom slug predicates allowed (`allow_custom_predicates: true`) |
| Narrative `notes` | 1-command `kf.py note` | Always `authoritative: false` |
| `trust: external` claims | **Blocked from `remember`** → `sources/` + `capture signal` + `propose → review → publish` | Prevents prompt injection from untrusted web clips, emails, or imported bundles |
| `skills` & `guidance` | `propose → review → publish` | Untrusted text can never inject executable procedures or rules into `bootstrap` |

---

## 3. Retrieval, Graph & Performance Upgrades (v5.1)

- **Zero-copy shadow validation:** `validate_candidate_writes()` only shadows `knowledge/` and `factory/` — never copying `sources/` (PDFs, images, audio) into `/tmp` while still verifying `derived_from` evidence paths.
- **Cooperative write locking:** Re-entrant cross-platform exclusive lock (`factory/_staging/.kf.lock`) prevents races between parallel agents and scheduled curation jobs.
- **Zero-dependency multi-term BM25 search:** NFKD accent-folded, lightweight EN/ES stemming, field-weighted ranking, plus `--include-notes`, `--include-sources`, and `--limit`.
- **Disposable SQLite FTS5 + Embedding RRF index:** `_generated/indexes/search.sqlite` is purely a derived read model (ignored by Git; deleting it loses zero canonical data). Automatically detects drift via `source_digest` and fuses FTS5 BM25 + cosine similarity + entity boost with Reciprocal Rank Fusion.
- **Multi-hop & temporal graph:** `kf.py query graph <node> --depth N --to <target> --as-of YYYY-MM-DD`.

---

## 4. Sleep-Time Curation, OKF v0.2 Interop & Ledger Archival

```bash
# Generate a prompt-injection-hardened Sleep-Time Curation packet (<untrusted_source_data> boundaries)
python3 tools/kf.py curate sleep-pack --emit-signals

# Export living knowledge to Google Cloud Open Knowledge Format (OKF v0.2)
python3 tools/kf.py export-okf ./exports/okf-bundle

# Forgivingly import an external OKF bundle into immutable sources/okf-imports/ + curation signals
python3 tools/kf.py import-okf ./incoming-okf

# Lint in OKF forgiving mode (downgrades unknown extra frontmatter fields to WARN)
python3 tools/kf.py lint --forgiving

# Archive old closed signals & unreferenced receipts into yearly SHA-256 rollups (OD-004)
python3 tools/kf.py archive-ledger --before 2026-01-01 --yes
```

---

## 5. Stdio MCP Server (`tools/kf_mcp.py`)

Connect any MCP host (Hermes, Claude Desktop, Cursor) with zero external packages:

```json
{
  "mcpServers": {
    "obsidian-memory": {
      "command": "python3",
      "args": ["/path/to/vault/tools/kf_mcp.py", "--vault", "/path/to/vault"]
    }
  }
}
```

- **Tools (12):** `kf_bootstrap`, `kf_search`, `kf_remember`, `kf_forget`, `kf_note`, `kf_capture_signal`, `kf_query_facts`, `kf_query_skills`, `kf_query_guidance`, `kf_query_why`, `kf_query_graph`, `kf_sleep_pack`.
- **Resources (4):** `kf://dashboard`, `kf://bootstrap/personal`, `kf://catalog`, `kf://factory-queue`.
