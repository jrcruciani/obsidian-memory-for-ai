# Reference Vault — Knowledge Factory v5.0

Self-contained reference vault demonstrating **Obsidian Memory for AI v5.0: The Knowledge Factory Reboot**.

## Quick Tour

```bash
export KF_TODAY=2026-10-15  # pin reference vault snapshot date
KF_TODAY=2026-10-15 python3 tools/kf.py lint --strict
KF_TODAY=2026-10-15 python3 tools/kf.py bootstrap --profile executor
KF_TODAY=2026-10-15 python3 tools/kf.py bootstrap --profile curator
KF_TODAY=2026-10-15 python3 tools/kf.py query facts --entity elena-voss
KF_TODAY=2026-10-15 python3 tools/kf.py query facts --entity elena-voss --predicate role --as-of 2026-07-01
KF_TODAY=2026-10-15 python3 tools/kf.py query skills --trigger xrf
KF_TODAY=2026-10-15 python3 tools/kf.py query guidance --scope executor
KF_TODAY=2026-10-15 python3 tools/kf.py query why skill xrf-pigment-scan
KF_TODAY=2026-10-15 python3 tools/kf.py query signals --status open
KF_TODAY=2026-10-15 python3 tools/kf.py query proposals --status proposed
```
