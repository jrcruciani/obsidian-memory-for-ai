# Reference Vault — Knowledge Factory v5.0

Self-contained reference vault demonstrating **Obsidian Memory for AI v5.0: The Knowledge Factory Reboot**.

## Quick Tour

```bash
python3 tools/kf.py lint --strict
KF_TODAY=2026-10-15 python3 tools/kf.py bootstrap --profile executor
KF_TODAY=2026-10-15 python3 tools/kf.py bootstrap --profile curator
python3 tools/kf.py query facts --entity elena-voss
python3 tools/kf.py query facts --entity elena-voss --predicate role --as-of 2026-07-01
python3 tools/kf.py query skills --trigger xrf
python3 tools/kf.py query guidance --scope executor
python3 tools/kf.py query why skill xrf-pigment-scan
python3 tools/kf.py query signals --status open
python3 tools/kf.py query proposals --status proposed
```
