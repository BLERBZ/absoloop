"""Optional ZComb Kanban UI for Absoloop mission monitoring.

Vendors the ZCombinator dashboard (zcomb/monitor) and bridges Absoloop
telemetry (.absoloop/tmp/monitor.json + live.jsonl + state/runtime) into
ZComb's agents/tasks/activity/metrics state files.

CLI:  absoloop --zcomb  → same briefing/launch as absoloop + Kanban UI
      absoloop zcomb [-C project] [--port N] [--no-browser]  → dashboard only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Optional

DEFAULT_PORT = 3141
HEARTBEAT_STALE_SECONDS = 90
# A spawned teammate is shown "active" while the mission is live and its
# spawn event is younger than this; afterwards it flips to "done".
TEAMMATE_ACTIVE_SECONDS = 600
TEAMMATE_SPAWN_PREFIX = "spawn teammate · "
TEAMMATE_TOOL_NAMES = ("Task", "Agent", "SpawnAgent", "spawn_subagent")

# Quirky teammate names, themed by what the teammate was spawned to do.
TEAMMATE_NAME_THEMES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("critic", "review", "adversar", "audit", "skeptic", "challenge"),
     ("Grumbles von Nitpick", "The Side-Eye Sommelier", "Redline Rhonda",
      "Doubtfire the Unimpressed", "Squint Eastwood")),
    (("test", "qa", "verif", "validat", "coverage"),
     ("Sgt. Breaksalot", "Captain Edge-Case", "Wanda the Wrecker",
      "Flake Detector Hector", "The Assertion Goblin")),
    (("research", "search", "explore", "investigat", "find", "scan", "analy"),
     ("Indiana Grep", "Ferret of Facts", "Rabbit-Hole Ranger",
      "Snoop Docs", "Magnifying-Glass Gus")),
    (("fix", "repair", "debug", "patch", "bug"),
     ("Duct-Tape Da Vinci", "Patchwork Pete", "The Solder Goblin",
      "Wrench Wench", "Kintsugi Kevin")),
    (("build", "implement", "write", "code", "creat", "develop"),
     ("Tinker Tantrum", "Keyboard Kraken", "The Commit Gremlin",
      "Scaffold Salamander", "Bricklayer Byte")),
    (("doc", "readme", "spec", "summar"),
     ("Quill Quibbler", "The Footnote Fiend", "Sir Scribbles-a-Lot",
      "Parchment Piranha")),
    (("secur", "vuln", "threat", "pentest"),
     ("Paranoia Petunia", "Lockpick Lenny", "Tinfoil Tarantula",
      "The Zero-Trust Walrus")),
    (("plan", "design", "architect", "strateg"),
     ("Blueprint Banshee", "Doodle Oracle", "Whiteboard Wizard Wes",
      "The Napkin-Sketch Sphinx")),
)
TEAMMATE_FALLBACK_NAMES = (
    "Wildcard Wombat", "Gizmo Gremlin", "Free-Range Frankie",
    "The Loose Cannonball", "Odd-Job Ozzy", "Miscellaneous Mabel",
)


def extract_zcomb_flag(argv: list[str]) -> tuple[list[str], bool]:
    """Pull `--zcomb` out of argv so it can ride on any absoloop invocation."""
    want = False
    cleaned: list[str] = []
    for arg in argv:
        if arg == "--zcomb":
            want = True
        else:
            cleaned.append(arg)
    return cleaned, want
KIND_TO_ACTIVITY = {
    "say": "status_change",
    "think": "research",
    "tool": "task_started",
    "verdict": "task_completed",
    "error": "error",
    "usage": "heartbeat",
    "start": "phase_start",
}

PHASE_PIPELINE = [
    (0, "Scaffold"),
    (1, "Execute"),
    (2, "Integrity"),
    (3, "Critic"),
    (4, "Human Gate"),
    (5, "Deliver"),
]


def zcomb_home() -> pathlib.Path:
    env = os.environ.get("ABSOLOOP_HOME")
    if env:
        root = pathlib.Path(env).expanduser().resolve()
        if (root / "zcomb" / "monitor").is_dir():
            return root / "zcomb"
    here = pathlib.Path(__file__).resolve().parent.parent
    return here / "zcomb"


def monitor_dir() -> pathlib.Path:
    return zcomb_home() / "monitor"


def project_state_dir(project: pathlib.Path) -> pathlib.Path:
    return project / ".absoloop" / "zcomb" / "state"


def _read_json(path: pathlib.Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _atomic_write(path: pathlib.Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def _iso(ts: Any) -> str:
    if isinstance(ts, (int, float)) and ts > 0:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _pid_alive(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def monitor_is_live(monitor: dict) -> bool:
    heartbeat = monitor.get("heartbeat_ts")
    fresh = (isinstance(heartbeat, (int, float))
             and time.time() - heartbeat < HEARTBEAT_STALE_SECONDS)
    return fresh and _pid_alive(monitor.get("pid"))


def _agent_status(live: bool, role: str, monitor: dict, state: dict) -> str:
    status = str(state.get("status") or monitor.get("status") or "").upper()
    if status in ("COMPLETED",):
        return "done"
    if status in ("BLOCKED", "BUDGET_EXHAUSTED", "REJECTED"):
        return "blocked"
    if not live:
        return "idle"
    agent = str(monitor.get("agent") or "").lower()
    phase = str(monitor.get("phase") or "").lower()
    if role == "builder":
        if "critic" in agent or "critic" in phase:
            return "idle"
        return "active"
    if role == "critic":
        if "critic" in agent or "critic" in phase or status == "FINAL_REVIEW":
            return "active"
        if status == "AWAITING_APPROVAL":
            return "done"
        return "idle"
    return "idle"


def _objective_history(runtime: dict, abs_dir: pathlib.Path) -> list[dict]:
    """Original objective plus each extend continuation note (oldest first).

    The Kanban objective bar shows the latest continuation by default and
    exposes the full chain in a dropdown. History is rebuilt from the
    append-only ledger (type=extension) with runtime.continuation as a
    fallback when the ledger has not caught up yet.
    """
    history: list[dict] = []
    objective = str(runtime.get("objective") or "").strip()
    if objective:
        history.append({
            "kind": "objective",
            "text": objective,
            "loopId": None,
            "previousLoopId": None,
            "ts": None,
        })

    ledger_path = abs_dir / "ledger.jsonl"
    if ledger_path.is_file():
        try:
            lines = ledger_path.read_text(
                encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or event.get("type") != "extension":
                continue
            note = str(event.get("note") or "").strip()
            if not note:
                continue
            history.append({
                "kind": "continuation",
                "text": note,
                "loopId": str(event.get("loop_id") or "").strip() or None,
                "previousLoopId": (
                    str(event.get("previous_loop_id") or "").strip() or None),
                "ts": event.get("ts") if isinstance(event.get("ts"),
                                                    (int, float)) else None,
            })

    cont = runtime.get("continuation")
    if isinstance(cont, dict):
        note = str(cont.get("note") or "").strip()
        if note:
            already = any(
                entry.get("kind") == "continuation" and entry.get("text") == note
                for entry in history
            )
            if not already:
                history.append({
                    "kind": "continuation",
                    "text": note,
                    "loopId": str(runtime.get("loop_id") or "").strip() or None,
                    "previousLoopId": (
                        str(cont.get("previous_loop_id") or "").strip() or None),
                    "ts": None,
                })
    return history


def _displayed_objective(history: list[dict], objective: str) -> str:
    """Latest continuation note, else the original objective."""
    for entry in reversed(history):
        if entry.get("kind") == "continuation" and entry.get("text"):
            return str(entry["text"])
    return objective


def _read_live_events(path: pathlib.Path, limit: int = 200) -> list[dict]:
    """Last `limit` parsed events from live.jsonl (oldest first)."""
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    events: list[dict] = []
    for line in lines[-limit:]:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _teammate_focus(detail: str) -> str:
    """Extract the teammate's focus from a 'spawn teammate · …' detail line."""
    if not detail.startswith(TEAMMATE_SPAWN_PREFIX):
        return ""
    rest = detail[len(TEAMMATE_SPAWN_PREFIX):].strip()
    for tool in TEAMMATE_TOOL_NAMES:
        if rest == tool:
            return "general support"
        prefix = f"{tool}: "
        if rest.startswith(prefix):
            return rest[len(prefix):].strip() or "general support"
    return rest or "general support"


def quirky_teammate_name(focus: str, used: Optional[set[str]] = None) -> str:
    """Deterministic off-the-wall name themed to the teammate's focus."""
    low = focus.lower()
    pool: tuple[str, ...] = TEAMMATE_FALLBACK_NAMES
    for keywords, names in TEAMMATE_NAME_THEMES:
        if any(k in low for k in keywords):
            pool = names
            break
    seed = int(hashlib.sha1(low.encode("utf-8")).hexdigest()[:8], 16)
    for offset in range(len(pool)):
        candidate = pool[(seed + offset) % len(pool)]
        if used is None or candidate not in used:
            if used is not None:
                used.add(candidate)
            return candidate
    # Pool exhausted — number the overflow so every teammate stays distinct.
    n = 2
    base = pool[seed % len(pool)]
    while f"{base} {n}" in (used or set()):
        n += 1
    name = f"{base} {n}"
    if used is not None:
        used.add(name)
    return name


def _collect_teammates(events: list[dict]) -> dict[str, dict]:
    """Fold spawn events into a registry keyed by focus text."""
    teammates: dict[str, dict] = {}
    used_names: set[str] = set()
    for event in events:
        if str(event.get("kind") or "") != "tool":
            continue
        detail = str(event.get("detail") or "")
        focus = _teammate_focus(detail)
        if not focus:
            continue
        key = focus.lower()
        ts = event.get("ts")
        ts = float(ts) if isinstance(ts, (int, float)) else time.time()
        if key in teammates:
            record = teammates[key]
            record["spawns"] += 1
            record["last_ts"] = max(record["last_ts"], ts)
        else:
            teammates[key] = {
                "id": f"teammate-{hashlib.sha1(key.encode('utf-8')).hexdigest()[:6]}",
                "name": quirky_teammate_name(focus, used_names),
                "focus": focus,
                "spawns": 1,
                "first_ts": ts,
                "last_ts": ts,
            }
    return teammates


_TOOL_VERBS = {
    "bash": "Ran",
    "read": "Read",
    "write": "Wrote",
    "edit": "Edited",
    "multiedit": "Edited",
    "strreplace": "Edited",
    "notebookedit": "Edited notebook",
    "grep": "Searched code for",
    "glob": "Looked for files matching",
    "ls": "Listed",
    "webfetch": "Fetched",
    "websearch": "Searched the web for",
    "todowrite": "Updated the plan",
}


def _humanize_shell(command: str) -> str:
    """Compress a raw shell command into a readable one-liner."""
    cmd = " ".join(command.split())
    # Drop redirection noise that dominates raw command dumps.
    cmd = re.sub(r"\s*(?:2>&1|>\s*/dev/null|2>\s*/dev/null)\s*", " ", cmd).strip()
    segments = [s.strip() for s in re.split(r"\s*(?:&&|\|\||;)\s*", cmd) if s.strip()]
    first = segments[0] if segments else cmd
    if len(first) > 100:
        first = first[:97] + "…"
    extra = len(segments) - 1
    label = f"Ran `{first}`"
    if extra > 0:
        label += f" (+{extra} more step{'s' if extra != 1 else ''})"
    return label


def _humanize_structured_output(payload: str) -> str:
    """Summarize a StructuredOutput JSON blob instead of dumping it raw."""
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        data = None
    if isinstance(data, dict):
        summary = str(data.get("summary") or data.get("status") or "").strip()
        parts = []
        if summary:
            parts.append(summary[:140])
        artifacts = data.get("changed_artifacts")
        if isinstance(artifacts, list) and artifacts:
            parts.append(f"{len(artifacts)} changed artifact"
                         + ("s" if len(artifacts) != 1 else ""))
        if parts:
            return "Reported results · " + " · ".join(parts)
        keys = ", ".join(list(data.keys())[:4])
        return f"Reported structured results ({keys})"
    return "Reported structured results"


def _humanize_activity(kind: str, detail: str) -> str:
    """Turn raw narration lines into readable activity-feed messages."""
    detail = detail.strip()
    if kind != "tool" or ": " not in detail:
        return detail
    tool, _, rest = detail.partition(": ")
    rest = rest.strip()
    low = tool.strip().lower()
    if low == "bash":
        return _humanize_shell(rest)
    if low == "structuredoutput":
        return _humanize_structured_output(rest)
    verb = _TOOL_VERBS.get(low)
    if verb:
        if len(rest) > 140:
            rest = rest[:137] + "…"
        return f"{verb} {rest}"
    return detail


def _task(tid: str, title: str, status: str, assignee: Optional[str],
          priority: str, phase: int, created: str, updated: str,
          deps: Optional[list[str]] = None,
          description: str = "") -> dict:
    return {
        "id": tid,
        "title": title,
        "status": status,
        "assignee": assignee,
        "priority": priority,
        "dependencies": deps or [],
        "phase": phase,
        "createdAt": created,
        "updatedAt": updated,
        "description": description or "",
    }


def _pipeline_status(name: str, live: bool, status: str, phase: str,
                     iteration: int, max_iter: int) -> str:
    """Map Absoloop lifecycle → Kanban column for a named pipeline task."""
    status = (status or "").upper()
    phase = (phase or "").lower()
    terminal_fail = status in ("BLOCKED", "BUDGET_EXHAUSTED", "REJECTED", "STOPPED")
    terminal_done = status == "COMPLETED"

    order = ["scaffold", "execute", "integrity", "critic", "gate", "deliver"]
    idx = order.index(name)

    # Which stage is "current"?
    if terminal_done:
        current = 5  # deliver done
    elif terminal_fail:
        current = 1 if name == "execute" else idx
    elif status == "AWAITING_APPROVAL":
        current = 4
    elif status == "FINAL_REVIEW" or "critic" in phase or "integrity" in phase:
        current = 3 if "critic" in phase else 2
    elif live and phase in ("preparing", "starting"):
        # Runner is still in its consolidated preparation block —
        # /goal work has not begun yet.
        current = 0
    elif live or status in ("EXECUTING", "READY"):
        current = 1
    else:
        current = 0 if iteration == 0 else 1

    if terminal_fail and name == "execute":
        return "failed"
    if idx < current:
        return "done"
    if idx == current:
        if name == "gate" and status == "AWAITING_APPROVAL":
            return "review"
        if name == "scaffold":
            if live and phase in ("preparing", "starting"):
                return "in_progress"
            return "done" if iteration > 0 or live or status else "in_progress"
        return "in_progress" if live or status in (
            "EXECUTING", "FINAL_REVIEW", "AWAITING_APPROVAL", "READY"
        ) else "assigned"
    if idx == current + 1:
        return "inbox"
    return "inbox"


def _awaiting_new_run(abs_dir: pathlib.Path, runtime: dict, state: dict,
                      monitor: dict, live: bool) -> bool:
    """True when a mission is scaffolded/extended but the runner has not
    produced a live heartbeat for this loop yet.

    Covers: fresh `absoloop` scaffold (runtime only), post-extend gap
    (state.json archived), and stale monitor leftover from a prior loop_id.
    """
    if not (abs_dir / "runtime.json").is_file():
        return False
    if live:
        return False
    if not (abs_dir / "state.json").is_file():
        return True
    loop_id = str(runtime.get("loop_id") or "").strip()
    monitor_loop = str(monitor.get("loop_id") or "").strip()
    if loop_id and monitor_loop and monitor_loop != loop_id:
        return True
    # State exists but run never started (READY with no iterations / no start).
    status = str(state.get("status") or "").upper()
    iteration = int(state.get("iteration") or 0)
    if status in ("", "READY") and iteration == 0 and not state.get("started_at"):
        return True
    return False


def _run_key(loop_id: str, *, awaiting: bool, started: Any = None) -> str:
    """Stable identity the Kanban UI uses to reset on a new run/project."""
    lid = (loop_id or "mission").strip() or "mission"
    if awaiting:
        return f"{lid}:pending"
    if isinstance(started, (int, float)) and started > 0:
        return f"{lid}:{int(started)}"
    return f"{lid}:active"


def build_bridge_state(project: pathlib.Path) -> dict:
    """Translate Absoloop mission artifacts into ZComb dashboard state."""
    abs_dir = project / ".absoloop"
    tmp = abs_dir / "tmp"
    monitor = _read_json(tmp / "monitor.json")
    state = _read_json(abs_dir / "state.json")
    runtime = _read_json(abs_dir / "runtime.json")
    live = monitor_is_live(monitor)

    loop_id = str(runtime.get("loop_id") or "").strip()
    monitor_loop = str(monitor.get("loop_id") or "").strip()
    # Ignore leftover telemetry from a previous loop so the board does not
    # flash the old pipeline while a new run is activating.
    if loop_id and monitor_loop and monitor_loop != loop_id:
        monitor = {}
        live = False

    awaiting = _awaiting_new_run(abs_dir, runtime, state, monitor, live)

    source = monitor if live and monitor else state
    status = str(source.get("status") or state.get("status") or "READY")
    if awaiting:
        status = "STARTING"
    phase = str(monitor.get("phase") or "")
    iteration = int(source.get("iteration") or state.get("iteration") or 0)
    max_iter = int(runtime.get("max_iterations") or 0)
    engine = str(monitor.get("engine") or runtime.get("engine")
                 or (runtime.get("builder") or {}).get("engine") or "builder")
    objective = str(runtime.get("objective") or "Absoloop mission").strip()
    objective_history = _objective_history(runtime, abs_dir)
    displayed_objective = _displayed_objective(objective_history, objective)
    mission_id = str(state.get("mission_id") or monitor.get("mission_id")
                     or runtime.get("mission_id") or loop_id or "mission")
    started = (monitor.get("started_at") if live else state.get("started_at"))
    if not isinstance(started, (int, float)) or started <= 0:
        started = time.time() if not awaiting else 0
    created = _iso(started) if started else _iso(time.time())
    updated = _iso(monitor.get("heartbeat_ts") or time.time())
    now = _iso(time.time())
    project_name = project.name or str(project)
    run_key = _run_key(loop_id or mission_id, awaiting=awaiting, started=started)

    builder_id = "builder-01"
    critic_id = "critic-01"
    activity_detail = ""
    last = monitor.get("last_activity")
    if isinstance(last, dict):
        activity_detail = str(last.get("detail") or "").strip()

    live_events = _read_live_events(tmp / "live.jsonl")
    teammates = _collect_teammates(live_events)

    agents = [
        {
            "id": builder_id,
            "name": f"Builder ({engine})",
            "role": "Repair-loop builder — iterates toward the /goal contract",
            "status": _agent_status(live, "builder", monitor, state),
            "currentTask": (
                (activity_detail[:120] or f"iteration {iteration}")
                if live and _agent_status(
                    live, "builder", monitor, state) == "active"
                else None
            ),
            "metrics": {
                "tasksCompleted": max(0, iteration - (1 if live else 0)),
                "errors": int(state.get("repeated_failure_count")
                              or monitor.get("repeated_failure_count") or 0),
            },
        },
        {
            "id": critic_id,
            "name": "Critic",
            "role": "Independent adversarial reviewer — does not take the builder's word",
            "status": _agent_status(live, "critic", monitor, state),
            "currentTask": ("reviewing acceptance evidence"
                            if _agent_status(live, "critic", monitor, state) == "active"
                            else None),
            "metrics": {
                "tasksCompleted": 1 if status in (
                    "AWAITING_APPROVAL", "COMPLETED") else 0,
                "errors": 0,
            },
        },
    ]

    # Pipeline tasks + current iteration card
    cost_usd = float(source.get("cost_usd") or 0)
    iter_label = f"{iteration}/{max_iter}" if max_iter else f"iter {iteration}"
    execute_desc = f"Engine {engine} · iteration {iter_label}"
    if live and activity_detail:
        execute_desc += f" · now: {activity_detail[:110]}"
    critic_desc = f"Independent adversarial review of iteration {iteration} evidence"
    if teammates:
        critic_desc += (f" · {len(teammates)} teammate"
                        + ("s" if len(teammates) != 1 else "") + " spawned")
    gate_desc = ("Awaiting your decision — approve or reject from Mission Controls"
                 if status == "AWAITING_APPROVAL"
                 else "Human reviews the critic-passed result before delivery")
    deliver_desc = f"Hand off accepted work for {mission_id}"
    if cost_usd:
        deliver_desc += f" · ${cost_usd:.2f} spent"

    pipe_defs = [
        # One consolidated prep card: scaffold, skills, runner sync, and the
        # /goal contract all live here rather than as separate setup noise.
        ("scaffold", "Prepare mission — scaffold · skills · /goal contract",
         builder_id, "high", 0,
         [], f"{mission_id} · {objective[:150]}"),
        ("execute", f"Execute repair iterations ({iter_label})",
         builder_id, "high", 1, ["task-scaffold"], execute_desc),
        ("integrity", "Integrity check before critic", builder_id, "medium", 2,
         ["task-execute"],
         "Builder self-audits acceptance evidence against the /goal contract"),
        ("critic", "Adversarial critic review", critic_id, "high", 3,
         ["task-integrity"], critic_desc),
        ("gate", "Human approval gate", None, "high", 4, ["task-critic"],
         gate_desc),
        ("deliver", "Deliver accepted work", builder_id, "medium", 5,
         ["task-gate"], deliver_desc),
    ]
    tasks = []
    for name, title, assignee, priority, phase_n, deps, desc in pipe_defs:
        col = _pipeline_status(name, live, status, phase, iteration, max_iter)
        tasks.append(_task(
            f"task-{name}", title, col, assignee, priority, phase_n,
            created, updated, deps, description=desc))

    # One card per completed/current iteration for kanban depth
    for i in range(1, max(iteration, 0) + 1):
        if i < iteration:
            col = "done"
        elif i == iteration and live and status in ("EXECUTING", "READY"):
            col = "in_progress"
        elif i == iteration and status == "FINAL_REVIEW":
            col = "review"
        elif i == iteration and status in ("BLOCKED", "BUDGET_EXHAUSTED", "REJECTED"):
            col = "failed"
        elif i == iteration and status in ("AWAITING_APPROVAL", "COMPLETED"):
            col = "done"
        else:
            col = "done"
        if i == iteration and live and activity_detail:
            iter_desc = f"Now: {activity_detail[:140]}"
        else:
            iter_desc = f"Repair pass {i}" \
                        + (f" of {max_iter}" if max_iter else "") \
                        + f" toward: {objective[:110]}"
        tasks.append(_task(
            f"iter-{i:04d}",
            f"Iteration {i}: advance toward objective",
            col, builder_id, "medium", 1, created, updated,
            ["task-execute"] if i == 1 else [f"iter-{i - 1:04d}"],
            description=iter_desc))

    if not (abs_dir / "runtime.json").is_file():
        # Empty project — idle placeholder so the UI isn't blank
        tasks = [
            _task("task-waiting", "Waiting for an Absoloop mission in this project",
                  "inbox", None, "low", 0, now, now,
                  description="Run `absoloop` in this project to start a mission."),
        ]
        agents = [
            {**agents[0], "status": "idle", "currentTask": None,
             "metrics": {"tasksCompleted": 0, "errors": 0}},
            {**agents[1], "status": "idle", "currentTask": None,
             "metrics": {"tasksCompleted": 0, "errors": 0}},
        ]
        awaiting = True
        run_key = _run_key("", awaiting=True)
        objective = ""
        objective_history = []
        displayed_objective = ""
        mission_id = ""
        loop_id = ""
        status = "IDLE"
    elif awaiting:
        # New / extended run activated — clear prior pipeline and wait for
        # the runner to publish live telemetry for this objective.
        wait_title = "Waiting for new Absoloop run to start"
        wait_focus = displayed_objective or objective
        wait_desc = (
            f"Project {project_name}"
            + (f" · {loop_id}" if loop_id else "")
            + (f" · {wait_focus[:140]}" if wait_focus else "")
            + " — Kanban refreshes when the runner becomes live."
        )
        tasks = [
            _task("task-waiting", wait_title, "inbox", None, "high", 0,
                  now, now, description=wait_desc),
            _task("task-objective",
                  (f"Objective: {wait_focus[:120]}" if wait_focus
                   else "Objective pending"),
                  "assigned", builder_id, "high", 0, now, now,
                  ["task-waiting"],
                  description="New mission objective loaded; waiting for "
                              "builder heartbeat."),
        ]
        agents = [
            {**agents[0], "status": "idle",
             "currentTask": "waiting for runner…",
             "metrics": {"tasksCompleted": 0, "errors": 0}},
            {**agents[1], "status": "idle", "currentTask": None,
             "metrics": {"tasksCompleted": 0, "errors": 0}},
        ]
        teammates = {}
        live_events = []

    # Spawned teammates get first-class agent cards with quirky names.
    for record in teammates.values():
        recent = live and (time.time() - record["last_ts"]) < TEAMMATE_ACTIVE_SECONDS
        agents.append({
            "id": record["id"],
            "name": record["name"],
            "role": f"Spawned teammate — {record['focus'][:140]}",
            "status": "active" if recent else "done",
            "currentTask": record["focus"][:120] if recent else None,
            "metrics": {"tasksCompleted": record["spawns"], "errors": 0},
        })

    # Activity from live.jsonl
    activity: list[dict] = []
    for event in live_events:
        agent_name = str(event.get("agent") or "builder").lower()
        agent_id = critic_id if "critic" in agent_name else builder_id
        kind = str(event.get("kind") or "say")
        detail = str(event.get("detail") or kind)
        activity_type = KIND_TO_ACTIVITY.get(kind, "status_change")
        focus = _teammate_focus(detail) if kind == "tool" else ""
        record = teammates.get(focus.lower()) if focus else None
        if record:
            agent_id = record["id"]
            activity_type = "spawned"
            message = f"{record['name']} joins the team — {record['focus']}"
        else:
            message = _humanize_activity(kind, detail)
        activity.append({
            "timestamp": _iso(event.get("ts")),
            "agentId": agent_id,
            "type": activity_type,
            "message": message[:240],
        })

    if awaiting:
        activity = [{
            "timestamp": now,
            "agentId": builder_id,
            "type": "session_start",
            "message": (
                f"New run pending"
                + (f" · {project_name}" if project_name else "")
                + (f" · {loop_id}" if loop_id else "")
                + (f": {objective[:140]}" if objective else "")
            ),
        }]
    elif not activity:
        activity.append({
            "timestamp": now,
            "agentId": builder_id,
            "type": "session_start",
            "message": f"{mission_id}: {objective[:160]}",
        })

    # Metrics / phase progress
    done_tasks = sum(1 for t in tasks if t["status"] == "done")
    failed_tasks = sum(1 for t in tasks if t["status"] == "failed")
    total = len(tasks) or 1
    completion = 100 if status == "COMPLETED" else int(100 * done_tasks / total)
    if status == "AWAITING_APPROVAL":
        completion = max(completion, 85)

    phase_progress = []
    for phase_n, name in PHASE_PIPELINE:
        matching = [t for t in tasks if t["phase"] == phase_n]
        if not matching:
            prog = 0
        else:
            prog = int(100 * sum(1 for t in matching if t["status"] == "done")
                       / len(matching))
        phase_progress.append({"phase": phase_n, "name": name, "progress": prog})

    elapsed_h = max(1e-6, (time.time() - float(started or time.time())) / 3600.0)
    tasks_per_hour = round(max(0, iteration) / elapsed_h, 1)

    if awaiting:
        completion = 0
        tasks_per_hour = 0.0
        phase_progress = [
            {"phase": phase_n, "name": name, "progress": 0}
            for phase_n, name in PHASE_PIPELINE
        ]

    return {
        "agents": {"agents": agents},
        "tasks": {"tasks": tasks},
        "metrics": {
            "completionPct": completion,
            "errorRate": round(failed_tasks / total, 3),
            "tasksPerHour": tasks_per_hour,
            "phases": phase_progress,
            "missionId": mission_id,
            "loopId": loop_id,
            "objective": objective,
            "displayedObjective": displayed_objective,
            "objectiveHistory": objective_history,
            "status": status,
            "live": live,
            "awaitingRun": awaiting,
            "runKey": run_key,
            "projectName": project_name,
        },
        "activity": activity,
        "riskAnalysis": {
            "summary": (
                (f"Awaiting new run · {project_name}"
                 + (f" · {loop_id}" if loop_id else "")
                 + (f" · {displayed_objective[:80]}"
                    if displayed_objective else ""))
                if awaiting else
                (f"Mission {mission_id} · status {status}"
                 + (f" · phase {phase}" if phase else ""))
            ),
            "iteration": 0 if awaiting else iteration,
            "maxIterations": max_iter,
            "costUsd": 0.0 if awaiting else float(source.get("cost_usd") or 0),
            "tokensTotal": 0 if awaiting else (source.get("tokens_total") or 0),
        },
    }


def sync_state(project: pathlib.Path, state_dir: Optional[pathlib.Path] = None) -> pathlib.Path:
    """Write bridged ZComb state for `project`. Returns the state directory."""
    out = state_dir or project_state_dir(project)
    out.mkdir(parents=True, exist_ok=True)
    bridged = build_bridge_state(project)
    _atomic_write(out / "agents.json", bridged["agents"])
    _atomic_write(out / "tasks.json", bridged["tasks"])
    _atomic_write(out / "metrics.json", bridged["metrics"])
    _atomic_write(out / "risk-analysis.json", bridged["riskAnalysis"])
    # activity.jsonl — rewrite from the bridged snapshot (source of truth is live.jsonl)
    activity_path = out / "activity.jsonl"
    tmp = activity_path.with_suffix(".jsonl.tmp")
    body = "\n".join(json.dumps(row, ensure_ascii=False)
                     for row in bridged["activity"])
    if body:
        body += "\n"
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(activity_path)
    return out


def ensure_dashboard_built(*, force: bool = False) -> None:
    """npm install + vite build under zcomb/monitor when needed."""
    mon = monitor_dir()
    if not mon.is_dir():
        raise FileNotFoundError(
            f"ZComb monitor not found at {mon}. Re-clone Absoloop with the zcomb/ tree.")
    if not shutil.which("node") or not shutil.which("npm"):
        raise RuntimeError(
            "Node.js 18+ (with npm) is required for absoloop --zcomb.\n"
            "  Install: https://nodejs.org  or  brew install node")
    node_modules = mon / "node_modules"
    dist_index = mon / "dist" / "index.html"
    if force or not node_modules.is_dir():
        print("  Installing ZComb dashboard dependencies…")
        subprocess.run(["npm", "install"], cwd=mon, check=True)
    if force or not dist_index.is_file():
        print("  Building ZComb dashboard…")
        subprocess.run(["npm", "run", "build"], cwd=mon, check=True)


def _port_in_use(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health",
                                    timeout=0.4) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _pids_listening_on(port: int) -> list[int]:
    """PIDs with a TCP listen socket on `port` (best-effort via lsof)."""
    try:
        out = subprocess.check_output(
            ["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return []
    pids: list[int] = []
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def stop_dashboard(port: int = DEFAULT_PORT, *, timeout: float = 5.0) -> bool:
    """Stop a ZComb dashboard listening on `port`. Returns True when free."""
    if not _port_in_use(port):
        return True
    pids = _pids_listening_on(port)
    if not pids:
        return False
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except PermissionError:
            return False
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _port_in_use(port):
            return True
        time.sleep(0.1)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    return not _port_in_use(port)


def retarget_dashboard(project: pathlib.Path, port: int = DEFAULT_PORT,
                       state_dir: Optional[pathlib.Path] = None) -> bool:
    """Ask a running ZComb server to point at a new project/state dir.

    Returns True when the live dashboard acknowledged the retarget.
    """
    out = state_dir or project_state_dir(project)
    payload = json.dumps({
        "project": str(project.resolve()),
        "stateDir": str(out.resolve()),
    }).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/retarget",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if resp.status != 200:
                return False
            body = json.loads(resp.read().decode("utf-8"))
            return bool(body.get("ok"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return False


def ensure_dashboard(project: pathlib.Path, state_dir: pathlib.Path,
                     port: int = DEFAULT_PORT) -> tuple[Optional[subprocess.Popen], str]:
    """Attach to a live dashboard or start/replace one for `project`.

    Prefer HTTP retarget when the server supports it. If the listener is an
    older build (no `/api/retarget`) or retarget fails, replace the process
    so new runs do not stay stuck on stale state.

    Returns `(proc_or_None, status)` where status is one of:
    `started`, `retargeted`, `restarted`, `failed`.
    """
    if not _port_in_use(port):
        proc = start_server(state_dir, port, project=project)
        if wait_ready(port, timeout=20):
            return proc, "started"
        return proc, "failed"

    if retarget_dashboard(project, port=port, state_dir=state_dir):
        return None, "retargeted"

    # Pre-retarget servers answer /api/health but 404 on /api/retarget.
    if not stop_dashboard(port):
        return None, "failed"
    proc = start_server(state_dir, port, project=project)
    if wait_ready(port, timeout=20):
        return proc, "restarted"
    return proc, "failed"


def start_server(state_dir: pathlib.Path, port: int,
                 project: Optional[pathlib.Path] = None) -> subprocess.Popen:
    mon = monitor_dir()
    env = os.environ.copy()
    env["ZCOMB_PORT"] = str(port)
    env["ZCOMB_STATE_DIR"] = str(state_dir.resolve())
    env["PORT"] = str(port)
    if project is not None:
        env["ZCOMB_PROJECT"] = str(project.resolve())
    env.setdefault("ABSOLOOP_HOME", str(zcomb_home().parent))
    log_path = state_dir.parent / "dashboard.log"
    state_dir.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(log_path, "a", encoding="utf-8")
    proc = subprocess.Popen(
        ["node", "server.js"],
        cwd=mon,
        env=env,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    proc._absoloop_log = log_f  # type: ignore[attr-defined]
    return proc


def wait_ready(port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_in_use(port):
            return True
        time.sleep(0.25)
    return False


def open_browser(url: str) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", url], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        elif os.name == "nt":
            os.startfile(url)  # type: ignore[attr-defined]
    except Exception:
        pass


def _bridge_loop_main(project: str, state_dir: str, interval: float) -> None:
    """Entry for the detached bridge subprocess (keeps Kanban fresh)."""
    proj = pathlib.Path(project)
    out = pathlib.Path(state_dir)
    while True:
        try:
            sync_state(proj, out)
        except Exception:
            pass
        time.sleep(max(0.5, interval))


def spawn_background(project: pathlib.Path, *, port: int = DEFAULT_PORT,
                     open_url: bool = True,
                     interval: float = 2.0) -> Optional[subprocess.Popen]:
    """Best-effort: sync, start server + bridge loop, open browser.

    Used when `absoloop … --zcomb` launches a mission — never raises into
    the mission path. Returns the dashboard Popen (or None if already up).

    When a dashboard is already listening, retarget it to this project so the
    open Kanban refreshes for the new objective/run instead of staying on
    stale state.
    """
    try:
        ensure_dashboard_built()
        # Sync first so the UI's next poll sees awaiting-run / new objective
        # immediately (before the runner has written monitor.json).
        state_dir = sync_state(project)
        proc, status = ensure_dashboard(project, state_dir, port)
        if status == "failed":
            print(f"  warning: ZComb dashboard did not become ready on :{port}",
                  file=sys.stderr)
            return proc
        if status == "retargeted":
            print(f"  ZComb UI retargeted → {project.name}")
        elif status == "restarted":
            print(f"  ZComb UI restarted → {project.name}")
        # Detached bridge keeps state files fresh while the mission runs.
        subprocess.Popen(
            [sys.executable, "-c",
             "from absoloop_harness.zcomb import _bridge_loop_main; "
             f"_bridge_loop_main({str(project)!r}, {str(state_dir)!r}, {interval!r})"],
            cwd=str(zcomb_home().parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env={**os.environ, "ABSOLOOP_HOME": str(zcomb_home().parent)},
        )
        url = f"http://localhost:{port}"
        print(f"  ZComb UI → {url}")
        if open_url:
            open_browser(url)
        return proc
    except Exception as exc:
        print(f"  warning: could not start ZComb UI ({exc})", file=sys.stderr)
        return None


def zcomb_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="absoloop zcomb",
        description=(
            "ZComb Kanban dashboard for monitoring an Absoloop mission. "
            "Requires Node.js 18+. For briefing + launch with Kanban, use "
            "'absoloop --zcomb' (same process as bare 'absoloop')."
        ),
        epilog=(
            "examples:\n"
            "  absoloop --zcomb\n"
            "  absoloop \"Make all tests pass\" --zcomb\n"
            "  absoloop zcomb -C ./my-mission --port 3141\n"
            "\n"
            "Dashboard: http://localhost:3141  ·  state: .absoloop/zcomb/state/"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-C", "--project", default=".",
                        help="project directory (default: current directory)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"dashboard port (default: {DEFAULT_PORT})")
    parser.add_argument("--no-browser", action="store_true",
                        help="do not open the browser")
    parser.add_argument("--once", action="store_true",
                        help="sync state once and exit (no server)")
    parser.add_argument("--build", action="store_true",
                        help="force npm install + vite rebuild")
    parser.add_argument("-n", "--interval", type=float, default=2.0,
                        help="bridge sync interval in seconds (default: 2)")
    args = parser.parse_args(argv)

    project = pathlib.Path(args.project).expanduser().resolve()
    if not project.is_dir():
        print(f"error: project directory not found: {project}", file=sys.stderr)
        return 1

    try:
        ensure_dashboard_built(force=args.build)
    except (RuntimeError, FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    state_dir = sync_state(project)
    print(f"  Bridged Absoloop → ZComb state at {state_dir}")

    if args.once:
        return 0

    port = args.port
    url = f"http://localhost:{port}"
    if _port_in_use(port):
        print(f"  Dashboard already running at {url}")
    else:
        print(f"  Starting ZComb dashboard on {url} …")
    proc, status = ensure_dashboard(project, state_dir, port)
    if status == "failed":
        print(f"error: dashboard failed to start (see "
              f"{state_dir.parent / 'dashboard.log'})", file=sys.stderr)
        if proc is not None and proc.poll() is None:
            proc.terminate()
        return 1
    if status == "retargeted":
        print(f"  Retargeted dashboard → {project}")
    elif status == "restarted":
        print(f"  Replaced stale dashboard → {project}")
    else:
        print(f"  ✔ Dashboard ready at {url}")

    if not args.no_browser:
        open_browser(url)

    print(f"  Syncing every {args.interval:g}s · Ctrl-C to stop")
    try:
        while True:
            sync_state(project, state_dir)
            if proc is not None and proc.poll() is not None:
                print("error: dashboard process exited", file=sys.stderr)
                return 1
            time.sleep(max(0.5, args.interval))
    except KeyboardInterrupt:
        print("\n  Stopping ZComb bridge.")
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        return 0


__all__ = [
    "extract_zcomb_flag",
    "build_bridge_state",
    "sync_state",
    "zcomb_command",
    "spawn_background",
    "retarget_dashboard",
    "ensure_dashboard",
    "stop_dashboard",
    "ensure_dashboard_built",
    "DEFAULT_PORT",
]
