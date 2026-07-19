"""Evidence helpers for two-layer team observability.

Outer spawn: harness recorded a provider process start (RUN_STARTED /
``_absoloop_spawn``). Inner teams: best-effort markers in streams or text
(``spawn_subagent``, Agent Teams, teammate tools). Used by characterization
tests and the ZComb bridge — never required for acceptance.
"""
from __future__ import annotations

import json
import pathlib
import re
from typing import Any, Iterable, List, Optional

from .core import AgentEvent, EventType

_INNER_MARKERS = re.compile(
    r"(spawn_subagent|spawn_agent|agent.?team|teammate|subagent|"
    r"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS)",
    re.IGNORECASE,
)


def events_show_outer_spawn(events: Iterable[AgentEvent]) -> bool:
    """True when the harness recorded a provider process start."""
    for event in events:
        if event.type == EventType.RUN_STARTED:
            return True
        if event.raw_type == "_absoloop_spawn":
            return True
    return False


def text_shows_inner_teams(text: str) -> bool:
    return bool(_INNER_MARKERS.search(text or ""))


def events_show_inner_teams(events: Iterable[AgentEvent]) -> bool:
    """Best-effort: vendor streams differ; any team/subagent marker counts."""
    for event in events:
        blob = " ".join([
            event.text or "",
            event.raw_type or "",
            json.dumps(event.data, sort_keys=True) if event.data else "",
        ])
        if text_shows_inner_teams(blob):
            return True
        if event.type == EventType.TOOL_STARTED and text_shows_inner_teams(
                str(event.data.get("tool", ""))):
            return True
    return False


def load_events_jsonl(path: pathlib.Path) -> List[AgentEvent]:
    events: List[AgentEvent] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return events
    for line in lines:
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        etype = raw.get("type") or raw.get("event_type")
        try:
            event_type = EventType(etype) if etype else EventType.UNKNOWN
        except ValueError:
            event_type = EventType.UNKNOWN
        events.append(AgentEvent(
            type=event_type,
            provider=str(raw.get("provider", "")),
            text=str(raw.get("text", "") or ""),
            raw_type=str(raw.get("raw_type", "") or ""),
            data=raw.get("data") if isinstance(raw.get("data"), dict) else {},
        ))
    return events


def mission_ledger_shows_spawn(ledger_path: pathlib.Path,
                               engine: Optional[str] = None) -> bool:
    """True when the mission ledger recorded at least one agent_run spawn."""
    try:
        lines = ledger_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return False
    for line in lines:
        try:
            row: Any = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or row.get("type") != "agent_run":
            continue
        if engine is None or row.get("engine") == engine:
            return True
    return False
