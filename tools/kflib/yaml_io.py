"""YAML frontmatter & schema I/O with PyYAML primary and zero-dependency stdlib fallback."""

from __future__ import annotations

import json
import math
import os
import re
from typing import Any

try:
    import yaml as _pyyaml  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    _pyyaml = None


class YAMLError(ValueError):
    """Raised when YAML text cannot be parsed or serialized."""


_SIMPLE_STR_RE = re.compile(r"^[A-Za-z0-9_./@-][A-Za-z0-9_./@ -]*$")
_YAML_KEYWORDS = {
    "true", "false", "null", "~", "yes", "no", "on", "off",
    "True", "False", "Null", "TRUE", "FALSE", "NULL", "Yes", "No", "On", "Off",
}
_NUM_RE = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")


def has_pyyaml(force_fallback: bool = False) -> bool:
    if force_fallback or os.environ.get("KF_NO_PYYAML") == "1":
        return False
    return _pyyaml is not None


def load_yaml(text: str, *, force_fallback: bool = False) -> Any:
    if not text.strip():
        return None
    if has_pyyaml(force_fallback) and _pyyaml is not None:
        try:
            # Use BaseLoader-free safe_load, keeping ISO dates as strings if quoted;
            # normalize datetime.date/datetime objects if unquoted in user files.
            loaded = _pyyaml.safe_load(text)
            return _normalize_loaded(loaded)
        except Exception as exc:
            raise YAMLError(str(exc)) from exc
    return _parse_fallback_yaml(text)


def dump_yaml(data: Any, *, sort_keys: bool = False, force_fallback: bool = False) -> str:
    # Always emit canonical deterministic block YAML so output is byte-identical
    # whether PyYAML is installed or running on bare Python stdlib.
    _ = force_fallback
    lines = _dump_fallback_node(data, indent=0, sort_keys=sort_keys)
    return "\n".join(lines) + "\n"


def _normalize_loaded(value: Any) -> Any:
    import datetime as dt

    if isinstance(value, dt.datetime):
        if value.tzinfo is not None:
            return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _normalize_loaded(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_loaded(v) for v in value]
    return value


# ---------------------------------------------------------------------------
# Zero-dependency fallback YAML serializer & parser
# ---------------------------------------------------------------------------

def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise YAMLError(f"non-finite float not allowed in YAML: {value!r}")
        return repr(value)
    if isinstance(value, str):
        if (
            value
            and value == value.strip()
            and _SIMPLE_STR_RE.fullmatch(value)
            and value not in _YAML_KEYWORDS
            and not _NUM_RE.fullmatch(value)
        ):
            return value
        return json.dumps(value, ensure_ascii=False)
    raise YAMLError(f"unsupported YAML scalar type: {type(value).__name__}")


def _dump_fallback_node(value: Any, indent: int, sort_keys: bool) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        if not value:
            return [f"{prefix}{{}}"]
        keys = sorted(value.keys()) if sort_keys else list(value.keys())
        lines: list[str] = []
        for k in keys:
            key_str = _format_scalar(str(k))
            v = value[k]
            if isinstance(v, dict):
                if not v:
                    lines.append(f"{prefix}{key_str}: {{}}")
                else:
                    lines.append(f"{prefix}{key_str}:")
                    lines.extend(_dump_fallback_node(v, indent + 2, sort_keys))
            elif isinstance(v, list):
                if not v:
                    lines.append(f"{prefix}{key_str}: []")
                else:
                    lines.append(f"{prefix}{key_str}:")
                    lines.extend(_dump_fallback_node(v, indent + 2, sort_keys))
            else:
                lines.append(f"{prefix}{key_str}: {_format_scalar(v)}")
        return lines
    if isinstance(value, list):
        if not value:
            return [f"{prefix}[]"]
        lines = []
        for item in value:
            if isinstance(item, dict):
                if not item:
                    lines.append(f"{prefix}- {{}}")
                else:
                    sub = _dump_fallback_node(item, indent + 2, sort_keys)
                    first = sub[0].lstrip()
                    lines.append(f"{prefix}- {first}")
                    lines.extend(sub[1:])
            elif isinstance(item, list):
                lines.append(f"{prefix}-")
                lines.extend(_dump_fallback_node(item, indent + 2, sort_keys))
            else:
                lines.append(f"{prefix}- {_format_scalar(item)}")
        return lines
    return [f"{prefix}{_format_scalar(value)}"]


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    for idx, ch in enumerate(line):
        if escaped:
            escaped = False
            continue
        if ch == "\\" and in_double:
            escaped = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if idx == 0 or line[idx - 1].isspace():
                return line[:idx].rstrip()
    return line.rstrip()


def _split_key_value(content: str) -> tuple[str, str | None]:
    in_single = False
    in_double = False
    escaped = False
    for idx, ch in enumerate(content):
        if escaped:
            escaped = False
            continue
        if ch == "\\" and in_double:
            escaped = True
            continue
        if ch == "'" and not in_single and not in_double:
            in_single = True
        elif ch == "'" and in_single:
            in_single = False
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == ":" and not in_single and not in_double:
            rest = content[idx + 1:]
            if not rest or rest[0].isspace():
                raw_key = content[:idx].strip()
                key = str(_parse_scalar(raw_key)) if (raw_key.startswith('"') or raw_key.startswith("'")) else raw_key
                val = rest.strip()
                return key, (val if val != "" else None)
    raise YAMLError(f"expected mapping key: value, got {content!r}")


def _split_inline_items(inner: str) -> list[str]:
    if not inner.strip():
        return []
    items: list[str] = []
    cur: list[str] = []
    depth = 0
    in_single = False
    in_double = False
    escaped = False
    for ch in inner:
        if escaped:
            cur.append(ch)
            escaped = False
            continue
        if ch == "\\" and in_double:
            cur.append(ch)
            escaped = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
            elif ch == "," and depth == 0:
                items.append("".join(cur).strip())
                cur = []
                continue
        cur.append(ch)
    if cur:
        items.append("".join(cur).strip())
    return items


def _parse_scalar(token: str) -> Any:
    token = token.strip()
    if token in ("", "null", "~", "Null", "NULL"):
        return None
    if token in ("true", "True", "TRUE"):
        return True
    if token in ("false", "False", "FALSE"):
        return False
    if token == "[]":
        return []
    if token == "{}":
        return {}
    if token.startswith('"') and token.endswith('"') and len(token) >= 2:
        try:
            return json.loads(token)
        except json.JSONDecodeError as exc:
            raise YAMLError(f"invalid double-quoted string {token!r}: {exc}") from exc
    if token.startswith("'") and token.endswith("'") and len(token) >= 2:
        return token[1:-1].replace("''", "'")
    if token.startswith("[") and token.endswith("]"):
        return [_parse_scalar(part) for part in _split_inline_items(token[1:-1])]
    if token.startswith("{") and token.endswith("}"):
        result: dict[str, Any] = {}
        for part in _split_inline_items(token[1:-1]):
            k, v = _split_key_value(part)
            result[k] = _parse_scalar(v or "")
        return result
    if re.fullmatch(r"[+-]?\d+", token):
        return int(token)
    if _NUM_RE.fullmatch(token):
        return float(token)
    return token


def _parse_fallback_yaml(text: str) -> Any:
    cleaned: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        if "\t" in raw_line:
            raise YAMLError("tabs are not permitted for YAML indentation")
        stripped_comment = _strip_comment(raw_line)
        if not stripped_comment.strip():
            continue
        if stripped_comment.strip() == "---":
            continue
        indent = len(stripped_comment) - len(stripped_comment.lstrip(" "))
        cleaned.append((indent, stripped_comment.lstrip(" ")))
    if not cleaned:
        return None
    val, idx = _parse_block(cleaned, 0, cleaned[0][0])
    if idx != len(cleaned):
        raise YAMLError(f"unexpected trailing YAML content at line {idx + 1}: {cleaned[idx][1]!r}")
    return val


def _parse_block(lines: list[tuple[int, str]], index: int, base_indent: int) -> tuple[Any, int]:
    indent, content = lines[index]
    if indent != base_indent:
        raise YAMLError(f"unexpected indentation {indent} (expected {base_indent}) near {content!r}")
    if content == "- " or content == "-" or content.startswith("- "):
        return _parse_list(lines, index, base_indent)
    if ":" in content:
        is_kv = False
        try:
            _split_key_value(content)
            is_kv = True
        except YAMLError:
            is_kv = False
        if is_kv:
            return _parse_dict(lines, index, base_indent)
    return _parse_scalar(content), index + 1


def _consume_wrapped_scalar(lines: list[tuple[int, str]], index: int, min_continuation_indent: int, initial: str) -> tuple[str, int]:
    parts = [initial]
    n = len(lines)
    while index < n and lines[index][0] >= min_continuation_indent:
        parts.append(lines[index][1].strip())
        index += 1
    return " ".join(parts), index


def _parse_dict(lines: list[tuple[int, str]], index: int, base_indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    n = len(lines)
    while index < n:
        indent, content = lines[index]
        if indent < base_indent:
            break
        if indent > base_indent:
            raise YAMLError(f"unexpected over-indent in mapping near {content!r}")
        if content == "-" or content.startswith("- "):
            break
        key, val_str = _split_key_value(content)
        index += 1
        if val_str is not None:
            if val_str in ("|", ">", "|-", ">-"):
                block_lines: list[str] = []
                block_indent: int | None = None
                while index < n and lines[index][0] > base_indent:
                    b_ind, b_text = lines[index]
                    if block_indent is None:
                        block_indent = b_ind
                    pad = " " * max(0, b_ind - block_indent)
                    block_lines.append(pad + b_text)
                    index += 1
                joiner = "\n" if val_str.startswith("|") else " "
                result[key] = joiner.join(block_lines)
            else:
                joined, index = _consume_wrapped_scalar(lines, index, base_indent + 1, val_str)
                result[key] = _parse_scalar(joined)
        else:
            if index < n and lines[index][0] > base_indent:
                child, index = _parse_block(lines, index, lines[index][0])
                result[key] = child
            elif index < n and lines[index][0] == base_indent and (
                lines[index][1] == "-" or lines[index][1].startswith("- ")
            ):
                child, index = _parse_list(lines, index, base_indent)
                result[key] = child
            else:
                result[key] = None
    return result, index


def _parse_list(lines: list[tuple[int, str]], index: int, base_indent: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    n = len(lines)
    while index < n:
        indent, content = lines[index]
        if indent < base_indent:
            break
        if indent > base_indent:
            raise YAMLError(f"unexpected over-indent in sequence near {content!r}")
        if not (content == "-" or content.startswith("- ")):
            break
        rest = content[1:].strip()
        index += 1
        if not rest:
            if index < n and lines[index][0] > base_indent:
                child, index = _parse_block(lines, index, lines[index][0])
                items.append(child)
            else:
                items.append(None)
            continue
        # Check if inline mapping start `- key: value`
        map_key: str | None = None
        map_val: str | None = None
        if not (rest.startswith('"') or rest.startswith("'") or rest.startswith("[") or rest.startswith("{")):
            try:
                map_key, map_val = _split_key_value(rest)
            except YAMLError:
                map_key = None
        if map_key is not None:
            obj: dict[str, Any] = {}
            if map_val is not None:
                joined, index = _consume_wrapped_scalar(lines, index, base_indent + 3, map_val)
                obj[map_key] = _parse_scalar(joined)
            else:
                if index < n and lines[index][0] > base_indent + 2:
                    child, index = _parse_block(lines, index, lines[index][0])
                    obj[map_key] = child
                elif index < n and lines[index][0] == base_indent + 2 and (
                    lines[index][1] == "-" or lines[index][1].startswith("- ")
                ):
                    child, index = _parse_list(lines, index, base_indent + 2)
                    obj[map_key] = child
                else:
                    obj[map_key] = None
            if index < n and lines[index][0] == base_indent + 2 and not (
                lines[index][1] == "-" or lines[index][1].startswith("- ")
            ):
                more, index = _parse_dict(lines, index, base_indent + 2)
                obj.update(more)
            items.append(obj)
        else:
            joined, index = _consume_wrapped_scalar(lines, index, base_indent + 1, rest)
            items.append(_parse_scalar(joined))
    return items, index
