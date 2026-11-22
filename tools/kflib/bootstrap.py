"""Role-aware character-budgeted bootstrap builder for Knowledge Factory v5.0."""

from __future__ import annotations

import datetime as dt
from collections import Counter
from pathlib import Path
from typing import Any

from .model import (
    canonical_source_digest,
    is_current_record,
    is_fact_visible,
    load_entities,
    load_yaml_file,
    parse_date,
    parse_datetime,
    rel_path,
    scan_records,
    today,
)
from .schema_check import compute_stale_records

SECTION_TITLES = {
    "critical_guidance": "Active Guidance & Guardrails",
    "pinned_facts": "Pinned Facts",
    "active_skills": "Available Skills",
    "recent_decisions": "Accepted Decisions",
    "active_entities": "Active Entities",
    "recent_events": "Recent Events",
    "open_signals": "Open Signals & Gaps",
    "pending_proposals": "Pending Proposals",
    "stale_knowledge": "Stale Knowledge Requiring Review",
}

DEFAULT_BOOTSTRAP = {
    "default_profile": "default",
    "lookback_days": 45,
    "profiles": {
        "default": {
            "budget_chars": 6000,
            "sections": [
                "critical_guidance",
                "pinned_facts",
                {"active_skills": 8},
                {"recent_decisions": 5},
                {"active_entities": 6},
                {"recent_events": 8},
            ],
        },
        "executor": {
            "budget_chars": 5000,
            "sections": [
                "critical_guidance",
                "pinned_facts",
                {"active_skills": 10},
                {"recent_decisions": 5},
                {"active_entities": 5},
            ],
        },
        "curator": {
            "budget_chars": 6000,
            "sections": [
                {"open_signals": 12},
                {"pending_proposals": 8},
                {"stale_knowledge": 8},
                {"recent_events": 10},
                "critical_guidance",
            ],
        },
    },
}


def render_scalar_inline(value: Any) -> str:
    if isinstance(value, (list, dict)):
        import json

        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _collect_candidates(root: Path, lookback_days: int, profile: str) -> dict[str, list[tuple[str, str, str]]]:
    out: dict[str, list[tuple[str, str, str]]] = {k: [] for k in SECTION_TITLES}
    ref = today()

    # Guidance
    prio_rank = {"critical": "3", "high": "2", "normal": "1"}
    for path, fm, _ in scan_records(root, "knowledge/guidance", "guidance"):
        if not is_current_record(fm):
            continue
        scope = fm.get("scope", "all")
        if profile in {"executor", "curator"} and scope not in {"all", profile}:
            continue
        if profile == "default" and fm.get("priority") not in {"critical", "high"} and not fm.get("pinned"):
            continue
        r = rel_path(path, root)
        sort_key = f"{prio_rank.get(str(fm.get('priority')), '0')}:{fm.get('last_confirmed', '')}"
        line = f"- **[{fm.get('priority', 'normal').upper()}] {fm['title']}** (`{fm['domain']}` / `{scope}`): {fm['policy_rule']} (`{r}`)\n"
        out["critical_guidance"].append((sort_key, r, line))

    # Pinned facts
    for path, fm, _ in scan_records(root, "knowledge/facts", "fact"):
        if fm.get("pinned") is True and is_fact_visible(fm) and is_fact_visible(fm, ref):
            r = rel_path(path, root)
            obs = parse_datetime(fm["observed_at"]).date().isoformat()
            line = f"- **{fm['entity']}/{fm['predicate']}**: {render_scalar_inline(fm.get('value'))} (`{r}`)\n"
            out["pinned_facts"].append((obs, r, line))

    # Active skills
    for path, fm, _ in scan_records(root, "knowledge/skills", "skill"):
        if not is_current_record(fm):
            continue
        r = rel_path(path, root)
        triggers = ", ".join(str(t) for t in (fm.get("triggers") or [])[:3])
        obs = parse_datetime(fm["observed_at"]).date().isoformat()
        pin_prefix = "1:" if fm.get("pinned") else "0:"
        line = f"- **{fm['title']}** (`{fm['slug']}`, domain `{fm['domain']}`): triggers=[{triggers}] (`{r}`)\n"
        out["active_skills"].append((pin_prefix + obs, r, line))

    # Decisions
    for path, fm, _ in scan_records(root, "knowledge/decisions", "decision"):
        dec_date = parse_date(fm.get("decided_at"))
        if dec_date and dec_date <= ref and fm.get("status") == "accepted":
            r = rel_path(path, root)
            line = f"- **{fm['id']}** ({dec_date}): {fm['title']} — {fm['summary']} (`{r}`)\n"
            out["recent_decisions"].append((dec_date.isoformat(), r, line))

    # Events & active entities
    event_rows: list[tuple[dict[str, Any], dt.date]] = []
    for path, fm, _ in scan_records(root, "knowledge/events", "event"):
        ev_date = parse_datetime(fm["occurred_at"]).date()
        if ev_date <= ref:
            event_rows.append((fm, ev_date))
            r = rel_path(path, root)
            line = f"- {ev_date}: {fm['summary']} (`{r}`)\n"
            out["recent_events"].append((ev_date.isoformat(), r, line))

    cutoff = ref - dt.timedelta(days=lookback_days)
    counts: Counter[str] = Counter()
    latest: dict[str, dt.date] = {}
    for fm, ev_date in event_rows:
        if ev_date < cutoff:
            continue
        for ent in set(fm.get("entities") or []):
            counts[ent] += 1
            latest[ent] = max(latest.get(ent, dt.date.min), ev_date)
    entities = load_entities(root)
    for ent, cnt in sorted(counts.items(), key=lambda item: (-item[1], -latest[item[0]].toordinal(), item[0])):
        disp = entities.get(ent, {}).get("display", ent)
        sort_token = f"{cnt:05d}:{latest[ent].isoformat()}"
        line = f"- **{disp}** (`{ent}`): {cnt} event(s), latest {latest[ent]}\n"
        out["active_entities"].append((sort_token, f"knowledge/entities.md#{ent}", line))

    # Open signals (for curator)
    sev_rank = {"high": "3", "medium": "2", "low": "1"}
    for path, fm, _ in scan_records(root, "factory/signals", "signal"):
        if fm.get("status") == "open":
            r = rel_path(path, root)
            sort_key = f"{sev_rank.get(str(fm.get('severity')), '1')}:{fm.get('created_at', '')}"
            line = f"- **[{fm['severity'].upper()}/{fm['kind']}]** {fm['summary']} (`{r}`)\n"
            out["open_signals"].append((sort_key, r, line))

    # Pending proposals (for curator)
    for path, fm, _ in scan_records(root, "factory/proposals", "proposal"):
        if fm.get("status") in {"draft", "proposed", "changes_requested", "approved"}:
            r = rel_path(path, root)
            line = f"- **{fm['id']}** [{fm['status']}] {fm['title']} (`{r}`)\n"
            out["pending_proposals"].append((str(fm.get("created_at", "")), r, line))

    # Stale knowledge
    for stale_rel, reason in compute_stale_records(root):
        line = f"- `{stale_rel}`: {reason}\n"
        out["stale_knowledge"].append(("1", stale_rel, line))

    return out


def _render_bootstrap(
    items: list[tuple[str, str]],
    *,
    profile: str,
    budget: int,
    ref_date: dt.date,
    source_digest: str,
) -> str:
    header = (
        f"<!-- DO NOT EDIT: generated by kf rebuild | profile={profile} | source_digest={source_digest} -->\n"
        f"# Knowledge Factory Bootstrap ({profile})\n\n"
    )
    body = ""
    current_sec: str | None = None
    for sec, line in items:
        if sec != current_sec:
            if current_sec is not None:
                body += "\n"
            body += f"## {SECTION_TITLES[sec]}\n\n"
            current_sec = sec
        body += line
    if not items:
        body = "_No active bootstrap items in this profile yet._\n"
    body += "\n"
    estimated_len = 0
    while True:
        footer = f"<!-- bootstrap: profile={profile}, {len(items)} items, {estimated_len}/{budget} chars, generated {ref_date.isoformat()} -->\n"
        full = header + body + footer
        if len(full) == estimated_len:
            return full
        estimated_len = len(full)


def build_bootstrap(
    root: Path,
    *,
    profile: str | None = None,
    budget_override: int | None = None,
) -> str:
    cfg = dict(DEFAULT_BOOTSTRAP, **load_yaml_file(root / "factory/schema/bootstrap.yaml"))
    profiles = cfg.get("profiles", DEFAULT_BOOTSTRAP["profiles"])
    prof_name = profile or str(cfg.get("default_profile", "default"))
    if prof_name not in profiles:
        raise ValueError(f"unknown bootstrap profile {prof_name!r}; available: {sorted(profiles.keys())}")
    prof = profiles[prof_name]
    budget = budget_override if budget_override is not None else int(prof.get("budget_chars", 6000))
    lookback = int(cfg.get("lookback_days", 45))
    ref = today()
    digest = canonical_source_digest(root, ref)

    selected: list[tuple[str, str]] = []
    current_text = _render_bootstrap(selected, profile=prof_name, budget=budget, ref_date=ref, source_digest=digest)
    if len(current_text) > budget:
        raise ValueError(f"bootstrap budget_chars={budget} is too small for header/footer ({len(current_text)} chars)")

    candidates = _collect_candidates(root, lookback, prof_name)
    for sec_spec in prof.get("sections", []):
        if isinstance(sec_spec, str):
            sec_name, limit = sec_spec, None
        elif isinstance(sec_spec, dict) and len(sec_spec) == 1:
            sec_name, limit = next(iter(sec_spec.items()))
        else:
            raise ValueError(f"invalid bootstrap section spec: {sec_spec!r}")
        if sec_name not in SECTION_TITLES:
            raise ValueError(f"unknown bootstrap section: {sec_name!r}")
        rows = candidates[sec_name]
        # Deterministic sort: primary sort_key descending, tie-break path ascending
        rows = sorted(sorted(rows, key=lambda r: r[1]), key=lambda r: r[0], reverse=True)
        if limit is not None:
            rows = rows[: int(limit)]
        for _, _, line in rows:
            trial = _render_bootstrap([*selected, (sec_name, line)], profile=prof_name, budget=budget, ref_date=ref, source_digest=digest)
            if len(trial) > budget:
                return current_text
            selected.append((sec_name, line))
            current_text = trial
    return current_text
