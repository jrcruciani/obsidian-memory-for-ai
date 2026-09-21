"""Shared JSON envelope and explicit CLI error boundary."""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import sys
from pathlib import Path
from typing import Any, Callable

import yaml


_result: Any = None
json_mode = False


def result(data: Any) -> None:
    global _result
    _result = data


def serializable(value: Any) -> str:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    raise TypeError(f"cannot encode {type(value).__name__}")


def run(main: Callable[[], int]) -> int:
    global _result, json_mode
    _result = None
    end = sys.argv.index("--") if "--" in sys.argv else len(sys.argv)
    json_mode = "--json" in sys.argv[1:end]
    sys.argv[:] = [arg for index, arg in enumerate(sys.argv) if not (index < end and arg == "--json")]
    output, diagnostics = io.StringIO(), io.StringIO()
    with contextlib.ExitStack() as stack:
        if json_mode:
            stack.enter_context(contextlib.redirect_stdout(output))
            stack.enter_context(contextlib.redirect_stderr(diagnostics))
        try:
            code = main()
        except (OSError, ValueError, yaml.YAMLError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            code = 1
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    if json_mode:
        if diagnostics.getvalue():
            print(diagnostics.getvalue(), end="", file=sys.stderr)
        envelope = {"ok": code == 0, "exit_code": code, "data": _result,
                    "text": output.getvalue(), "diagnostics": diagnostics.getvalue()}
        try:
            encoded = json.dumps(envelope, ensure_ascii=False, allow_nan=False, default=serializable)
        except (TypeError, ValueError) as exc:
            code = 1
            message = f"ERROR: invalid JSON result: {exc}"
            print(message, file=sys.stderr)
            encoded = json.dumps({"ok": False, "exit_code": code, "data": None,
                                  "text": "", "diagnostics": message})
        print(encoded)
    return code
