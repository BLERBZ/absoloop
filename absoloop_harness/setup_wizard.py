"""Absoloop Setup Wizard — guided first-run onboarding.

``absoloop setup`` walks a new user through PATH, providers, preferences, and
the first recommended command. Designed to feel like a short product tour,
not a config dump.

State persists in ``~/.absoloop/setup.json`` (override with
``ABSOLOOP_SETUP_STATE``). Bare ``absoloop`` on a TTY offers this wizard when
setup has not completed. Flags: ``-y``, ``--force``, ``--check``, ``--reset``.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .briefing import ask, pick, tint
from .platform_util import is_windows, prerequisite_checks, tooling_home

SETUP_STATE = pathlib.Path(
    os.environ.get("ABSOLOOP_SETUP_STATE",
                   str(pathlib.Path.home() / ".absoloop" / "setup.json")))

PROVIDER_INSTALL: Dict[str, Tuple[str, str]] = {
    "grok": (
        "Grok Build CLI",
        "curl -fsSL https://x.ai/cli/install.sh | bash   then: grok login",
    ),
    "claude": (
        "Claude Code CLI",
        "https://docs.anthropic.com/en/docs/claude-code/overview   then: claude login",
    ),
    "codex": (
        "OpenAI Codex CLI",
        "npm i -g @openai/codex   (or see OpenAI docs)   then: codex login",
    ),
}

TOTAL_STEPS = 6


@dataclass
class SetupResult:
    completed: bool = False
    path_linked: bool = False
    providers_ready: List[str] = field(default_factory=list)
    user_config_written: bool = False
    micro_tip_shown: bool = False
    gitignore_status: str = ""
    next_hint: str = ""
    aborted: bool = False


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def setup_state_path() -> pathlib.Path:
    return SETUP_STATE


def is_setup_complete() -> bool:
    path = setup_state_path()
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("completed"))


def mark_setup_complete(result: SetupResult) -> pathlib.Path:
    path = setup_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "completed": True,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "version": 1,
        "path_linked": result.path_linked,
        "providers_ready": list(result.providers_ready),
        "user_config_written": result.user_config_written,
        "home": str(tooling_home()),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def reset_setup_state() -> None:
    path = setup_state_path()
    if path.is_file():
        path.unlink()


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def _rule(width: int = 58) -> str:
    return tint("dim", "─" * width)


def _step_header(step: int, title: str) -> None:
    print()
    print(tint("accent", "∞") + " " + tint("bold", "ABSOLOOP SETUP")
          + tint("dim", f"  ·  step {step} of {TOTAL_STEPS}"))
    print(_rule())
    print(f"  {tint('gold', title)}")
    print()


def _pause(yes: bool, message: str = "Press Enter to continue") -> bool:
    """Return False if user aborts."""
    if yes:
        return True
    try:
        answer = input(tint("dim", f"  {message} · q quit ") ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if answer in ("q", "quit", "abort"):
        return False
    return True


def _ok(text: str) -> None:
    print(f"  {tint('ok', '✓')} {text}")


def _warn(text: str) -> None:
    print(f"  {tint('warn', '!')} {text}")


def _dim(text: str) -> None:
    print(f"  {tint('dim', text)}")


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def _step_welcome(yes: bool) -> bool:
    _step_header(1, "Welcome")
    print("  Absoloop is Synergetic Loops — on your machine.")
    print("  Builder + critic + you. Hard budgets. Local CLIs.")
    print()
    print("  This wizard will:")
    _dim("1. Put Absoloop on your PATH (if needed)")
    _dim("2. Find Grok / Claude Code / Codex")
    _dim("3. Save sensible defaults")
    _dim("4. Recommend ignoring `.absoloop/` in git")
    _dim("5. Show your first command")
    print()
    print(tint("dim", "  Needs: Python 3.9+ and at least one provider CLI."))
    return _pause(yes, "Ready? Enter")


def _ensure_path_link(home: pathlib.Path) -> Tuple[bool, str]:
    """Symlink (Unix) or instruct (Windows). Returns (linked_or_ok, message)."""
    script = home / "bin" / "absoloop"
    if not script.is_file():
        return False, f"missing {script} — is ABSOLOOP_HOME correct?"

    which = shutil.which("absoloop")
    if which:
        try:
            resolved = pathlib.Path(which).resolve()
            if resolved == script.resolve() or (
                    resolved.suffix.lower() in (".cmd", ".bat")
                    and resolved.with_suffix("").resolve() == script.resolve()):
                return True, f"already on PATH → {which}"
        except OSError:
            return True, f"absoloop on PATH → {which}"

    if is_windows():
        bin_dir = home / "bin"
        return False, (
            f"add this folder to your User PATH, then reopen the terminal:\n"
            f"         {bin_dir}\n"
            f"         (absoloop.cmd lives there and sets ABSOLOOP_HOME)"
        )

    local_bin = pathlib.Path.home() / ".local" / "bin"
    try:
        local_bin.mkdir(parents=True, exist_ok=True)
        dest = local_bin / "absoloop"
        if dest.is_symlink() or dest.is_file():
            try:
                dest.unlink()
            except OSError:
                pass
        dest.symlink_to(script.resolve())
        # Check if ~/.local/bin is typically on PATH
        path_env = os.environ.get("PATH", "")
        if str(local_bin) not in path_env.split(os.pathsep):
            return True, (
                f"linked {dest} → {script.name}\n"
                f"         add ~/.local/bin to PATH if `absoloop` is not found:\n"
                f"         export PATH=\"$HOME/.local/bin:$PATH\""
            )
        return True, f"linked {dest}"
    except OSError as exc:
        return False, f"could not create symlink: {exc}"


def _step_path(yes: bool, result: SetupResult) -> bool:
    _step_header(2, "Install on PATH")
    home = tooling_home()
    _ok(f"Absoloop home: {home}")
    for note in prerequisite_checks():
        if note.startswith("fix:"):
            _warn(note.replace("fix: ", "", 1))
        elif note.startswith("ABSOLOOP_HOME=") or note.startswith("python="):
            _dim(note)

    if yes or not sys.stdin.isatty():
        linked, msg = _ensure_path_link(home)
        result.path_linked = linked
        if linked:
            _ok(msg.replace("\n", "\n    "))
        else:
            _warn(msg.replace("\n", "\n    "))
        return True

    print("  Put `absoloop` on your PATH so any terminal can find it.")
    print()
    choice = pick(
        "  PATH setup",
        ["link", "skip", "show"],
        "link",
        {
            "link": "create ~/.local/bin/absoloop (recommended)",
            "skip": "I'll manage PATH myself",
            "show": "just show me the commands",
        },
    )
    if choice == "skip":
        _dim("skipped — you can re-run: absoloop setup")
        return _pause(yes)
    if choice == "show":
        if is_windows():
            _dim(f"Add to User PATH: {home / 'bin'}")
        else:
            _dim(f"ln -sf {home / 'bin' / 'absoloop'} ~/.local/bin/absoloop")
            _dim('export PATH="$HOME/.local/bin:$PATH"')
        return _pause(yes)

    linked, msg = _ensure_path_link(home)
    result.path_linked = linked
    if linked:
        _ok(msg.replace("\n", "\n    "))
    else:
        _warn(msg.replace("\n", "\n    "))
    return _pause(yes)


def _probe_providers() -> List[Tuple[str, Optional[str], str]]:
    """(name, path_or_None, auth_hint)."""
    rows = []
    try:
        from .providers import make_adapter
    except Exception:
        for name in ("grok", "claude", "codex"):
            path = shutil.which(name)
            rows.append((name, path, ""))
        return rows
    for name in ("grok", "claude", "codex"):
        try:
            adapter = make_adapter(name, {})
            path = adapter.executable()
            hint = adapter.auth_hint() if path else ""
            rows.append((name, path, hint))
        except Exception:
            rows.append((name, shutil.which(name), ""))
    return rows


def _step_providers(yes: bool, result: SetupResult) -> bool:
    _step_header(3, "AI providers")
    print("  Absoloop wraps local CLIs — it does not replace their login.")
    print("  You need at least one of: grok · claude · codex")
    print()

    ready: List[str] = []
    for name, path, hint in _probe_providers():
        label, install = PROVIDER_INSTALL[name]
        if path:
            ready.append(name)
            _ok(f"{name:<8} {path}")
            if hint:
                if hint.startswith("no credentials"):
                    _warn(f"         auth: {hint}")
                else:
                    _dim(f"         auth: {hint}")
        else:
            _warn(f"{name:<8} not on PATH — {label}")
            _dim(f"         install: {install}")
        print()

    result.providers_ready = ready
    if ready:
        _ok(f"{len(ready)} provider(s) ready: {', '.join(ready)}")
    else:
        _warn("No providers found yet — install one, then re-run absoloop setup")
        print()
        print(tint("dim", "  Tip: open a new terminal after installing so PATH updates."))

    if yes:
        return True
    if not ready:
        print()
        cont = ask("  Continue without a provider? [y/N]", "n").lower()
        if cont not in ("y", "yes"):
            print(tint("dim", "  Install a provider, then run: absoloop setup"))
            return False
    return _pause(yes)


def _write_user_defaults(delivery: str = "local") -> pathlib.Path:
    user_dir = pathlib.Path.home() / ".absoloop"
    user_dir.mkdir(parents=True, exist_ok=True)
    path = user_dir / "absoloop.toml"
    if path.is_file():
        return path
    body = f"""# Absoloop user defaults — written by `absoloop setup`
# Project absoloop.toml overrides these. See absoloop.toml.example.

[permissions]
default_profile = "edit"

[gates]
required = ["tests"]

[gates.commands]
tests = "python -m unittest discover -s tests"

[shortcuts]
enabled = true
confirm_dangerous = true

# Codex Micro: map keys in Input to `absoloop do <action>`
# Run: absoloop shortcuts layout
"""
    path.write_text(body, encoding="utf-8")
    return path


def _step_preferences(yes: bool, result: SetupResult) -> bool:
    _step_header(4, "Defaults & Codex Micro")
    delivery = "local"
    if not yes and sys.stdin.isatty():
        delivery = pick(
            "  Where should accepted work land by default?",
            ["local", "git", "out"],
            "local",
            {
                "local": "stay in the working tree (you commit) — recommended",
                "git": "commit to branch absoloop/<loop>",
                "out": "export a pack under ~/absoloop/out/",
            },
        )
    path = _write_user_defaults(delivery)
    result.user_config_written = True
    _ok(f"user config → {path}")
    _dim(f"default delivery preference: {delivery} (edit anytime)")

    print()
    print("  " + tint("bold", "Codex Micro / keyboard"))
    _dim("Best setup on every OS: map keys to shell macros")
    _dim("  absoloop do status")
    _dim("  absoloop do approve --yes")
    _dim("See the full pad map:  absoloop shortcuts layout")
    _dim("Export Input recipe:   absoloop shortcuts export --format input -o micro.md")
    result.micro_tip_shown = True
    return _pause(yes)


def _step_gitignore(yes: bool, result: SetupResult) -> bool:
    """Offer to ignore `.absoloop/` in the current project's `.gitignore`."""
    _step_header(5, "Gitignore (recommended)")
    from .gitignore_util import ensure_absoloop_gitignore

    cwd = pathlib.Path.cwd().resolve()
    print("  Absoloop stores mission state under "
          + tint("bold", ".absoloop/")
          + " (runtime, reports, ledgers, telemetry).")
    print(tint("dim", "  Recommended: add `.absoloop/` to this project's "
                       ".gitignore so that state is never committed."))
    print()
    _dim(f"Project: {cwd}")

    looks_like_project = (cwd / ".git").exists() or (cwd / ".gitignore").is_file()
    if not looks_like_project:
        _dim("No git repo / .gitignore in this directory.")
        if yes:
            _dim("Skipping auto-edit in non-interactive mode "
                 "(re-run setup inside a project, or start a mission).")
            result.gitignore_status = "skipped"
            return True
        print()
        _dim("You can still create .gitignore here, or skip.")

    print()
    status = ensure_absoloop_gitignore(cwd, yes=yes, ask_user=not yes)
    result.gitignore_status = status
    if status == "added":
        _ok(f"added `.absoloop/` → {cwd / '.gitignore'}")
    elif status == "exists":
        _ok("`.absoloop/` already ignored")
    elif status == "declined":
        _warn("left .gitignore unchanged (you can add `.absoloop/` later)")
    else:
        _dim(f"gitignore: {status}")
    return _pause(yes)


def _step_finish(yes: bool, result: SetupResult) -> bool:
    _step_header(6, "You're ready")
    mark_setup_complete(result)
    _ok(f"setup saved → {setup_state_path()}")
    print()

    if result.providers_ready:
        engine = result.providers_ready[0]
        result.next_hint = f'absoloop "Make all tests pass"'
        print("  " + tint("bold", "Start a mission (recommended)"))
        print()
        print(f"    {tint('accent', result.next_hint)}")
        print()
        _dim("One card to review → Enter launches the loop.")
        _dim(f"Your first ready engine: {engine}")
        print()
        print("  " + tint("bold", "Or try the harness"))
        harness_ex = 'absoloop run --provider %s "Fix the failing tests"' % engine
        print("    " + tint("dim", harness_ex))
    else:
        result.next_hint = "absoloop setup"
        print("  " + tint("bold", "Next"))
        _warn("Install grok, claude, or codex, then run: absoloop setup")
        print(f"    {tint('dim', 'absoloop doctor   # re-check anytime')}")

    print()
    print("  " + tint("bold", "Handy commands"))
    _dim("absoloop doctor     environment + provider health")
    _dim("absoloop status     mission snapshot")
    _dim("absoloop watch      live terminal dashboard while looping")
    _dim("absoloop --zcomb    briefing + launch with ZComb Kanban (Node.js 18+)")
    _dim("absoloop report     Markdown report + lite viewer")
    _dim("absoloop --help     full command list")
    print()
    print(tint("ok", "  ∞  Setup complete. The loop is yours."))
    print()
    result.completed = True
    return True


def offer_first_mission(yes: bool, result: SetupResult) -> Optional[str]:
    """Optionally return an objective string to hand off to Mission Briefing."""
    if yes or not result.providers_ready or not sys.stdin.isatty():
        return None
    print(_rule())
    choice = pick(
        "  What next?",
        ["mission", "later"],
        "mission",
        {
            "mission": "start Mission Briefing now",
            "later": "I'll run a command myself",
        },
    )
    if choice != "mission":
        return None
    objective = ask("  Mission objective (one sentence)",
                    "Make all tests pass")
    return objective.strip() or None


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def run_wizard(*, yes: bool = False, force: bool = False) -> SetupResult:
    """Run the interactive (or -y) setup wizard."""
    result = SetupResult()
    if is_setup_complete() and not force:
        print(tint("bold", "∞ Absoloop setup")
              + tint("dim", "  ·  already completed"))
        print(tint("dim", f"  state: {setup_state_path()}"))
        if yes:
            print(tint("dim", "  Tip: absoloop setup --force to run again"))
            result.completed = True
            # Refresh provider list for handoff callers.
            for name, path, _hint in _probe_providers():
                if path:
                    result.providers_ready.append(name)
            return result
        print()
        redo = ask("  Run the wizard again? [y/N]", "n").lower()
        if redo not in ("y", "yes"):
            print(tint("dim",
                       "  Tip: absoloop doctor · absoloop \"your objective\" · "
                       "absoloop --zcomb · absoloop zcomb"))
            result.completed = True
            for name, path, _hint in _probe_providers():
                if path:
                    result.providers_ready.append(name)
            return result

    print()
    print(tint("accent", "∞") + " " + tint("bold", "Absoloop")
          + tint("dim", "  ·  setup wizard"))
    print(tint("dim", "  A few short steps. Enter continues · q quits anytime."))

    if not _step_welcome(yes):
        result.aborted = True
        print(tint("dim", "  Setup paused. Resume anytime: absoloop setup"))
        return result
    if not _step_path(yes, result):
        result.aborted = True
        return result
    if not _step_providers(yes, result):
        result.aborted = True
        return result
    if not _step_preferences(yes, result):
        result.aborted = True
        return result
    if not _step_gitignore(yes, result):
        result.aborted = True
        return result
    _step_finish(yes, result)
    return result


def should_offer_first_run() -> bool:
    """True when a TTY user has never finished setup."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False
    if os.environ.get("ABSOLOOP_SKIP_SETUP"):
        return False
    return not is_setup_complete()


def first_run_gate() -> str:
    """Ask a first-time user what to do. Returns: setup | continue | quit."""
    print()
    print(tint("accent", "∞") + " " + tint("bold", "First time here?"))
    print(tint("dim", "  A 2-minute setup wizard gets PATH, providers, and defaults ready."))
    print()
    print("  " + tint("bold", "Enter") + " run setup   "
          + tint("dim", "s") + " skip   "
          + tint("dim", "q") + " quit")
    try:
        key = input(tint("bold", "  ▶ ") + tint("dim", " ") ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return "quit"
    if key in ("q", "quit"):
        return "quit"
    if key in ("s", "skip", "later", "n", "no"):
        return "continue"
    return "setup"


def setup_command(argv: Sequence[str]) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="absoloop setup",
        description="Guided first-run wizard — PATH, providers, defaults, next steps.")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="non-interactive: link PATH, write defaults, print summary")
    parser.add_argument("--force", action="store_true",
                        help="run even if setup was completed before")
    parser.add_argument("--reset", action="store_true",
                        help="clear saved setup state and exit")
    parser.add_argument("--check", action="store_true",
                        help="exit 0 if setup completed, 1 otherwise (no UI)")
    args = parser.parse_args(list(argv))

    if args.check:
        return 0 if is_setup_complete() else 1
    if args.reset:
        reset_setup_state()
        print(f"cleared {setup_state_path()}")
        return 0

    result = run_wizard(yes=args.yes, force=args.force)
    if result.aborted:
        return 1
    if not result.completed:
        return 1

    # Non-interactive: stop after summary. Interactive: optional mission handoff
    # is handled by the bin/absoloop wrapper when it wants to chain.
    return 0 if result.providers_ready or args.yes else 2
