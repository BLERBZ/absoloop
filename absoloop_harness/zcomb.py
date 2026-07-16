"""Optional ZComb Kanban UI for Absoloop mission monitoring.

Vendors the ZCombinator dashboard (zcomb/monitor) and bridges Absoloop
telemetry (.absoloop/tmp/monitor.json + live.jsonl + state/runtime) into
ZComb's agents/tasks/activity/metrics state files.

CLI:  absoloop --zcomb  → same briefing/launch as absoloop + Kanban UI
      absoloop zcomb [-C project] [--port N] [--no-browser]  → dashboard only
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Optional

DEFAULT_PORT = 3141
HEARTBEAT_STALE_SECONDS = 90


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


def _task(tid: str, title: str, status: str, assignee: Optional[str],
          priority: str, phase: int, created: str, updated: str,
          deps: Optional[list[str]] = None) -> dict:
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
    }


def _pipeline_status(name: str, live: bool, status: str, phase: str,
                     iteration: int, max_iter: int) -> str:
    """Map Absoloop lifecycle → Kanban column for a named pipeline task."""
    status = (status or "").upper()
    phase = (phase or "").lower()
    terminal_fail = status in ("BLOCKED", "BUDGET_EXHAUSTED", "REJECTED")
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
            return "done" if iteration > 0 or live or status else "in_progress"
        return "in_progress" if live or status in (
            "EXECUTING", "FINAL_REVIEW", "AWAITING_APPROVAL", "READY"
        ) else "assigned"
    if idx == current + 1:
        return "inbox"
    return "inbox"


def build_bridge_state(project: pathlib.Path) -> dict:
    """Translate Absoloop mission artifacts into ZComb dashboard state."""
    abs_dir = project / ".absoloop"
    tmp = abs_dir / "tmp"
    monitor = _read_json(tmp / "monitor.json")
    state = _read_json(abs_dir / "state.json")
    runtime = _read_json(abs_dir / "runtime.json")
    live = monitor_is_live(monitor)

    source = monitor if live and monitor else state
    status = str(source.get("status") or state.get("status") or "READY")
    phase = str(monitor.get("phase") or "")
    iteration = int(source.get("iteration") or state.get("iteration") or 0)
    max_iter = int(runtime.get("max_iterations") or 0)
    engine = str(monitor.get("engine") or runtime.get("engine")
                 or (runtime.get("builder") or {}).get("engine") or "builder")
    objective = str(runtime.get("objective") or "Absoloop mission").strip()
    mission_id = str(state.get("mission_id") or monitor.get("mission_id")
                     or runtime.get("loop_id") or "mission")
    started = (monitor.get("started_at") if live else state.get("started_at")) or time.time()
    created = _iso(started)
    updated = _iso(monitor.get("heartbeat_ts") or time.time())
    now = _iso(time.time())

    builder_id = "builder-01"
    critic_id = "critic-01"
    activity_detail = ""
    last = monitor.get("last_activity")
    if isinstance(last, dict):
        activity_detail = str(last.get("detail") or "").strip()

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
    pipe_defs = [
        ("scaffold", "Scaffold mission + /goal contract", builder_id, "high", 0, []),
        ("execute", f"Execute repair iterations"
                    + (f" ({iteration}/{max_iter})" if max_iter else f" (iter {iteration})"),
         builder_id, "high", 1, ["task-scaffold"]),
        ("integrity", "Integrity check before critic", builder_id, "medium", 2,
         ["task-execute"]),
        ("critic", "Adversarial critic review", critic_id, "high", 3,
         ["task-integrity"]),
        ("gate", "Human approval gate", None, "high", 4, ["task-critic"]),
        ("deliver", "Deliver accepted work", builder_id, "medium", 5, ["task-gate"]),
    ]
    tasks = []
    for name, title, assignee, priority, phase_n, deps in pipe_defs:
        col = _pipeline_status(name, live, status, phase, iteration, max_iter)
        tasks.append(_task(
            f"task-{name}", title, col, assignee, priority, phase_n,
            created, updated, deps))

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
        tasks.append(_task(
            f"iter-{i:04d}",
            f"Iteration {i}: advance toward objective",
            col, builder_id, "medium", 1, created, updated,
            ["task-execute"] if i == 1 else [f"iter-{i - 1:04d}"]))

    if not (abs_dir / "runtime.json").is_file():
        # Empty project — idle placeholder so the UI isn't blank
        tasks = [
            _task("task-waiting", "Waiting for an Absoloop mission in this project",
                  "inbox", None, "low", 0, now, now),
        ]
        agents = [
            {**agents[0], "status": "idle", "currentTask": None,
             "metrics": {"tasksCompleted": 0, "errors": 0}},
            {**agents[1], "status": "idle", "currentTask": None,
             "metrics": {"tasksCompleted": 0, "errors": 0}},
        ]

    # Activity from live.jsonl
    activity: list[dict] = []
    live_path = tmp / "live.jsonl"
    if live_path.is_file():
        try:
            lines = live_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
        for line in lines[-200:]:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            agent_name = str(event.get("agent") or "builder").lower()
            agent_id = critic_id if "critic" in agent_name else builder_id
            kind = str(event.get("kind") or "say")
            activity.append({
                "timestamp": _iso(event.get("ts")),
                "agentId": agent_id,
                "type": KIND_TO_ACTIVITY.get(kind, "status_change"),
                "message": str(event.get("detail") or kind)[:240],
            })

    if not activity:
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

    return {
        "agents": {"agents": agents},
        "tasks": {"tasks": tasks},
        "metrics": {
            "completionPct": completion,
            "errorRate": round(failed_tasks / total, 3),
            "tasksPerHour": tasks_per_hour,
            "phases": phase_progress,
            "missionId": mission_id,
            "objective": objective,
            "status": status,
            "live": live,
        },
        "activity": activity,
        "riskAnalysis": {
            "summary": (f"Mission {mission_id} · status {status}"
                        + (f" · phase {phase}" if phase else "")),
            "iteration": iteration,
            "maxIterations": max_iter,
            "costUsd": float(source.get("cost_usd") or 0),
            "tokensTotal": source.get("tokens_total") or 0,
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


def start_server(state_dir: pathlib.Path, port: int) -> subprocess.Popen:
    mon = monitor_dir()
    env = os.environ.copy()
    env["ZCOMB_PORT"] = str(port)
    env["ZCOMB_STATE_DIR"] = str(state_dir.resolve())
    env["PORT"] = str(port)
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
    """
    try:
        ensure_dashboard_built()
        state_dir = sync_state(project)
        proc: Optional[subprocess.Popen]
        if not _port_in_use(port):
            proc = start_server(state_dir, port)
            if not wait_ready(port, timeout=20):
                print(f"  warning: ZComb dashboard did not become ready on :{port}",
                      file=sys.stderr)
                return proc
        else:
            proc = None
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
    proc: Optional[subprocess.Popen] = None
    if _port_in_use(port):
        print(f"  Dashboard already running at {url}")
    else:
        print(f"  Starting ZComb dashboard on {url} …")
        proc = start_server(state_dir, port)
        if not wait_ready(port):
            print(f"error: dashboard failed to start (see "
                  f"{state_dir.parent / 'dashboard.log'})", file=sys.stderr)
            if proc and proc.poll() is None:
                proc.terminate()
            return 1
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
    "ensure_dashboard_built",
    "DEFAULT_PORT",
]
