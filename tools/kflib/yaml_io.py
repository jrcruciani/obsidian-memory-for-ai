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


_BLOCK_HEADER_RE = re.compile(r"^([|>])(?:([1-9])([+-])?|([+-])([1-9])?)?$")


def _parse_block_header(token: str) -> tuple[str, int | None, str] | None:
    m = _BLOCK_HEADER_RE.fullmatch(token.strip())
    if not m:
        return None
    style = m.group(1)
    ind_str = m.group(2) or m.group(5)
    chomp_str = m.group(3) or m.group(4) or "clip"
    return style, (int(ind_str) if ind_str else None), chomp_str


def _next_structural_line(raw_lines: list[str], index: int) -> tuple[int, int, str] | None:
    n = len(raw_lines)
    while index < n:
        raw = raw_lines[index]
        after_spaces = raw.lstrip(" ")
        if after_spaces.startswith("\t"):
            raise YAMLError("tabs are not permitted for YAML indentation")
        stripped = _strip_comment(raw)
        if not stripped.strip():
            index += 1
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        content = stripped.lstrip(" ")
        if indent == 0 and content in ("---", "..."):
            index += 1
            continue
        return index, indent, content
    return None


def _is_mapping_entry(content: str) -> bool:
    if ":" not in content:
        return False
    try:
        _split_key_value(content)
        return True
    except YAMLError:
        return False


def _parse_block_scalar(
    raw_lines: list[str],
    index: int,
    parent_indent: int,
    header_token: str,
) -> tuple[str, int]:
    parsed_hdr = _parse_block_header(header_token)
    if parsed_hdr is None:
        raise YAMLError(f"invalid block scalar header {header_token!r}")
    style, explicit_indent, chomp = parsed_hdr
    n = len(raw_lines)

    block_indent: int | None = (max(0, parent_indent) + explicit_indent) if explicit_indent is not None else None
    if block_indent is None:
        scan = index
        max_leading_blank_spaces = 0
        while scan < n:
            raw = raw_lines[scan]
            leading_spaces = len(raw) - len(raw.lstrip(" "))
            rest = raw[leading_spaces:]
            if rest == "":
                max_leading_blank_spaces = max(max_leading_blank_spaces, leading_spaces)
                scan += 1
                continue
            if leading_spaces == 0 and rest in ("---", "..."):
                break
            if leading_spaces <= parent_indent:
                break
            if rest.startswith("\t"):
                raise YAMLError("tabs are not permitted for YAML indentation")
            if max_leading_blank_spaces > leading_spaces:
                raise YAMLError("leading blank line is more indented than first content line in block scalar")
            block_indent = leading_spaces
            break

    collected: list[str] = []
    if block_indent is None:
        while index < n:
            raw = raw_lines[index]
            if raw.lstrip(" ") == "":
                collected.append("")
                index += 1
            else:
                break
    else:
        while index < n:
            raw = raw_lines[index]
            leading_spaces = len(raw) - len(raw.lstrip(" "))
            rest = raw[leading_spaces:]
            if rest == "":
                collected.append(raw[block_indent:] if len(raw) >= block_indent else "")
                index += 1
                continue
            if leading_spaces == 0 and rest in ("---", "...") and parent_indent < 0:
                break
            if leading_spaces < block_indent:
                if leading_spaces <= parent_indent:
                    break
                if rest.startswith("\t"):
                    raise YAMLError("tabs are not permitted for YAML indentation")
                raise YAMLError(
                    f"under-indented line in block scalar (indent {leading_spaces}, expected >= {block_indent})"
                )
            collected.append(raw[block_indent:])
            index += 1

    trailing_empty = 0
    while collected and collected[-1] == "":
        collected.pop()
        trailing_empty += 1

    if not collected:
        if chomp == "+":
            return "\n" * trailing_empty, index
        return "", index

    if style == "|":
        core = "\n".join(collected)
    else:
        out_parts: list[str] = []
        pos = 0
        while pos < len(collected) and collected[pos] == "":
            out_parts.append("\n")
            pos += 1
        prev_line = collected[pos]
        out_parts.append(prev_line)
        pos += 1
        empty_between = 0
        while pos < len(collected):
            cur_line = collected[pos]
            pos += 1
            if cur_line == "":
                empty_between += 1
                continue
            prev_indented = prev_line[0] in (" ", "\t")
            cur_indented = cur_line[0] in (" ", "\t")
            if not prev_indented and not cur_indented:
                out_parts.append(" " if empty_between == 0 else ("\n" * empty_between))
            else:
                out_parts.append("\n" * (empty_between + 1))
            out_parts.append(cur_line)
            prev_line = cur_line
            empty_between = 0
        core = "".join(out_parts)

    if chomp == "-":
        return core, index
    if chomp == "+":
        return core + "\n" + ("\n" * trailing_empty), index
    return core + "\n", index


def _is_self_contained_scalar(token: str) -> bool:
    s = token.strip()
    return (
        (len(s) >= 2 and s[0] == '"' and s[-1] == '"')
        or (len(s) >= 2 and s[0] == "'" and s[-1] == "'")
        or (len(s) >= 2 and s[0] == "[" and s[-1] == "]")
        or (len(s) >= 2 and s[0] == "{" and s[-1] == "}")
    )


def _consume_wrapped_scalar(
    raw_lines: list[str],
    index: int,
    min_continuation_indent: int,
    initial: str,
) -> tuple[str, int]:
    if _is_self_contained_scalar(initial):
        return initial, index
    chunks = [initial]
    n = len(raw_lines)
    scan = index
    blank_count = 0
    while scan < n:
        raw = raw_lines[scan]
        if raw.lstrip(" ").startswith("\t"):
            raise YAMLError("tabs are not permitted for YAML indentation")
        if raw.strip() == "":
            blank_count += 1
            scan += 1
            continue
        if raw.lstrip(" ").startswith("#"):
            break
        stripped = _strip_comment(raw)
        ind = len(stripped) - len(stripped.lstrip(" "))
        txt = stripped.lstrip(" ")
        if ind < min_continuation_indent:
            break
        if txt == "-" or txt.startswith("- ") or _is_mapping_entry(txt):
            break
        sep = ("\n" * blank_count) if blank_count > 0 else " "
        chunks.append(sep + txt.strip())
        scan += 1
        index = scan
        blank_count = 0
    return "".join(chunks), index


def _parse_fallback_yaml(text: str) -> Any:
    raw_lines = text.splitlines()
    first = _next_structural_line(raw_lines, 0)
    if first is None:
        return None
    line_idx, base_indent, content = first
    if _parse_block_header(content) is not None:
        val, next_idx = _parse_block_scalar(raw_lines, line_idx + 1, -1, content)
    else:
        val, next_idx = _parse_block(raw_lines, line_idx, base_indent)
    rem = _next_structural_line(raw_lines, next_idx)
    if rem is not None:
        raise YAMLError(f"unexpected trailing YAML content at line {rem[0] + 1}: {rem[2]!r}")
    return val


def _parse_block(raw_lines: list[str], index: int, base_indent: int) -> tuple[Any, int]:
    nxt = _next_structural_line(raw_lines, index)
    if nxt is None:
        return None, len(raw_lines)
    index, indent, content = nxt
    if indent != base_indent:
        raise YAMLError(f"unexpected indentation {indent} (expected {base_indent}) near {content!r}")
    if content == "-" or content.startswith("- "):
        return _parse_list(raw_lines, index, base_indent)
    if _is_mapping_entry(content):
        return _parse_dict(raw_lines, index, base_indent)
    if _parse_block_header(content) is not None:
        return _parse_block_scalar(raw_lines, index + 1, base_indent - 1, content)
    joined, next_idx = _consume_wrapped_scalar(raw_lines, index + 1, base_indent + 1, content)
    return _parse_scalar(joined), next_idx


def _parse_dict(raw_lines: list[str], index: int, base_indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while True:
        nxt = _next_structural_line(raw_lines, index)
        if nxt is None:
            return result, len(raw_lines)
        index, indent, content = nxt
        if indent < base_indent:
            return result, index
        if indent > base_indent:
            raise YAMLError(f"unexpected over-indent in mapping near {content!r}")
        if content == "-" or content.startswith("- "):
            return result, index
        key, val_str = _split_key_value(content)
        index += 1
        if val_str is not None:
            if _parse_block_header(val_str) is not None:
                result[key], index = _parse_block_scalar(raw_lines, index, base_indent, val_str)
            else:
                joined, index = _consume_wrapped_scalar(raw_lines, index, base_indent + 1, val_str)
                result[key] = _parse_scalar(joined)
        else:
            child_nxt = _next_structural_line(raw_lines, index)
            if child_nxt is not None and child_nxt[1] > base_indent:
                result[key], index = _parse_block(raw_lines, child_nxt[0], child_nxt[1])
            elif child_nxt is not None and child_nxt[1] == base_indent and (
                child_nxt[2] == "-" or child_nxt[2].startswith("- ")
            ):
                result[key], index = _parse_list(raw_lines, child_nxt[0], base_indent)
            else:
                result[key] = None


def _parse_list(raw_lines: list[str], index: int, base_indent: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    while True:
        nxt = _next_structural_line(raw_lines, index)
        if nxt is None:
            return items, len(raw_lines)
        index, indent, content = nxt
        if indent < base_indent:
            return items, index
        if indent > base_indent:
            raise YAMLError(f"unexpected over-indent in sequence near {content!r}")
        if not (content == "-" or content.startswith("- ")):
            return items, index
        rest = content[1:].strip()
        index += 1
        if not rest:
            child_nxt = _next_structural_line(raw_lines, index)
            if child_nxt is not None and child_nxt[1] > base_indent:
                child, index = _parse_block(raw_lines, child_nxt[0], child_nxt[1])
                items.append(child)
            else:
                items.append(None)
            continue
        if _parse_block_header(rest) is not None:
            blk_val, index = _parse_block_scalar(raw_lines, index, base_indent, rest)
            items.append(blk_val)
            continue
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
                if _parse_block_header(map_val) is not None:
                    obj[map_key], index = _parse_block_scalar(raw_lines, index, base_indent + 2, map_val)
                else:
                    joined, index = _consume_wrapped_scalar(raw_lines, index, base_indent + 3, map_val)
                    obj[map_key] = _parse_scalar(joined)
            else:
                child_nxt = _next_structural_line(raw_lines, index)
                if child_nxt is not None and child_nxt[1] > base_indent + 2:
                    obj[map_key], index = _parse_block(raw_lines, child_nxt[0], child_nxt[1])
                elif child_nxt is not None and child_nxt[1] == base_indent + 2 and (
                    child_nxt[2] == "-" or child_nxt[2].startswith("- ")
                ):
                    obj[map_key], index = _parse_list(raw_lines, child_nxt[0], base_indent + 2)
                else:
                    obj[map_key] = None
            more_nxt = _next_structural_line(raw_lines, index)
            if more_nxt is not None and more_nxt[1] == base_indent + 2 and not (
                more_nxt[2] == "-" or more_nxt[2].startswith("- ")
            ):
                more, index = _parse_dict(raw_lines, more_nxt[0], base_indent + 2)
                obj.update(more)
            items.append(obj)
        else:
            joined, index = _consume_wrapped_scalar(raw_lines, index, base_indent + 1, rest)
            items.append(_parse_scalar(joined))
