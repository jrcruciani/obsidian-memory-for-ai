# Offline Deterministic Query & Bootstrap Evaluations (v5.0)

Run `python3 tests/eval/run_eval.py` from any directory.

`tests/eval/questions.yaml` defines **26 exact offline contracts** executed against `examples/v5-knowledge-factory/` with `KF_TODAY=2026-10-15`, verifying:

- Current facts vs. half-open `--as-of` historical facts and `--history` chains
- End-to-end Factory lineage (`query why`) across `facts` (including reviewed `trust: external` sources) and `skills` (`signal → proposal → review → receipt → skill`)
- Procedural `skills` lookup by domain and trigger phrase
- Normative `guidance` filtering by role scope (`executor` vs. `curator`)
- Accepted `decisions`, open `signals`, pending `proposals`, and `proposal_publish` `receipts`
- Role-aware character-budgeted `bootstrap` (`default`, `executor`, `curator`)
- Case- and accent-insensitive NFKD entity alias resolution (`resolve`) and exit code `2` on unknown entities
- Multi-type ranked `search`, relationship `graph`, and `--json` v5.0 CLI envelopes

Latency is reported for visibility only and never gates pass/fail. Zero network calls, zero LLM calls, and works both with `PyYAML` and with `KF_NO_PYYAML=1` (stdlib fallback).
