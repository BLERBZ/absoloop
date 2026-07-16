"""Absoloop shortcuts — keyboard chords + CLI actions, Codex Micro ready.

The Work Louder Codex Micro is an HID keyboard (13 keys, dial, joystick).
Keymaps are stored on the device via the Input app / Codex remapping, so
Absoloop does not talk to the hardware — it exposes a stable action catalog
and chord bindings the Micro (or any keyboard) can fire.

Two equal entry points for every action:
  1. Chord  — Micro key / keyboard hotspot → `absoloop shortcuts listen`
  2. Command — `absoloop do <action>` / `absoloop shortcuts run <action>`
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import toml_lite
from .briefing import tint

# ---------------------------------------------------------------------------
# Action catalog — every Absoloop workflow the Micro (or CLI) can trigger
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Action:
    name: str
    summary: str
    argv: Tuple[str, ...]              # args after `absoloop`
    group: str = "mission"             # mission | gate | harness | system
    needs_prompt: bool = False         # ask for trailing text (reject, run…)
    prompt_label: str = ""
    micro_slot: str = ""               # suggested Codex Micro keycap role
    dangerous: bool = False            # confirm before run unless --yes


# Default chords prefer F13–F24 and rare modifiers so typing is never stolen.
# Codex Micro / Input users map physical keys → these HID codes.
DEFAULT_BINDINGS: Dict[str, str] = {
    # Agent-status cluster (left of Micro)
    "status":   "f13",
    "watch":    "f14",
    "report":   "f15",
    "goal":     "f16",
    # Command cluster (accept / reject / continue)
    "approve":  "f17",
    "reject":   "f18",
    "resume":   "f19",
    "extend":   "ctrl+shift+alt+e",
    # Mission control
    "brief":    "f20",
    "cancel":   "f21",
    "doctor":   "f22",
    "inspect":  "f23",
    # Harness
    "run":      "f24",
    "providers": "ctrl+shift+alt+p",
    "build":    "ctrl+shift+alt+b",
    # Dial-inspired thinking / layer helpers (document for Input layers)
    "layer-mission": "ctrl+shift+alt+1",
    "layer-harness": "ctrl+shift+alt+2",
}

ACTIONS: Dict[str, Action] = {
    "status": Action(
        "status", "Mission at a glance + next command",
        ("status",), group="mission", micro_slot="status"),
    "watch": Action(
        "watch", "Live dashboard (phase, budgets, activity)",
        ("watch",), group="mission", micro_slot="thinking"),
    "report": Action(
        "report", "Open the mission report (Markdown + lite viewer)",
        ("report",), group="mission", micro_slot="complete"),
    "goal": Action(
        "goal", "Show the /goal contract",
        ("goal",), group="mission", micro_slot="goal"),
    "approve": Action(
        "approve", "Accept mission at the human gate + deliver",
        ("approve",), group="gate", micro_slot="accept", dangerous=True),
    "reject": Action(
        "reject", "Send feedback and keep looping",
        ("reject",), group="gate", micro_slot="reject",
        needs_prompt=True, prompt_label="rejection feedback"),
    "resume": Action(
        "resume", "Re-enter the active mission loop",
        ("resume",), group="mission", micro_slot="continue"),
    "extend": Action(
        "extend", "Follow-on run for a COMPLETED mission",
        ("resume", "--extend"), group="mission", micro_slot="extend"),
    "schedule-tick": Action(
        "schedule-tick", "Fire due Absoloop schedules once",
        ("schedule", "tick", "--once"), group="system", micro_slot=""),
    "schedule-list": Action(
        "schedule-list", "List project schedules",
        ("schedule", "list"), group="system", micro_slot=""),
    "brief": Action(
        "brief", "Open Mission Briefing in the current directory",
        (".",), group="mission", micro_slot="new",
        needs_prompt=True, prompt_label="mission objective (optional)"),
    "cancel": Action(
        "cancel", "Cancel a live harness run (prompts for run-id if needed)",
        ("cancel",), group="harness", micro_slot="error",
        needs_prompt=True, prompt_label="run-id (blank = newest live)",
        dangerous=True),
    "setup": Action(
        "setup", "First-run setup wizard (PATH · providers · defaults)",
        ("setup",), group="system", micro_slot=""),
    "doctor": Action(
        "doctor", "Provider health, auth, actionable fixes",
        ("doctor",), group="system", micro_slot="doctor"),
    "providers": Action(
        "providers", "Capability matrix for grok / claude / codex",
        ("providers",), group="harness", micro_slot="agents"),
    "inspect": Action(
        "inspect", "Inspect harness runs (blank = list)",
        ("inspect",), group="harness", micro_slot="inspect",
        needs_prompt=True, prompt_label="run-id (optional)"),
    "run": Action(
        "run", "Harness single-provider run",
        ("run",), group="harness", micro_slot="run",
        needs_prompt=True, prompt_label="task prompt"),
    "build": Action(
        "build", "Harness race/council build",
        ("build", "--strategy", "race"), group="harness", micro_slot="build",
        needs_prompt=True, prompt_label="task prompt"),
    "layer-mission": Action(
        "layer-mission", "Print mission-layer Micro cheat sheet",
        ("shortcuts", "layout", "--layer", "mission"), group="system",
        micro_slot="layer"),
    "layer-harness": Action(
        "layer-harness", "Print harness-layer Micro cheat sheet",
        ("shortcuts", "layout", "--layer", "harness"), group="system",
        micro_slot="layer"),
}


# ---------------------------------------------------------------------------
# Chord parsing
# ---------------------------------------------------------------------------

_MODS = ("ctrl", "control", "cmd", "command", "meta", "alt", "option",
         "shift", "super")


def normalize_chord(chord: str) -> str:
    """Canonical form: ctrl+shift+alt+key (sorted mods, lowercased)."""
    parts = [p.strip().lower() for p in re.split(r"[+|]", chord) if p.strip()]
    if not parts:
        raise ValueError("empty chord")
    key = parts[-1]
    mods = []
    for part in parts[:-1]:
        if part in ("control", "ctrl"):
            mods.append("ctrl")
        elif part in ("cmd", "command", "meta", "super"):
            mods.append("cmd")
        elif part in ("alt", "option"):
            mods.append("alt")
        elif part == "shift":
            mods.append("shift")
        else:
            raise ValueError(f"unknown modifier {part!r} in chord {chord!r}")
    # stable order for matching
    order = ["ctrl", "cmd", "alt", "shift"]
    mods = [m for m in order if m in mods]
    # aliases
    if key == "return":
        key = "enter"
    if key == "esc":
        key = "escape"
    return "+".join(mods + [key]) if mods else key


def parse_chord(chord: str) -> Tuple[frozenset, str]:
    norm = normalize_chord(chord)
    parts = norm.split("+")
    key = parts[-1]
    mods = frozenset(parts[:-1])
    return mods, key


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

USER_SHORTCUTS = pathlib.Path(os.environ.get(
    "ABSOLOOP_USER_CONFIG",
    str(pathlib.Path.home() / ".absoloop" / "absoloop.toml")))


@dataclass
class ShortcutConfig:
    bindings: Dict[str, str] = field(default_factory=dict)   # action -> chord
    enabled: bool = True
    listen_confirm_dangerous: bool = True

    def chord_for(self, action: str) -> str:
        return self.bindings.get(action, DEFAULT_BINDINGS.get(action, ""))

    def action_for_chord(self, chord: str) -> Optional[str]:
        want = normalize_chord(chord)
        for action, bound in self.bindings.items():
            if not bound:
                continue  # explicitly unbound
            if action in ACTIONS and normalize_chord(bound) == want:
                return action
        return None


def load_shortcuts(project_root: pathlib.Path) -> ShortcutConfig:
    merged = dict(DEFAULT_BINDINGS)
    enabled = True
    confirm = True
    for path in (USER_SHORTCUTS, project_root / "absoloop.toml"):
        if not path.is_file():
            continue
        try:
            doc = toml_lite.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        section = doc.get("shortcuts") or {}
        if not isinstance(section, dict):
            continue
        if "enabled" in section:
            enabled = bool(section["enabled"])
        if "confirm_dangerous" in section:
            confirm = bool(section["confirm_dangerous"])
        binds = section.get("bindings") or section
        if isinstance(binds, dict):
            for key, value in binds.items():
                if key in ("enabled", "confirm_dangerous", "bindings"):
                    continue
                if key in ACTIONS and isinstance(value, str):
                    merged[key] = value
    # Apply explicit empties from project last — already in merged via loops
    return ShortcutConfig(bindings=merged, enabled=enabled,
                          listen_confirm_dangerous=confirm)


def save_user_binding(action: str, chord: str) -> pathlib.Path:
    """Persist one binding into ~/.absoloop/absoloop.toml [shortcuts]."""
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    chord = normalize_chord(chord)
    path = USER_SHORTCUTS
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: Dict[str, Any] = {}
    if path.is_file():
        try:
            existing = toml_lite.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    shortcuts = dict(existing.get("shortcuts") or {})
    shortcuts[action] = chord
    existing["shortcuts"] = shortcuts
    path.write_text(_dump_toml(existing), encoding="utf-8")
    return path


def _dump_toml(doc: Dict[str, Any]) -> str:
    """Minimal writer for the tables we touch (stdlib, no tomli-w)."""
    lines: List[str] = []
    for key, value in doc.items():
        if isinstance(value, dict):
            lines.append(f"[{key}]")
            for sub, subval in value.items():
                if isinstance(subval, dict):
                    lines.append(f"[{key}.{sub}]")
                    for k3, v3 in subval.items():
                        lines.append(f"{k3} = {_toml_lit(v3)}")
                else:
                    lines.append(f"{sub} = {_toml_lit(subval)}")
            lines.append("")
        else:
            lines.append(f"{key} = {_toml_lit(value)}")
    return "\n".join(lines).rstrip() + "\n"


def _toml_lit(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_lit(v) for v in value) + "]"
    return json.dumps(str(value))


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def absoloop_bin() -> List[str]:
    """How to re-invoke Absoloop from a shortcut (same interpreter + script)."""
    from .platform_util import tooling_home
    # Prefer the running entry point when we were launched as bin/absoloop.
    argv0 = pathlib.Path(sys.argv[0]).resolve()
    if argv0.name in ("absoloop", "absoloop.cmd") and argv0.is_file():
        if argv0.suffix.lower() == ".cmd":
            script = argv0.with_suffix("")
            if script.is_file():
                return [sys.executable, str(script)]
        try:
            head = argv0.read_bytes()[:40]
        except OSError:
            head = b""
        if head.startswith(b"#!") or argv0.suffix == "":
            return [sys.executable, str(argv0)]
    which = shutil.which("absoloop")
    if which:
        path = pathlib.Path(which)
        # On Windows, which may return absoloop.CMD — invoke via python + script.
        if path.suffix.lower() in (".cmd", ".bat"):
            script = path.with_suffix("")
            if script.is_file():
                return [sys.executable, str(script)]
        return [which]
    home = tooling_home()
    candidate = home / "bin" / "absoloop"
    if candidate.is_file():
        return [sys.executable, str(candidate)]
    return [sys.executable, "-m", "absoloop_harness.cli"]  # fallback


def run_action(action_name: str, *, cwd: pathlib.Path,
               extra: Sequence[str] = (), yes: bool = False,
               prompt_text: Optional[str] = None) -> int:
    action = ACTIONS.get(action_name)
    if action is None:
        print(f"error: unknown action {action_name!r}", file=sys.stderr)
        print(f"known: {', '.join(sorted(ACTIONS))}", file=sys.stderr)
        return 2

    cfg = load_shortcuts(cwd)
    trailing: List[str] = list(extra)
    text = prompt_text

    if action.needs_prompt and text is None and not trailing:
        if action.name == "cancel" and not trailing:
            text = _default_cancel_run_id(cwd) or ""
            if not text and sys.stdin.isatty():
                text = _ask(action.prompt_label)
        elif action.name == "brief":
            # bare briefing in cwd — no objective required
            text = ""
        elif action.name in ("inspect",) and not trailing:
            text = ""
        elif sys.stdin.isatty():
            text = _ask(action.prompt_label or "input")
        else:
            print(f"error: action {action.name!r} needs: {action.prompt_label}",
                  file=sys.stderr)
            return 2

    if action.dangerous and not yes and cfg.listen_confirm_dangerous:
        if sys.stdin.isatty():
            answer = _ask(f"run dangerous action {action.name!r}? [y/N]")
            if answer.lower() not in ("y", "yes"):
                print(tint("dim", "  skipped."))
                return 1
        else:
            print(f"error: {action.name} is dangerous — pass --yes",
                  file=sys.stderr)
            return 2

    argv = list(action.argv)
    if action.name == "reject" and text:
        argv = ["reject", text]
    elif action.name == "brief":
        # With text: adopt cwd + objective. Without: full interactive briefing.
        argv = [".", "-o", text] if text else []
    elif action.name == "cancel":
        run_id = (trailing[0] if trailing else text) or _default_cancel_run_id(cwd)
        if not run_id:
            print("error: no live harness run to cancel", file=sys.stderr)
            return 2
        argv = ["cancel", run_id]
    elif action.name == "inspect":
        argv = ["inspect"] + ([text] if text else list(trailing))
    elif action.name == "run":
        if text:
            argv = ["run", text, "-y"]
        elif trailing:
            argv = ["run", *trailing, "-y"]
        else:
            argv = ["run"]
    elif action.name == "build":
        task = text or (trailing[0] if trailing else "")
        argv = ["build", task, "-y"] if task else ["build"]
    elif trailing:
        argv = list(action.argv) + list(trailing)

    cmd = absoloop_bin() + argv
    print(tint("dim", "  $ " + " ".join(shlex.quote(c) for c in cmd)))
    return subprocess.run(cmd, cwd=str(cwd)).returncode


def _default_cancel_run_id(cwd: pathlib.Path) -> str:
    from . import runtime as run_ctrl
    from .workspace import list_runs, RunStore
    for run_id in list_runs(cwd):
        if run_ctrl.is_run_live(RunStore(cwd, run_id).run_dir):
            return run_id
    return ""


def _ask(label: str) -> str:
    try:
        return input(f"  {label}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


# ---------------------------------------------------------------------------
# Listen (terminal + line protocol for Micro / automation)
# ---------------------------------------------------------------------------

# CSI sequences for common function keys (xterm / macOS Terminal / iTerm /
# Windows Terminal). F13–F24 match Codex Micro default bindings.
_FUNC_KEY_CSI = {
    "1": "home", "2": "insert", "3": "delete", "4": "end",
    "5": "pageup", "6": "pagedown",
    "11": "f1", "12": "f2", "13": "f3", "14": "f4", "15": "f5",
    "17": "f6", "18": "f7", "19": "f8", "20": "f9", "21": "f10",
    "23": "f11", "24": "f12",
    "25": "f13", "26": "f14", "28": "f15", "29": "f16",
    "31": "f17", "32": "f18", "33": "f19", "34": "f20",
    "42": "f21", "43": "f22", "44": "f23", "45": "f24",
}


def listen(cwd: pathlib.Path, *, once: bool = False) -> int:
    """Listen for chords. Two modes:

    - TTY raw (Unix): function keys F13–F24 / ctrl+letter (best-effort)
    - Line protocol (all platforms / Micro shell macros / pipes):
        action:<name>
        chord:<chord>
        <name>                  # bare action name

    On Windows, TTY raw listen is unavailable — use `absoloop do <action>`
    (recommended for Codex Micro) or pipe the line protocol into listen.
    """
    from .platform_util import is_windows, tty_raw_listen_supported

    cfg = load_shortcuts(cwd)
    if not cfg.enabled:
        print("shortcuts disabled in config", file=sys.stderr)
        return 1
    print(tint("bold", "∞ Absoloop shortcuts listen"))
    print(tint("dim", "  chords · action:<name> · chord:f13 · q to quit"))
    print(tint("dim", "  Codex Micro: prefer `absoloop do <action>` shell macros"))
    print()
    _print_micro_compact(cfg, layer="mission")

    if not sys.stdin.isatty():
        return _listen_lines(cwd, cfg, once=once)

    if not tty_raw_listen_supported():
        print(tint("warn", "  TTY chord listen needs a Unix terminal (termios)."))
        if is_windows():
            print(tint("dim", "  Windows / Codex Micro: map keys to shell macros:"))
            print(tint("dim", "    absoloop do status"))
            print(tint("dim", "    absoloop do approve --yes"))
            print(tint("dim", "  Or pipe:  echo action:status | absoloop shortcuts listen"))
        print(tint("dim", "  Waiting on stdin (line protocol) — Ctrl+Z Enter to end on Windows."))
        print()
        return _listen_lines(cwd, cfg, once=once)

    return _listen_tty(cwd, cfg, once=once)


def _dispatch_chord_or_action(cwd: pathlib.Path, cfg: ShortcutConfig,
                              token: str) -> int:
    token = token.strip()
    if not token:
        return 0
    if token.startswith("action:"):
        return run_action(token.split(":", 1)[1].strip(), cwd=cwd)
    if token.startswith("chord:"):
        action = cfg.action_for_chord(token.split(":", 1)[1].strip())
        if not action:
            print(tint("warn", f"  no action bound to that chord"), file=sys.stderr)
            return 1
        print(tint("ok", f"  ∞ {action}"))
        return run_action(action, cwd=cwd)
    if token in ACTIONS:
        print(tint("ok", f"  ∞ {token}"))
        return run_action(token, cwd=cwd)
    try:
        action = cfg.action_for_chord(token)
    except ValueError:
        action = None
    if action:
        print(tint("ok", f"  ∞ {action}  ({normalize_chord(token)})"))
        return run_action(action, cwd=cwd)
    print(tint("warn", f"  unknown: {token!r}"), file=sys.stderr)
    return 1


def _listen_lines(cwd: pathlib.Path, cfg: ShortcutConfig, *, once: bool) -> int:
    for line in sys.stdin:
        line = line.strip()
        if line.lower() in ("q", "quit", "exit"):
            return 0
        code = _dispatch_chord_or_action(cwd, cfg, line)
        if once:
            return code
    return 0


def _listen_tty(cwd: pathlib.Path, cfg: ShortcutConfig, *, once: bool) -> int:
    import select
    import termios
    import tty
    from .platform_util import tty_raw_listen_supported
    if not tty_raw_listen_supported():
        print(tint("warn", "  falling back to line protocol"), file=sys.stderr)
        return _listen_lines(cwd, cfg, once=once)
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        buf = ""
        while True:
            if select.select([fd], [], [], 0.5)[0]:
                ch = os.read(fd, 1).decode("utf-8", errors="ignore")
                if ch in ("q", "Q") and not buf:
                    print()
                    return 0
                if ch == "\x03":  # ctrl+c
                    print()
                    return 130
                if ch == "\x1b":
                    # escape sequence
                    seq = ch
                    time.sleep(0.02)
                    while select.select([fd], [], [], 0.02)[0]:
                        seq += os.read(fd, 1).decode("utf-8", errors="ignore")
                    key = _decode_escape(seq)
                    if key:
                        code = _dispatch_chord_or_action(cwd, cfg, key)
                        if once:
                            return code
                    continue
                if ch in ("\n", "\r"):
                    if buf:
                        code = _dispatch_chord_or_action(cwd, cfg, buf)
                        buf = ""
                        if once:
                            return code
                    continue
                if ch.isprintable():
                    buf += ch
                    # ctrl+letter arrives as bytes 1-26 in cbreak — handled below
                # Control characters as ctrl+letter
                if len(ch) == 1 and 1 <= ord(ch) <= 26 and ch not in ("\n", "\r", "\t"):
                    letter = chr(ord("a") + ord(ch) - 1)
                    code = _dispatch_chord_or_action(cwd, cfg, f"ctrl+{letter}")
                    if once:
                        return code
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _decode_escape(seq: str) -> str:
    if seq == "\x1b":
        return "escape"
    # CSI: ESC [ n ~
    m = re.match(r"^\x1b\[(\d+)(~)$", seq)
    if m and m.group(1) in _FUNC_KEY_CSI:
        return _FUNC_KEY_CSI[m.group(1)]
    # ESC [ 1 ; mods letter  (modifier function keys vary by terminal)
    m = re.match(r"^\x1b\[(?:1;)?(\d+)([A-Z~])$", seq)
    if m:
        # best-effort: ignore mods in tty listen; prefer line protocol for Micro
        code = m.group(1)
        if code in _FUNC_KEY_CSI:
            return _FUNC_KEY_CSI[code]
    # xterm: ESC O P..S = F1-F4
    m = re.match(r"^\x1bO([P-S])$", seq)
    if m:
        return {"P": "f1", "Q": "f2", "R": "f3", "S": "f4"}[m.group(1)]
    return ""


# ---------------------------------------------------------------------------
# Views / export (Codex Micro + Input)
# ---------------------------------------------------------------------------

MICRO_LAYOUT = {
    # Physical suggestion for the 13 mechanical keys (Input layer 0 / 1).
    "mission": [
        ("K1", "status", "idle / status"),
        ("K2", "watch", "thinking feed"),
        ("K3", "report", "complete log"),
        ("K4", "goal", "goal contract"),
        ("K5", "approve", "accept"),
        ("K6", "reject", "reject"),
        ("K7", "resume", "continue"),
        ("K8", "extend", "extend"),
        ("K9", "brief", "new mission"),
        ("K10", "cancel", "error / cancel"),
        ("K11", "doctor", "doctor"),
        ("K12", "inspect", "inspect"),
        ("K13", "run", "custom / run"),
    ],
    "harness": [
        ("K1", "providers", "agents"),
        ("K2", "doctor", "doctor"),
        ("K3", "inspect", "inspect"),
        ("K4", "run", "run"),
        ("K5", "build", "build"),
        ("K6", "cancel", "cancel"),
        ("K7", "status", "status"),
        ("K8", "watch", "watch"),
        ("K9", "report", "report"),
        ("K10", "goal", "goal"),
        ("K11", "approve", "accept"),
        ("K12", "reject", "reject"),
        ("K13", "brief", "brief"),
    ],
}


def list_actions(cfg: ShortcutConfig) -> str:
    lines = [tint("bold", "∞ Absoloop actions"), ""]
    group_order = ("mission", "gate", "harness", "system")
    by_group: Dict[str, List[Action]] = {g: [] for g in group_order}
    for action in ACTIONS.values():
        by_group.setdefault(action.group, []).append(action)
    for group in group_order:
        if not by_group.get(group):
            continue
        lines.append(tint("cyan", f"  [{group}]"))
        for action in by_group[group]:
            chord = cfg.chord_for(action.name) or "—"
            # Widths ignore ANSI — keep name/chord plain for alignment.
            lines.append(
                f"  {action.name:<14} {tint('dim', chord):<24} {action.summary}")
    lines.append("")
    lines.append(tint("dim", "Run:  absoloop do <action>"))
    lines.append(tint("dim", "Bind: absoloop shortcuts bind <action> <chord>"))
    lines.append(tint("dim", "Listen: absoloop shortcuts listen"))
    lines.append(tint("dim", "Micro: absoloop shortcuts layout · export --format input"))
    return "\n".join(lines)


def _print_micro_compact(cfg: ShortcutConfig, layer: str) -> None:
    print(tint("bold", f"  Codex Micro · layer {layer}"))
    for slot, action, label in MICRO_LAYOUT.get(layer, []):
        chord = cfg.chord_for(action) if action in ACTIONS else ""
        print(f"  {tint('cyan', slot):<6} {action:<10} {tint('dim', chord):<20} {label}")
    print()


def render_layout(cfg: ShortcutConfig, layer: str = "mission") -> str:
    lines = [
        tint("bold", f"∞ Codex Micro layout — {layer}"),
        tint("dim", "Map each physical key in Work Louder Input → chord"),
        tint("dim", "Dial: switch Input layers (mission ↔ harness)"),
        tint("dim", "Joystick: bind four custom actions in Input"),
        "",
    ]
    for slot, action, label in MICRO_LAYOUT.get(layer, MICRO_LAYOUT["mission"]):
        chord = cfg.chord_for(action) if action in ACTIONS else "—"
        act = ACTIONS.get(action)
        summary = act.summary if act else ""
        lines.append(
            f"  {slot:<4}  {tint('gold', action):<18} {tint('accent', chord):<22} "
            f"{tint('dim', label)} — {summary}")
    lines.append("")
    lines.append(tint("dim", "Export JSON for reference: absoloop shortcuts export --format json"))
    return "\n".join(lines)


def export_bundle(cfg: ShortcutConfig, fmt: str = "markdown") -> str:
    if fmt == "json":
        payload = {
            "device": "work-louder-codex-micro",
            "note": "HID keyboard — program these chords in Input / Codex remap. "
                    "Absoloop listens via `absoloop shortcuts listen` or run "
                    "`absoloop do <action>` from any shell macro.",
            "layers": {
                name: [
                    {"key": slot, "action": action, "chord": cfg.chord_for(action),
                     "label": label}
                    for slot, action, label in rows
                ]
                for name, rows in MICRO_LAYOUT.items()
            },
            "actions": {
                name: {
                    "summary": act.summary,
                    "group": act.group,
                    "chord": cfg.chord_for(name),
                    "argv": list(act.argv),
                    "needs_prompt": act.needs_prompt,
                    "micro_slot": act.micro_slot,
                }
                for name, act in ACTIONS.items()
            },
            "line_protocol": [
                "action:<name>",
                "chord:<chord>",
                "<name>",
            ],
        }
        return json.dumps(payload, indent=2) + "\n"

    if fmt == "input":
        # Human recipe for the Input app (no proprietary file format published).
        lines = [
            "# Absoloop → Work Louder Input (Codex Micro)",
            "",
            "Codex Micro stores keymaps on-device. In Input (desktop):",
            "1. Select layer 0 = Absoloop Mission, layer 1 = Absoloop Harness",
            "2. For each key below, set the binding type to Keyboard Shortcut",
            "   (or single key for F13–F24) matching the chord",
            "3. Optional: map Dial rotate to Layer Up / Layer Down",
            "4. Optional: map Joystick N/E/S/W to four `absoloop do …` shell macros",
            "",
            "Shell macro alternative (any key → Open App / Run Shortcut):",
            "  absoloop do status",
            "  absoloop do approve --yes",
            "",
            "## Layer 0 — Mission",
        ]
        for slot, action, label in MICRO_LAYOUT["mission"]:
            lines.append(f"- {slot}: {action} → `{cfg.chord_for(action)}`  # {label}")
        lines.append("")
        lines.append("## Layer 1 — Harness")
        for slot, action, label in MICRO_LAYOUT["harness"]:
            lines.append(f"- {slot}: {action} → `{cfg.chord_for(action)}`  # {label}")
        lines.append("")
        lines.append("## Listen")
        lines.append("Keep a terminal running: `absoloop shortcuts listen`")
        lines.append("Or bind keys to shell: `absoloop do <action>` (no listener needed).")
        lines.append("")
        return "\n".join(lines)

    # markdown cheat sheet
    lines = [
        "# Absoloop shortcuts",
        "",
        "| Action | Chord | Group | Summary |",
        "|---|---|---|---|",
    ]
    for name, act in ACTIONS.items():
        lines.append(
            f"| `{name}` | `{cfg.chord_for(name)}` | {act.group} | {act.summary} |")
    lines.append("")
    lines.append("## Codex Micro")
    lines.append("")
    lines.append(render_layout(cfg, "mission"))
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry for shortcuts subcommands
# ---------------------------------------------------------------------------

def shortcuts_command(argv: List[str], *, cwd: Optional[pathlib.Path] = None) -> int:
    import argparse
    cwd = cwd or pathlib.Path.cwd()
    parser = argparse.ArgumentParser(
        prog="absoloop shortcuts",
        description="Customizable Absoloop actions for keyboard + Codex Micro")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list actions and chords")
    p_run = sub.add_parser("run", help="run an action by name")
    p_run.add_argument("action")
    p_run.add_argument("extra", nargs="*")
    p_run.add_argument("--yes", "-y", action="store_true")
    p_run.add_argument("--text", "-t", default=None,
                       help="prompt text for reject/run/brief/cancel")

    p_bind = sub.add_parser("bind", help="bind action to a chord (user config)")
    p_bind.add_argument("action")
    p_bind.add_argument("chord")

    p_export = sub.add_parser("export", help="export Micro / Input / markdown")
    p_export.add_argument("--format", choices=("markdown", "json", "input"),
                          default="markdown")
    p_export.add_argument("-o", "--output", default="")

    p_layout = sub.add_parser("layout", help="show Codex Micro key layout")
    p_layout.add_argument("--layer", choices=("mission", "harness"),
                          default="mission")

    p_listen = sub.add_parser("listen", help="listen for chords / line protocol")
    p_listen.add_argument("--once", action="store_true")

    p_show = sub.add_parser("show", help="show one action")
    p_show.add_argument("action")

    args = parser.parse_args(argv)
    cfg = load_shortcuts(cwd)

    if args.cmd == "list":
        print(list_actions(cfg))
        return 0
    if args.cmd == "show":
        act = ACTIONS.get(args.action)
        if not act:
            print(f"unknown action {args.action!r}", file=sys.stderr)
            return 2
        print(f"{act.name}")
        print(f"  {act.summary}")
        print(f"  group:  {act.group}")
        print(f"  chord:  {cfg.chord_for(act.name)}")
        print(f"  argv:   absoloop {' '.join(act.argv)}")
        print(f"  micro:  {act.micro_slot or '—'}")
        return 0
    if args.cmd == "run":
        return run_action(args.action, cwd=cwd, extra=args.extra,
                          yes=args.yes, prompt_text=args.text)
    if args.cmd == "bind":
        if args.action not in ACTIONS:
            print(f"unknown action {args.action!r}", file=sys.stderr)
            return 2
        path = save_user_binding(args.action, args.chord)
        print(f"bound {args.action} → {normalize_chord(args.chord)}")
        print(f"wrote {path}")
        return 0
    if args.cmd == "export":
        body = export_bundle(cfg, args.format)
        if args.output:
            pathlib.Path(args.output).write_text(body, encoding="utf-8")
            print(f"wrote {args.output}")
        else:
            print(body, end="" if body.endswith("\n") else "\n")
        return 0
    if args.cmd == "layout":
        print(render_layout(cfg, args.layer))
        return 0
    if args.cmd == "listen":
        return listen(cwd, once=args.once)
    return 2


def do_command(argv: List[str], *, cwd: Optional[pathlib.Path] = None) -> int:
    """`absoloop do <action> [args…]` — shortest path from Micro shell macros."""
    import argparse
    cwd = cwd or pathlib.Path.cwd()
    parser = argparse.ArgumentParser(prog="absoloop do")
    parser.add_argument("action", help="action name (see absoloop shortcuts list)")
    parser.add_argument("extra", nargs="*")
    parser.add_argument("--yes", "-y", action="store_true")
    parser.add_argument("--text", "-t", default=None)
    args = parser.parse_args(argv)
    return run_action(args.action, cwd=cwd, extra=args.extra,
                      yes=args.yes, prompt_text=args.text)
