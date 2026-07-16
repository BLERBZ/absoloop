"""Absoloop schedules — cron/interval triggers for resume / extend / start.

Definitions live under `.absoloop/schedules/<id>.toml`. A host cron (or the
built-in daemon) calls `absoloop schedule tick` to fire due jobs. The human
gate is never auto-approved.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import toml_lite
from .runtime import is_run_live, pid_alive

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover — Python < 3.9 backport unlikely
    ZoneInfo = None  # type: ignore


ACTIONS = ("resume", "extend", "start")
IF_BUSY = ("skip", "queue")
ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def schedules_dir(project: pathlib.Path) -> pathlib.Path:
    return project / ".absoloop" / "schedules"


def user_schedules_dir() -> pathlib.Path:
    return pathlib.Path.home() / ".absoloop" / "schedules"


def state_path(project: pathlib.Path) -> pathlib.Path:
    return schedules_dir(project) / "state.json"


def history_path(project: pathlib.Path) -> pathlib.Path:
    return schedules_dir(project) / "history.jsonl"


def daemon_path() -> pathlib.Path:
    return user_schedules_dir() / "daemon.json"


# ---------------------------------------------------------------------------
# Minimal 5-field cron
# ---------------------------------------------------------------------------


def _parse_field(token: str, lo: int, hi: int) -> List[int]:
    """Parse a cron field into sorted unique ints in [lo, hi]."""
    values: set[int] = set()
    for part in token.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"empty cron field part in {token!r}")
        step = 1
        if "/" in part:
            base, step_s = part.split("/", 1)
            step = int(step_s)
            if step < 1:
                raise ValueError(f"cron step must be >= 1: {part!r}")
            part = base if base else "*"
        if part == "*":
            values.update(range(lo, hi + 1, step))
            continue
        if "-" in part:
            a_s, b_s = part.split("-", 1)
            a, b = int(a_s), int(b_s)
            if a > b or a < lo or b > hi:
                raise ValueError(f"cron range out of bounds: {part!r}")
            values.update(range(a, b + 1, step))
            continue
        n = int(part)
        if n < lo or n > hi:
            raise ValueError(f"cron value out of bounds: {part!r}")
        if step != 1:
            # lone number with step is unusual; treat as that value only
            values.add(n)
        else:
            values.add(n)
    return sorted(values)


@dataclass(frozen=True)
class CronExpr:
    minute: Tuple[int, ...]
    hour: Tuple[int, ...]
    day: Tuple[int, ...]
    month: Tuple[int, ...]
    weekday: Tuple[int, ...]  # 0=Sun .. 6=Sat (also accept 7=Sun)
    raw: str

    @classmethod
    def parse(cls, expr: str) -> "CronExpr":
        parts = expr.split()
        if len(parts) != 5:
            raise ValueError(
                f"cron must have 5 fields (min hour dom mon dow), got {expr!r}")
        minute = tuple(_parse_field(parts[0], 0, 59))
        hour = tuple(_parse_field(parts[1], 0, 23))
        day = tuple(_parse_field(parts[2], 1, 31))
        month = tuple(_parse_field(parts[3], 1, 12))
        # Accept 0-7 where both 0 and 7 mean Sunday
        wd_raw = _parse_field(parts[4], 0, 7)
        weekday = tuple(sorted({0 if w == 7 else w for w in wd_raw}))
        return cls(minute, hour, day, month, weekday, expr)

    def matches(self, dt: datetime) -> bool:
        # Python: Monday=0 .. Sunday=6 → cron Sunday=0
        cron_wd = (dt.weekday() + 1) % 7
        return (
            dt.minute in self.minute
            and dt.hour in self.hour
            and dt.day in self.day
            and dt.month in self.month
            and cron_wd in self.weekday
        )


def next_cron_fire(expr: CronExpr, after: datetime, *, tz_name: str) -> datetime:
    """Return the next datetime >= after+1min that matches expr in tz."""
    tz = _zone(tz_name)
    if after.tzinfo is None:
        local = after.replace(tzinfo=tz)
    else:
        local = after.astimezone(tz)
    # Start at the next whole minute
    cursor = local.replace(second=0, microsecond=0) + timedelta(minutes=1)
    # Cap search at ~2 years of minutes
    for _ in range(366 * 24 * 60):
        if expr.matches(cursor):
            return cursor
        cursor += timedelta(minutes=1)
    raise ValueError(f"no fire time found for cron {expr.raw!r}")


def parse_every(text: str) -> int:
    """Parse duration like 30m, 6h, 1d into seconds."""
    text = text.strip().lower()
    m = re.fullmatch(r"(\d+)\s*([smhd])", text)
    if not m:
        raise ValueError(
            f"invalid --every value {text!r}; use e.g. 30m, 6h, 1d")
    n = int(m.group(1))
    unit = m.group(2)
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    seconds = n * mult
    if seconds < 60:
        raise ValueError("--every minimum is 60 seconds")
    return seconds


def _zone(name: str):
    if ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except Exception as exc:
        raise ValueError(f"unknown timezone {name!r}: {exc}") from exc


# ---------------------------------------------------------------------------
# Schedule model
# ---------------------------------------------------------------------------


@dataclass
class Schedule:
    id: str
    enabled: bool = True
    kind: str = "cron"  # cron | interval
    expr: str = ""  # cron expression
    interval_seconds: int = 0
    timezone: str = "UTC"
    action: str = "resume"
    engine: str = ""
    note: str = ""
    iterations: Optional[int] = None
    budget: Optional[float] = None
    hours: Optional[float] = None
    min_iterations: Optional[int] = None
    if_busy: str = "skip"
    require_status: List[str] = field(default_factory=list)
    project: str = "."  # relative hint only; real path is the host project

    def validate(self) -> None:
        if not ID_RE.match(self.id):
            raise ValueError(f"invalid schedule id {self.id!r}")
        if self.kind not in ("cron", "interval"):
            raise ValueError(f"kind must be cron|interval, got {self.kind!r}")
        if self.action not in ACTIONS:
            raise ValueError(f"action must be one of {ACTIONS}, got {self.action!r}")
        if self.if_busy not in IF_BUSY:
            raise ValueError(f"if_busy must be one of {IF_BUSY}")
        if self.kind == "cron":
            CronExpr.parse(self.expr)
            _zone(self.timezone)
        else:
            if self.interval_seconds < 60:
                raise ValueError("interval_seconds must be >= 60")

    def next_fire(self, after: datetime, *, last_fire: Optional[float] = None
                  ) -> datetime:
        if self.kind == "cron":
            return next_cron_fire(CronExpr.parse(self.expr), after,
                                  tz_name=self.timezone)
        # interval: from last_fire or after
        base_ts = last_fire if last_fire is not None else after.timestamp()
        nxt = datetime.fromtimestamp(base_ts + self.interval_seconds,
                                     tz=timezone.utc)
        if nxt <= after.astimezone(timezone.utc):
            nxt = after.astimezone(timezone.utc) + timedelta(
                seconds=self.interval_seconds)
        return nxt


def schedule_to_toml(s: Schedule) -> str:
    lines = [
        f'id = "{s.id}"',
        f"enabled = {'true' if s.enabled else 'false'}",
        f'kind = "{s.kind}"',
        f'timezone = "{s.timezone}"',
        f'action = "{s.action}"',
        f'if_busy = "{s.if_busy}"',
    ]
    if s.kind == "cron":
        lines.append(f'expr = "{s.expr}"')
    else:
        lines.append(f"interval_seconds = {int(s.interval_seconds)}")
    if s.engine:
        lines.append(f'engine = "{s.engine}"')
    if s.note:
        escaped = s.note.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'note = "{escaped}"')
    if s.iterations is not None:
        lines.append(f"iterations = {int(s.iterations)}")
    if s.budget is not None:
        lines.append(f"budget = {float(s.budget)}")
    if s.hours is not None:
        lines.append(f"hours = {float(s.hours)}")
    if s.min_iterations is not None:
        lines.append(f"min_iterations = {int(s.min_iterations)}")
    if s.require_status:
        arr = ", ".join(f'"{x}"' for x in s.require_status)
        lines.append(f"require_status = [{arr}]")
    return "\n".join(lines) + "\n"


def schedule_from_dict(data: Dict[str, Any], *, default_id: str = "") -> Schedule:
    sid = str(data.get("id") or default_id).strip()
    req = data.get("require_status") or []
    if not isinstance(req, list):
        raise ValueError("require_status must be an array of strings")
    s = Schedule(
        id=sid,
        enabled=bool(data.get("enabled", True)),
        kind=str(data.get("kind") or "cron"),
        expr=str(data.get("expr") or ""),
        interval_seconds=int(data.get("interval_seconds") or 0),
        timezone=str(data.get("timezone") or "UTC"),
        action=str(data.get("action") or "resume"),
        engine=str(data.get("engine") or ""),
        note=str(data.get("note") or ""),
        iterations=int(data["iterations"]) if data.get("iterations") is not None else None,
        budget=float(data["budget"]) if data.get("budget") is not None else None,
        hours=float(data["hours"]) if data.get("hours") is not None else None,
        min_iterations=(int(data["min_iterations"])
                        if data.get("min_iterations") is not None else None),
        if_busy=str(data.get("if_busy") or "skip"),
        require_status=[str(x) for x in req],
    )
    s.validate()
    return s


def load_schedule_file(path: pathlib.Path) -> Schedule:
    text = path.read_text(encoding="utf-8")
    data = toml_lite.loads(text)
    return schedule_from_dict(data, default_id=path.stem)


def list_schedules(project: pathlib.Path) -> List[Schedule]:
    root = schedules_dir(project)
    if not root.is_dir():
        return []
    out: List[Schedule] = []
    for path in sorted(root.glob("*.toml")):
        try:
            out.append(load_schedule_file(path))
        except (OSError, toml_lite.TomlError, ValueError) as exc:
            print(f"warning: skip {path.name}: {exc}", file=sys.stderr)
    return out


def save_schedule(project: pathlib.Path, s: Schedule) -> pathlib.Path:
    s.validate()
    root = schedules_dir(project)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{s.id}.toml"
    path.write_text(schedule_to_toml(s), encoding="utf-8")
    return path


def remove_schedule(project: pathlib.Path, sid: str) -> bool:
    path = schedules_dir(project) / f"{sid}.toml"
    if not path.is_file():
        return False
    path.unlink()
    return True


# ---------------------------------------------------------------------------
# State + history
# ---------------------------------------------------------------------------


def load_state(project: pathlib.Path) -> Dict[str, Any]:
    path = state_path(project)
    if not path.is_file():
        return {"schedules": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schedules": {}}
    if not isinstance(data, dict):
        return {"schedules": {}}
    data.setdefault("schedules", {})
    return data


def save_state(project: pathlib.Path, state: Dict[str, Any]) -> None:
    root = schedules_dir(project)
    root.mkdir(parents=True, exist_ok=True)
    path = state_path(project)
    body = json.dumps(state, indent=2, sort_keys=True) + "\n"
    tmp = root / f".state.{os.getpid()}.tmp"
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)


def append_history(project: pathlib.Path, event: Dict[str, Any]) -> None:
    root = schedules_dir(project)
    root.mkdir(parents=True, exist_ok=True)
    payload = {"ts": time.time(), **event}
    with history_path(project).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Busy detection
# ---------------------------------------------------------------------------


def mission_is_busy(project: pathlib.Path) -> bool:
    """True when a mission loop or harness run appears live."""
    monitor_path = project / ".absoloop" / "tmp" / "monitor.json"
    if monitor_path.is_file():
        try:
            mon = json.loads(monitor_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            mon = {}
        if isinstance(mon, dict):
            hb = mon.get("heartbeat_ts")
            pid = mon.get("pid")
            fresh = isinstance(hb, (int, float)) and time.time() - hb < 90
            if fresh and pid_alive(pid if isinstance(pid, int) else None):
                return True
            status = mon.get("status") or mon.get("phase")
            if fresh and status in ("EXECUTING", "running", "builder", "critic"):
                return True

    runs = project / ".absoloop" / "runs"
    if runs.is_dir():
        for child in runs.iterdir():
            if child.is_dir() and is_run_live(child):
                return True
    return False


def mission_status(project: pathlib.Path) -> Optional[str]:
    path = project / ".absoloop" / "state.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return str(data.get("status") or "") or None


# ---------------------------------------------------------------------------
# Fire
# ---------------------------------------------------------------------------


def _absoloop_bin() -> List[str]:
    """Return argv prefix to invoke this Absoloop CLI."""
    # Prefer the same Python + bin/absoloop that imported us
    home = os.environ.get("ABSOLOOP_HOME")
    if home:
        cli = pathlib.Path(home) / "bin" / "absoloop"
        if cli.is_file():
            return [sys.executable, str(cli)]
    # Fall back to PATH
    return ["absoloop"]


def build_fire_argv(s: Schedule, project: pathlib.Path) -> List[str]:
    base = _absoloop_bin()
    proj = str(project)
    if s.action == "resume":
        argv = base + ["resume", "-C", proj]
        if s.engine:
            argv += ["--engine", s.engine]
        return argv
    if s.action == "extend":
        argv = base + ["resume", "--extend", "-C", proj]
        if s.engine:
            argv += ["--engine", s.engine]
        if s.note:
            argv += ["-m", s.note]
        if s.iterations is not None:
            argv += ["--iterations", str(s.iterations)]
        if s.budget is not None:
            argv += ["--budget", str(s.budget)]
        if s.hours is not None:
            argv += ["--hours", str(s.hours)]
        if s.min_iterations is not None:
            argv += ["--min-iterations", str(s.min_iterations)]
        return argv
    # start — re-enter briefing-less launch via resume if possible, else error
    # `start` means: if READY/stopped, resume; if COMPLETED, extend with note
    status = mission_status(project)
    if status in (None, "COMPLETED", "BUDGET_EXHAUSTED"):
        argv = base + ["resume", "--extend", "-C", proj]
        if s.note:
            argv += ["-m", s.note or "scheduled start"]
        if s.engine:
            argv += ["--engine", s.engine]
        if s.iterations is not None:
            argv += ["--iterations", str(s.iterations)]
        if s.budget is not None:
            argv += ["--budget", str(s.budget)]
        if s.hours is not None:
            argv += ["--hours", str(s.hours)]
        return argv
    argv = base + ["resume", "-C", proj]
    if s.engine:
        argv += ["--engine", s.engine]
    return argv


def fire_schedule(s: Schedule, project: pathlib.Path, *, dry_run: bool = False
                  ) -> Tuple[str, int]:
    """Attempt to fire a schedule. Returns (result, exit_code).

    result is one of: fired, skipped_busy, skipped_status, skipped_gate,
    dry_run, error.
    """
    status = mission_status(project)
    if status == "AWAITING_APPROVAL":
        append_history(project, {
            "type": "skip", "schedule_id": s.id, "reason": "awaiting_approval",
            "status": status,
        })
        return "skipped_gate", 3

    if s.require_status and status not in s.require_status:
        append_history(project, {
            "type": "skip", "schedule_id": s.id, "reason": "status_mismatch",
            "status": status, "require_status": s.require_status,
        })
        return "skipped_status", 0

    busy = mission_is_busy(project)
    if busy:
        if s.if_busy == "skip":
            append_history(project, {
                "type": "skip", "schedule_id": s.id, "reason": "busy",
            })
            return "skipped_busy", 0
        # queue: record intent; tick will retry next time (no separate queue yet)
        append_history(project, {
            "type": "queued", "schedule_id": s.id, "reason": "busy",
        })
        return "skipped_busy", 0

    argv = build_fire_argv(s, project)
    if dry_run:
        append_history(project, {
            "type": "dry_run", "schedule_id": s.id, "argv": argv,
        })
        return "dry_run", 0

    try:
        proc = subprocess.run(argv, cwd=str(project), check=False)
        code = int(proc.returncode)
    except OSError as exc:
        append_history(project, {
            "type": "error", "schedule_id": s.id, "error": str(exc),
        })
        return "error", 1

    st = load_state(project)
    entry = st.setdefault("schedules", {}).setdefault(s.id, {})
    entry["last_fire_at"] = time.time()
    entry["last_result"] = "fired"
    entry["last_exit_code"] = code
    save_state(project, st)
    append_history(project, {
        "type": "fire", "schedule_id": s.id, "argv": argv, "exit_code": code,
    })
    return "fired", code


def due_schedules(project: pathlib.Path, *, now: Optional[datetime] = None
                  ) -> List[Tuple[Schedule, datetime]]:
    """Return enabled schedules that are due to fire at `now`."""
    now = now or datetime.now(timezone.utc)
    st = load_state(project)
    due: List[Tuple[Schedule, datetime]] = []
    for s in list_schedules(project):
        if not s.enabled:
            continue
        entry = st.get("schedules", {}).get(s.id, {})
        last = entry.get("last_fire_at")
        last_f = float(last) if isinstance(last, (int, float)) else None

        if s.kind == "cron":
            # Due if the current minute matches and we haven't fired this minute
            tz = _zone(s.timezone)
            local = now.astimezone(tz).replace(second=0, microsecond=0)
            if not CronExpr.parse(s.expr).matches(local):
                continue
            if last_f is not None:
                last_local = datetime.fromtimestamp(last_f, tz=tz).replace(
                    second=0, microsecond=0)
                if last_local == local:
                    continue
            due.append((s, local))
        else:
            # interval
            if last_f is None:
                # First interval fire: wait a full interval from "now" unless
                # next_fire_at was pre-seeded
                nxt = entry.get("next_fire_at")
                if isinstance(nxt, (int, float)) and now.timestamp() >= nxt:
                    due.append((s, now))
                elif nxt is None:
                    # Seed next_fire without firing immediately
                    entry["next_fire_at"] = now.timestamp() + s.interval_seconds
                    st.setdefault("schedules", {})[s.id] = entry
                    save_state(project, st)
                continue
            if now.timestamp() - last_f >= s.interval_seconds:
                due.append((s, now))
    return due


def tick_project(project: pathlib.Path, *, once: bool = True,
                 dry_run: bool = False, now: Optional[datetime] = None
                 ) -> int:
    """Fire all due schedules. Returns worst exit code (0 if nothing due)."""
    due = due_schedules(project, now=now)
    if not due:
        return 0
    worst = 0
    for s, _when in due:
        result, code = fire_schedule(s, project, dry_run=dry_run)
        print(f"schedule {s.id}: {result}"
              + (f" (exit {code})" if result == "fired" else ""))
        if code and code > worst:
            worst = code
        # Update next_fire hint
        st = load_state(project)
        entry = st.setdefault("schedules", {}).setdefault(s.id, {})
        try:
            nxt = s.next_fire(datetime.now(timezone.utc),
                              last_fire=entry.get("last_fire_at"))
            entry["next_fire_at"] = nxt.timestamp()
        except ValueError:
            pass
        save_state(project, st)
    return worst


# ---------------------------------------------------------------------------
# Daemon
# ---------------------------------------------------------------------------


def daemon_status() -> Dict[str, Any]:
    path = daemon_path()
    if not path.is_file():
        return {"running": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"running": False}
    pid = data.get("pid")
    alive = pid_alive(pid if isinstance(pid, int) else None)
    data["running"] = bool(alive)
    return data


def daemon_stop() -> int:
    info = daemon_status()
    if not info.get("running"):
        print("schedule daemon is not running")
        if daemon_path().is_file():
            daemon_path().unlink()
        return 0
    pid = info.get("pid")
    try:
        os.kill(int(pid), signal.SIGTERM)
    except (OSError, TypeError, ValueError) as exc:
        print(f"error: could not stop daemon pid {pid}: {exc}", file=sys.stderr)
        return 1
    # Wait briefly
    for _ in range(20):
        if not pid_alive(int(pid)):
            break
        time.sleep(0.1)
    if daemon_path().is_file():
        daemon_path().unlink()
    print(f"stopped schedule daemon (pid {pid})")
    return 0


def _discover_projects() -> List[pathlib.Path]:
    """Projects registered in ~/.absoloop/schedules/index.json plus cwd."""
    projects: List[pathlib.Path] = []
    index = user_schedules_dir() / "index.json"
    if index.is_file():
        try:
            data = json.loads(index.read_text(encoding="utf-8"))
            for item in data.get("projects", []):
                p = pathlib.Path(str(item)).expanduser().resolve()
                if (p / ".absoloop" / "schedules").is_dir():
                    projects.append(p)
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    cwd = pathlib.Path.cwd().resolve()
    if (cwd / ".absoloop" / "schedules").is_dir() and cwd not in projects:
        projects.append(cwd)
    return projects


def register_project(project: pathlib.Path) -> None:
    """Best-effort: record project in ~/.absoloop/schedules/index.json for the daemon."""
    try:
        root = user_schedules_dir()
        root.mkdir(parents=True, exist_ok=True)
        index = root / "index.json"
        data: Dict[str, Any] = {"projects": []}
        if index.is_file():
            try:
                data = json.loads(index.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {"projects": []}
        projects = [str(pathlib.Path(p).expanduser().resolve())
                    for p in data.get("projects", [])]
        key = str(project.resolve())
        if key not in projects:
            projects.append(key)
        data["projects"] = projects
        index.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError:
        # Sandboxed / read-only home — project-local schedules still work.
        return


def daemon_start(*, interval: int = 60, foreground: bool = False) -> int:
    info = daemon_status()
    if info.get("running"):
        print(f"schedule daemon already running (pid {info.get('pid')})")
        return 0

    if not foreground and os.name != "nt":
        # Double-fork style detach
        if os.fork() > 0:
            return 0
        os.setsid()
        if os.fork() > 0:
            os._exit(0)
        # Child continues as daemon
        sys.stdout = open(os.devnull, "w")
        sys.stderr = open(os.devnull, "w")

    root = user_schedules_dir()
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": os.getpid(),
        "started_at": time.time(),
        "interval": interval,
        "heartbeat": time.time(),
    }
    daemon_path().write_text(json.dumps(payload, indent=2) + "\n",
                             encoding="utf-8")
    if foreground:
        print(f"schedule daemon running in foreground (pid {os.getpid()}, "
              f"tick every {interval}s)")

    try:
        while True:
            payload["heartbeat"] = time.time()
            daemon_path().write_text(json.dumps(payload, indent=2) + "\n",
                                     encoding="utf-8")
            for project in _discover_projects():
                try:
                    tick_project(project, once=True, dry_run=False)
                except Exception:
                    append_history(project, {
                        "type": "error", "schedule_id": "*",
                        "error": "tick failed",
                    })
            time.sleep(max(15, interval))
    except KeyboardInterrupt:
        if daemon_path().is_file():
            daemon_path().unlink()
        return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def schedule_command(argv: Sequence[str], *, cwd: Optional[pathlib.Path] = None
                     ) -> int:
    cwd = (cwd or pathlib.Path.cwd()).resolve()
    parser = argparse.ArgumentParser(
        prog="absoloop schedule",
        description="Schedule Absoloop resume/extend/start — never auto-approves")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="add or replace a schedule")
    p_add.add_argument("--id", required=True, help="schedule id")
    p_add.add_argument("--cron", default="", help='5-field cron, e.g. "0 0 * * 5"')
    p_add.add_argument("--every", default="", help="interval, e.g. 6h / 1d")
    p_add.add_argument("--tz", default="UTC", dest="tz",
                       help="IANA timezone (default UTC)")
    p_add.add_argument("--action", choices=ACTIONS, default="resume")
    p_add.add_argument("-m", "--note", default="",
                       help="extend/start focus note")
    p_add.add_argument("--engine", choices=["claude", "codex", "grok"], default="")
    p_add.add_argument("--iterations", type=int)
    p_add.add_argument("--budget", type=float)
    p_add.add_argument("--hours", type=float)
    p_add.add_argument("--min-iterations", type=int, dest="min_iterations")
    p_add.add_argument("--if-busy", choices=IF_BUSY, default="skip",
                       dest="if_busy")
    p_add.add_argument("--require-status", default="",
                       help="comma-separated statuses that allow firing")
    p_add.add_argument("-C", "--project", default=".")
    p_add.add_argument("--disabled", action="store_true")

    p_list = sub.add_parser("list", help="list schedules")
    p_list.add_argument("-C", "--project", default=".")

    p_show = sub.add_parser("show", help="show one schedule")
    p_show.add_argument("id")
    p_show.add_argument("-C", "--project", default=".")

    p_en = sub.add_parser("enable", help="enable a schedule")
    p_en.add_argument("id")
    p_en.add_argument("-C", "--project", default=".")

    p_dis = sub.add_parser("disable", help="disable a schedule")
    p_dis.add_argument("id")
    p_dis.add_argument("-C", "--project", default=".")

    p_rm = sub.add_parser("rm", help="remove a schedule")
    p_rm.add_argument("id")
    p_rm.add_argument("-C", "--project", default=".")

    p_tick = sub.add_parser("tick", help="fire due schedules (for cron/daemon)")
    p_tick.add_argument("--once", action="store_true", default=True)
    p_tick.add_argument("--dry-run", action="store_true")
    p_tick.add_argument("-C", "--project", default=".")

    p_hist = sub.add_parser("history", help="show recent schedule events")
    p_hist.add_argument("id", nargs="?", default="")
    p_hist.add_argument("-n", type=int, default=20)
    p_hist.add_argument("-C", "--project", default=".")

    p_daemon = sub.add_parser("daemon", help="long-lived tick loop")
    dsub = p_daemon.add_subparsers(dest="daemon_cmd", required=True)
    p_ds = dsub.add_parser("start", help="start daemon")
    p_ds.add_argument("--interval", type=int, default=60,
                      help="seconds between ticks (default 60)")
    p_ds.add_argument("--foreground", "-f", action="store_true")
    dsub.add_parser("stop", help="stop daemon")
    dsub.add_parser("status", help="daemon status")

    args = parser.parse_args(list(argv))

    def project_of(ns) -> pathlib.Path:
        return pathlib.Path(getattr(ns, "project", ".")).expanduser().resolve()

    if args.cmd == "add":
        project = project_of(args)
        if bool(args.cron) == bool(args.every):
            print("error: provide exactly one of --cron or --every",
                  file=sys.stderr)
            return 2
        req = [x.strip() for x in args.require_status.split(",") if x.strip()]
        if args.cron:
            s = Schedule(
                id=args.id, enabled=not args.disabled, kind="cron",
                expr=args.cron, timezone=args.tz, action=args.action,
                engine=args.engine or "", note=args.note,
                iterations=args.iterations, budget=args.budget,
                hours=args.hours, min_iterations=args.min_iterations,
                if_busy=args.if_busy, require_status=req,
            )
        else:
            s = Schedule(
                id=args.id, enabled=not args.disabled, kind="interval",
                interval_seconds=parse_every(args.every),
                timezone=args.tz, action=args.action,
                engine=args.engine or "", note=args.note,
                iterations=args.iterations, budget=args.budget,
                hours=args.hours, min_iterations=args.min_iterations,
                if_busy=args.if_busy, require_status=req,
            )
        try:
            path = save_schedule(project, s)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        register_project(project)
        try:
            print(f"wrote {path.relative_to(project)}")
        except ValueError:
            print(f"wrote {path}")
        return 0

    if args.cmd == "list":
        project = project_of(args)
        rows = list_schedules(project)
        if not rows:
            print("(no schedules)")
            return 0
        st = load_state(project)
        for s in rows:
            entry = st.get("schedules", {}).get(s.id, {})
            when = (f"cron {s.expr} ({s.timezone})" if s.kind == "cron"
                    else f"every {s.interval_seconds}s")
            flag = "on " if s.enabled else "off"
            nxt = entry.get("next_fire_at")
            nxt_s = ""
            if isinstance(nxt, (int, float)):
                nxt_s = f"  next={datetime.fromtimestamp(nxt, tz=timezone.utc).isoformat()}"
            print(f"{flag}  {s.id:24}  {s.action:7}  {when}{nxt_s}")
        return 0

    if args.cmd == "show":
        project = project_of(args)
        path = schedules_dir(project) / f"{args.id}.toml"
        if not path.is_file():
            print(f"error: no schedule {args.id!r}", file=sys.stderr)
            return 1
        print(path.read_text(encoding="utf-8"), end="")
        return 0

    if args.cmd in ("enable", "disable"):
        project = project_of(args)
        path = schedules_dir(project) / f"{args.id}.toml"
        if not path.is_file():
            print(f"error: no schedule {args.id!r}", file=sys.stderr)
            return 1
        try:
            s = load_schedule_file(path)
        except (toml_lite.TomlError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        s.enabled = args.cmd == "enable"
        save_schedule(project, s)
        print(f"{args.cmd}d {s.id}")
        return 0

    if args.cmd == "rm":
        project = project_of(args)
        if not remove_schedule(project, args.id):
            print(f"error: no schedule {args.id!r}", file=sys.stderr)
            return 1
        print(f"removed {args.id}")
        return 0

    if args.cmd == "tick":
        project = project_of(args)
        register_project(project)
        return tick_project(project, once=True, dry_run=args.dry_run)

    if args.cmd == "history":
        project = project_of(args)
        path = history_path(project)
        if not path.is_file():
            print("(no history)")
            return 0
        lines = path.read_text(encoding="utf-8").splitlines()
        rows = []
        for line in lines:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if args.id and ev.get("schedule_id") != args.id:
                continue
            rows.append(ev)
        for ev in rows[-args.n:]:
            ts = datetime.fromtimestamp(float(ev.get("ts", 0)),
                                        tz=timezone.utc).isoformat()
            print(f"{ts}  {ev.get('type')}  {ev.get('schedule_id')}  "
                  f"{ev.get('reason', ev.get('exit_code', ''))}")
        return 0

    if args.cmd == "daemon":
        if args.daemon_cmd == "start":
            return daemon_start(interval=args.interval,
                                foreground=args.foreground)
        if args.daemon_cmd == "stop":
            return daemon_stop()
        if args.daemon_cmd == "status":
            info = daemon_status()
            if info.get("running"):
                print(f"running  pid={info.get('pid')}  "
                      f"interval={info.get('interval')}s")
            else:
                print("stopped")
            return 0

    return 2
