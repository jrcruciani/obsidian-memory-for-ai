#!/usr/bin/env python3
"""Offline exact-query evaluation; latency is reported, never a pass threshold."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import yaml


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, default=Path(__file__).resolve().parents[2] / "examples/v4.1-minimal-vault")
    args = parser.parse_args()
    vault = args.vault.resolve()
    questions = yaml.safe_load(Path(__file__).with_name("questions.yaml").read_text(encoding="utf-8"))["questions"]
    env = dict(os.environ, MEMORY_TODAY="2026-09-21")
    env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}"
    print("| Question | Result | Latency (ms) |")
    print("|---|---|---:|")
    failures = 0
    for question in questions:
        command = question["query"]
        if not isinstance(command, list) or not command or command[0] != "tools/query.sh":
            raise ValueError(f"{question['id']}: expected an exact query.sh argument list")
        if not all(isinstance(arg, str) for arg in command):
            raise ValueError(f"{question['id']}: query arguments must be strings")
        start = time.perf_counter()
        completed = subprocess.run(["sh", *command], cwd=vault, env=env, capture_output=True, text=True, timeout=30)
        elapsed = (time.perf_counter() - start) * 1000
        passed = completed.returncode == question.get("exit_code", 0)
        if "expected_stdout" in question:
            passed = passed and completed.stdout == question["expected_stdout"]
        passed = passed and all(value in completed.stdout for value in question.get("contains", []))
        passed = passed and all(value not in completed.stdout for value in question.get("not_contains", []))
        print(f"| {question['id']} | {'PASS' if passed else 'FAIL'} | {elapsed:.1f} |")
        if not passed:
            failures += 1
            print(f"{question['id']}: exit={completed.returncode}\n{completed.stdout}{completed.stderr}", file=sys.stderr)
    print(f"\n{len(questions) - failures}/{len(questions)} passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, yaml.YAMLError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
