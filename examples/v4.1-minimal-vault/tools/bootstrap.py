"""Deterministic, character-budgeted context built only from canonical records."""

from __future__ import annotations

import datetime as dt
from collections import Counter
from pathlib import Path
from typing import Any

from lint import parse_date, parse_datetime, rel
from memory_model import config, entities, observed, records, today, visible
from rebuild_indexes import render_value


DEFAULTS = {"budget_chars": 6000, "lookback_days": 30,
            "sections": ["pinned_facts", {"recent_decisions": 5}, {"active_entities": 5}, {"recent_events": 10}]}
TITLES = {"pinned_facts": "Pinned facts", "recent_decisions": "Recent decisions",
          "active_entities": "Active entities", "recent_events": "Recent events"}


def settings(root: Path) -> dict[str, Any]:
    result = dict(DEFAULTS, **config(root, "bootstrap.yaml"))
    for key in ("budget_chars", "lookback_days"):
        if isinstance(result[key], bool) or not isinstance(result[key], int) or result[key] < 0:
            raise ValueError(f"bootstrap {key} must be a non-negative integer")
    if not isinstance(result["sections"], list):
        raise ValueError("bootstrap sections must be a list")
    seen = set()
    for entry in result["sections"]:
        if isinstance(entry, str):
            name, count = entry, None
        elif isinstance(entry, dict) and len(entry) == 1:
            name, count = next(iter(entry.items()))
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("bootstrap section counts must be non-negative integers")
        else:
            raise ValueError("invalid bootstrap section")
        if name not in TITLES or name in seen:
            raise ValueError(f"unknown or duplicate bootstrap section: {name!r}")
        seen.add(name)
    return result


def candidates(root: Path, options: dict[str, Any]) -> dict[str, list[tuple[str, str, str]]]:
    result: dict[str, list[tuple[str, str, str]]] = {name: [] for name in TITLES}
    now = today()
    event_rows = []
    for path, data in records(root, "memory/events", "event"):
        date = parse_datetime(data["occurred_at"]).astimezone(dt.timezone.utc).date()
        if date <= now:
            event_rows.append((path, data, date))
            result["recent_events"].append((date.isoformat(), rel(path, root),
                                           f"- {date}: {data['summary']} (`{rel(path, root)}`)\n"))
    for path, data in records(root, "memory/facts", "fact"):
        if data.get("pinned") is True and visible(data) and visible(data, now):
            result["pinned_facts"].append((observed(data).date().isoformat(), rel(path, root),
                                          f"- **{data['entity']}/{data['predicate']}**: {render_value(data.get('value'))} (`{rel(path, root)}`)\n"))
    for path, data in records(root, "memory/decisions", "decision"):
        date = parse_date(data["decided_at"])
        if date and date <= now and data.get("status") == "accepted":
            result["recent_decisions"].append((date.isoformat(), rel(path, root),
                                              f"- {date}: {data['title']} (`{rel(path, root)}`)\n"))
    cutoff = now - dt.timedelta(days=options["lookback_days"])
    counts: Counter[str] = Counter()
    latest: dict[str, dt.date] = {}
    for _, data, date in event_rows:
        if date < cutoff:
            continue
        for entity in set(data.get("entities", [])):
            counts[entity] += 1
            latest[entity] = max(latest.get(entity, dt.date.min), date)
    declarations = entities(root)
    for entity, count in sorted(counts.items(), key=lambda row: (-row[1], -latest[row[0]].toordinal(), row[0])):
        display = declarations.get(entity, {}).get("display", entity)
        result["active_entities"].append((latest[entity].isoformat(), f"memory/entities.md#{entity}",
                                          f"- **{display}** (`{entity}`): {count} event(s), latest {latest[entity]}\n"))
    return result


def render(items: list[tuple[str, str]], budget: int, date: dt.date) -> str:
    content = "# Bootstrap\n\n"
    section = None
    for name, line in items:
        if name != section:
            if section is not None:
                content += "\n"
            content += f"## {TITLES[name]}\n\n"
            section = name
        content += line
    content += "\n"
    length = 0
    while True:
        text = content + f"<!-- bootstrap: {len(items)} items, {length}/{budget} chars, generated {date} -->\n"
        if len(text) == length:
            return text
        length = len(text)


def build_bootstrap(root: Path) -> str:
    options = settings(root)
    budget = options["budget_chars"]
    date = today()
    selected: list[tuple[str, str]] = []
    text = render(selected, budget, date)
    if len(text) > budget:
        raise ValueError(f"bootstrap budget_chars={budget} cannot fit its header and footer ({len(text)} chars)")
    available = candidates(root, options)
    for section in options["sections"]:
        name, count = (section, None) if isinstance(section, str) else next(iter(section.items()))
        rows = available[name]
        if name == "active_entities" and count is not None:
            rows = rows[:count]
        rows = sorted(sorted(rows, key=lambda row: row[1]), key=lambda row: row[0], reverse=True)
        if count is not None:
            rows = rows[:count]
        for _, _, line in rows:
            candidate = render([*selected, (name, line)], budget, date)
            if len(candidate) > budget:
                return text
            selected.append((name, line))
            text = candidate
    return text
