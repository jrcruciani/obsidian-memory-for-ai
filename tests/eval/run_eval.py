#!/usr/bin/env python3
"""Offline exact-query evaluation gate for Knowledge Factory v5.0 (latency reported, never gated)."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from kflib.yaml_io import load_yaml  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vault",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "examples/v5-knowledge-factory",
    )
    args = parser.parse_args()
    vault = args.vault.resolve()
    spec = load_yaml(Path(__file__).with_name("questions.yaml").read_text(encoding="utf-8"))
    questions = spec["questions"]
    eval_today = str(spec.get("eval_today", "2026-10-15"))
    env = dict(os.environ, KF_TODAY=eval_today)

    print("| Contract | Result | Latency (ms) |")
    print("|---|---|---:|")
    failures = 0
    for q in questions:
        qid = q["id"]
        cmd = q["command"]
        if not isinstance(cmd, list) or not cmd or cmd[0] != "tools/kf.py":
            raise ValueError(f"{qid}: command must start with 'tools/kf.py'")
        t0 = time.perf_counter()
        completed = subprocess.run(
            [sys.executable, *cmd],
            cwd=vault,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        ok = completed.returncode == int(q.get("exit_code", 0))
        if "expected_stdout" in q:
            ok = ok and (completed.stdout == q["expected_stdout"])
        for needle in q.get("contains", []):
            ok = ok and (needle in completed.stdout)
        for forbidden in q.get("not_contains", []):
            ok = ok and (forbidden not in completed.stdout)
        print(f"| {qid} | {'PASS' if ok else 'FAIL'} | {elapsed_ms:.1f} |")
        if not ok:
            failures += 1
            print(
                f"FAIL [{qid}] exit={completed.returncode}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
                file=sys.stderr,
            )
    print(f"\n{len(questions) - failures}/{len(questions)} passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
