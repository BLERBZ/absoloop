"""absoloop-cli: the multi-provider harness surface.

  absoloop doctor                     provider health, auth readiness, fixes
  absoloop providers                  capability matrix
  absoloop run --provider X "task"    single workflow
  absoloop build --strategy S ...     race / council
  absoloop review --implementer A --reviewer B "task"
  absoloop resume <run-id> "prompt"   continue a run's native session
  absoloop cancel <run-id>            kill a live run from another terminal
  absoloop inspect <run-id>           manifest + artifacts view
  absoloop apply <run-id> --candidate C   apply a candidate patch to the repo
  absoloop config                     resolved config with per-value sources

Kept intentionally minimal and Absoloop-branded: provider lanes, elapsed
time, tool activity, and final outcome — no raw stream dumps by default.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
from typing import Any, Dict, List, Optional

from .config import PROVIDERS, load_config
from .core import AgentRequest, EventType, SessionRef
from .orchestrator import Orchestrator
from .providers import make_adapter
from . import runtime as run_ctrl
from .workspace import RunStore, list_runs

HARNESS_COMMANDS = ("doctor", "providers", "run", "build", "review",
                    "cancel", "inspect", "apply", "config")

_USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _tint(code: str, text: str) -> str:
    return f"\x1b[{code}m{text}\x1b[0m" if _USE_COLOR else text


def _root() -> pathlib.Path:
    return pathlib.Path.cwd()


def _event_printer(verbose: bool):
    started = time.time()
    lanes_started = set()

    def show(event) -> None:
        elapsed = f"{time.time() - started:6.1f}s"
        lane = f"[{event.provider}]"
        if event.type == EventType.RUN_STARTED:
            # The supervisor synthesizes a spawn event and most providers
            # also emit their own start — show one "started" per lane.
            if event.provider in lanes_started:
                return
            lanes_started.add(event.provider)
            print(f"{elapsed} {_tint('1', lane)} started")
        elif event.type == EventType.TOOL_STARTED:
            print(f"{elapsed} {lane} tool: {event.text[:120]}")
        elif event.type == EventType.FILE_CHANGED:
            print(f"{elapsed} {lane} edit: {event.text[:120]}")
        elif event.type == EventType.RUN_COMPLETED:
            print(f"{elapsed} {_tint('32', lane)} completed")
        elif event.type == EventType.RUN_FAILED:
            print(f"{elapsed} {_tint('31', lane)} failed: {event.text[:160]}")
        elif event.type == EventType.PROGRESS and verbose:
            print(f"{elapsed} {_tint('2', lane)} {event.text[:120]}")
        elif event.type == EventType.TEXT_DELTA and verbose:
            text = " ".join(event.text.split())[:160]
            if text:
                print(f"{elapsed} {lane} {text}")

    return show


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def doctor_command(argv: List[str]) -> int:
    from .platform_util import prerequisite_checks, rewrite_python_gate

    cfg = load_config(_root())
    print("Absoloop doctor — environment + provider health\n")
    worst = 0

    print("  environment")
    for note in prerequisite_checks():
        if note.startswith("fix:"):
            worst = 1
            print(f"           {_tint('33', note)}")
        else:
            print(f"           {note}")
    gate = str(cfg.get("gates", "commands", default={}).get("tests") or "")
    if gate:
        rewritten = rewrite_python_gate(gate)
        print(f"           gate:    {rewritten}")
    print()

    available_count = 0
    for name in PROVIDERS:
        adapter = make_adapter(name, cfg.get("providers", name, default={}))
        probe = adapter.probe()
        mark = _tint("32", "ok") if probe.available else _tint("31", "missing")
        print(f"  {name:<8} {mark}")
        if probe.available:
            available_count += 1
            print(f"           path:    {probe.info.executable}")
            print(f"           version: {probe.info.version or 'unknown'}")
            auth = probe.info.auth_hint or adapter.auth_hint()
            if auth:
                tone = "33" if auth.startswith("no credentials") else "0"
                label = "auth:    "
                print(f"           {label}{_tint(tone, auth) if tone != '0' else auth}")
            caps = [key for key, val in probe.capabilities.to_json().items() if val]
            print(f"           caps:    {', '.join(caps)}")
            if name == "codex":
                style = adapter.config.get("resume_style") or "exec-resume"
                print(f"           resume:  {style}")
        for problem in probe.problems:
            worst = 1
            print(f"           {_tint('33', 'fix:')} {problem}")
        print()

    if available_count == 0:
        worst = 1
        print(_tint("31", "no providers on PATH — install grok, claude, and/or codex"))
        print("  macOS/Linux: ensure npm/cargo install bins are on PATH")
        print("  Windows:    add provider install dirs to PATH; use absoloop.cmd from bin\\")
        print()
    elif available_count < len(PROVIDERS):
        print(f"note: {available_count}/{len(PROVIDERS)} providers available — "
              "race/council need the ones you list in --providers")
        print()

    print("  Codex Micro")
    print("           map keys in Input to `absoloop do <action>` (works on all OS)")
    print("           or: absoloop shortcuts layout · export --format input")
    print("           Unix TTY: absoloop shortcuts listen  (F13–F24)")
    print()

    if not (_root() / "absoloop.toml").is_file():
        print("note: no project absoloop.toml — using defaults "
              "(create one to configure gates and providers)")
    return worst


def providers_command(argv: List[str]) -> int:
    cfg = load_config(_root())
    probes = [make_adapter(n, cfg.get("providers", n, default={})).probe()
              for n in PROVIDERS]
    fields = ["streaming_json", "session_resume", "structured_output",
              "permission_modes", "native_sandbox", "turn_limit",
              "prompt_via_stdin", "cost_reporting"]
    width = max(len(f) for f in fields) + 2
    header = "capability".ljust(width) + "".join(p.info.name.ljust(9) for p in probes)
    print(header)
    print("-" * len(header))
    for fieldname in fields:
        row = fieldname.ljust(width)
        for probe in probes:
            value = probe.capabilities.to_json()[fieldname]
            row += ("yes" if value else "no").ljust(9)
        print(row)
    print()
    for probe in probes:
        state = "available" if probe.available else "NOT FOUND"
        print(f"{probe.info.name}: {state} "
              f"{probe.info.version and ('v' + probe.info.version)}")
    return 0


def run_command(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="absoloop run")
    parser.add_argument("prompt", nargs="?",
                        help="task prompt (asked in the briefing if omitted)")
    parser.add_argument("--provider", default=None, choices=list(PROVIDERS))
    parser.add_argument("--profile", default=None, choices=["read", "edit", "full"])
    parser.add_argument("--no-isolate", action="store_true",
                        help="run in the repo root instead of an isolated worktree")
    parser.add_argument("--keep-worktrees", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="skip the run briefing and launch immediately")
    args = parser.parse_args(argv)
    cfg = load_config(_root())
    profile = args.profile or str(cfg.get("permissions", "default_profile",
                                          default="edit"))
    from . import briefing as ux
    available = [p for p in PROVIDERS
                 if make_adapter(p, cfg.get("providers", p, default={})).probe().available]
    provider = args.provider or (available[0] if available else PROVIDERS[0])
    prompt = (args.prompt or "").strip()
    interactive = sys.stdin.isatty() and sys.stdout.isatty() and not args.yes
    if not prompt:
        if not interactive:
            print("error: pass a prompt, e.g. absoloop run --provider claude \"…\"",
                  file=sys.stderr)
            return 2
        print(ux.tint("bold", "Harness run — what's the task?"))
        prompt = ux.ask("  prompt")
        while not prompt:
            prompt = ux.ask("  prompt (required)")
    if interactive:
        labels = {p: ("✓ ready" if p in available else "✗ missing") for p in PROVIDERS}
        print()
        print(ux.tint("accent", "∞") + " " + ux.tint("bold", "RUN BRIEFING"))
        print(ux.tint("dim", "─" * 50))
        print(f"  {ux.tint('gold', 'task')}      {prompt}")
        print(f"  {ux.tint('cyan', 'provider')}  {provider}  "
              f"{ux.tint('ok', 'ready') if provider in available else ux.tint('err', 'missing')}")
        print(f"  {ux.tint('cyan', 'profile')}   {profile}")
        print(f"  {ux.tint('cyan', 'isolate')}   {'no (repo root)' if args.no_isolate else 'yes (worktree)'}")
        print(ux.tint("dim", "─" * 50))
        print("  " + ux.tint("bold", "Enter") + " launch   "
              + ux.tint("dim", "p") + " provider   "
              + ux.tint("dim", "q") + " abort")
        while True:
            try:
                key = input(ux.tint("bold", "  ▶ ") + ux.tint("dim", "ready? ")).strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n" + ux.tint("dim", "Aborted."))
                return 1
            if key in ("", "y", "yes", "go", "launch"):
                break
            if key in ("q", "quit", "abort", "no"):
                print(ux.tint("dim", "  Scrubbed."))
                return 1
            if key in ("p", "provider"):
                provider = ux.pick("  Provider", PROVIDERS, provider, labels)
                continue
            print(ux.tint("warn", "  keys: Enter launch · p provider · q abort"))
    if provider not in available:
        print(f"error: provider {provider!r} is not available", file=sys.stderr)
        return 2
    orch = Orchestrator(_root(), cfg, on_event=_event_printer(args.verbose),
                        keep_worktrees=args.keep_worktrees or None)
    print(ux.tint("ok", f"  ∞  Running {provider}…"))
    print()
    manifest = orch.single(provider, prompt, profile,
                           isolate=not args.no_isolate)
    return _report_manifest(manifest)


def build_command(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="absoloop build")
    parser.add_argument("prompt")
    parser.add_argument("--strategy", default="race", choices=["race", "council"])
    parser.add_argument("--providers", default=None,
                        help="comma-separated provider list")
    parser.add_argument("--profile", default=None, choices=["read", "edit", "full"])
    parser.add_argument("--keep-worktrees", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    cfg = load_config(_root())
    providers = ([p.strip() for p in args.providers.split(",") if p.strip()]
                 if args.providers
                 else [str(p) for p in cfg.get("workflows", "implementers",
                                               default=list(PROVIDERS))])
    for provider in providers:
        if provider not in PROVIDERS:
            print(f"error: unknown provider {provider!r}", file=sys.stderr)
            return 2
    profile = args.profile or str(cfg.get("permissions", "default_profile",
                                          default="edit"))
    orch = Orchestrator(_root(), cfg, on_event=_event_printer(args.verbose),
                        keep_worktrees=args.keep_worktrees or None)
    workflow = orch.race if args.strategy == "race" else orch.council
    manifest = workflow(providers, args.prompt, profile)
    return _report_manifest(manifest)


def review_command(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="absoloop review")
    parser.add_argument("prompt")
    parser.add_argument("--implementer", required=True, choices=list(PROVIDERS))
    parser.add_argument("--reviewer", required=True, choices=list(PROVIDERS))
    parser.add_argument("--profile", default=None, choices=["read", "edit", "full"])
    parser.add_argument("--keep-worktrees", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    cfg = load_config(_root())
    profile = args.profile or str(cfg.get("permissions", "default_profile",
                                          default="edit"))
    orch = Orchestrator(_root(), cfg, on_event=_event_printer(args.verbose),
                        keep_worktrees=args.keep_worktrees or None)
    manifest = orch.review(args.implementer, args.reviewer, args.prompt, profile)
    return _report_manifest(manifest)


def harness_resume_command(argv: List[str]) -> Optional[int]:
    """`absoloop resume <run-id> "follow-up"` — continue a harness run's
    native provider session. Returns None when the argument is not a harness
    run id, so the legacy mission `resume` handles it."""
    if not argv:
        return None
    run_id = argv[0]
    store_dir = _root() / ".absoloop" / "runs" / run_id
    if not store_dir.is_dir():
        return None
    parser = argparse.ArgumentParser(prog="absoloop resume <run-id>")
    parser.add_argument("run_id")
    parser.add_argument("prompt", nargs="?", default="Continue the task.")
    parser.add_argument("--profile", default=None, choices=["read", "edit", "full"])
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    store = RunStore(_root(), run_id)
    manifest = store.read_manifest()
    selected = manifest.get("selected_candidate")
    candidates = manifest.get("candidates", [])
    target = next((c for c in candidates if c.get("role") == selected), None) \
        or (candidates[0] if candidates else None)
    if not target or not target.get("session_id"):
        print(f"error: run {run_id} has no resumable session", file=sys.stderr)
        return 2
    provider = target["provider"]
    cfg = load_config(_root())
    profile = args.profile or manifest.get("permission_profile", "edit")
    adapter = make_adapter(provider, cfg.get("providers", provider, default={}))
    session = SessionRef(provider=provider, native_id=target["session_id"])
    request = AgentRequest(prompt=args.prompt, cwd=str(_root()),
                           permission_profile=profile,
                           timeout_seconds=float(cfg.get(
                               "providers", provider, "timeout_seconds",
                               default=1800)))
    printer = _event_printer(args.verbose)
    failed = False
    for event in adapter.resume(session, request, run_id=run_id):
        store.append_event(event)
        printer(event)
        if event.type == EventType.RUN_FAILED:
            failed = True
    return 1 if failed else 0


def cancel_command(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="absoloop cancel")
    parser.add_argument("run_id")
    args = parser.parse_args(argv)
    store = RunStore(_root(), args.run_id)
    if not store.run_dir.is_dir():
        print(f"error: no harness run {args.run_id!r}", file=sys.stderr)
        return 2
    result = run_ctrl.cancel_run(store.run_dir)
    if not result.get("ok"):
        print(f"nothing to cancel: {result.get('message')}", file=sys.stderr)
        return 1
    for child in result.get("killed", []):
        state = ("was live" if child.get("was_alive") else "already gone")
        print(f"  killed {child.get('role')} pid={child.get('pid')} ({state})")
    if result.get("orchestrator_signaled"):
        print(f"  signaled orchestrator pid={result.get('orchestrator_pid')}")
    # Finalize the manifest so inspect shows cancelled even if the
    # orchestrator dies before writing its own wrap-up.
    manifest = store.read_manifest() or {"run_id": args.run_id}
    manifest["status"] = "cancelled"
    manifest["live"] = False
    manifest["selected_candidate"] = None
    manifest["cancel"] = {
        "requested_by_pid": os.getpid(),
        "orchestrator_pid": result.get("orchestrator_pid"),
        "children": result.get("killed", []),
    }
    store.write_manifest(manifest)
    store.write_summary(
        f"# Absoloop run — cancelled\n\n"
        f"Run `{args.run_id}` was cancelled via `absoloop cancel`.\n")
    print(f"cancelled run {args.run_id}")
    return 0


def inspect_command(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="absoloop inspect")
    parser.add_argument("run_id", nargs="?")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.run_id:
        runs = list_runs(_root())
        if not runs:
            print("no harness runs yet (.absoloop/runs/ is empty)")
            return 0
        for run_id in runs:
            store = RunStore(_root(), run_id)
            manifest = store.read_manifest()
            live = " LIVE" if run_ctrl.is_run_live(store.run_dir) else ""
            print(f"{run_id}  strategy={manifest.get('strategy', '?'):<8} "
                  f"status={manifest.get('status', '?'):<10} "
                  f"selected={manifest.get('selected_candidate')}{live}")
        return 0
    store = RunStore(_root(), args.run_id)
    manifest = store.read_manifest()
    if not manifest:
        print(f"error: no manifest for run {args.run_id}", file=sys.stderr)
        return 2
    if args.json:
        payload = dict(manifest)
        payload["live_state"] = run_ctrl.read_live(store.run_dir)
        print(json.dumps(payload, indent=2))
        return 0
    live = run_ctrl.is_run_live(store.run_dir)
    print(f"run {args.run_id} — strategy {manifest.get('strategy')}"
          f"{' (LIVE)' if live else ''}")
    print(f"status:   {manifest.get('status', '?')}")
    print(f"selected: {manifest.get('selected_candidate')}")
    print(f"profile:  {manifest.get('permission_profile')}")
    if live:
        live_state = run_ctrl.read_live(store.run_dir)
        print(f"orchestrator pid: {live_state.get('orchestrator_pid')}")
        for child in live_state.get("children", []):
            if isinstance(child, dict):
                print(f"  child {child.get('role')}: pid={child.get('pid')} "
                      f"pgid={child.get('pgid')}")
        print(f"cancel with: absoloop cancel {args.run_id}")
    for candidate in manifest.get("candidates", []):
        gates = ", ".join(f"{g['name']}:{'PASS' if g['passed'] else 'FAIL'}"
                          for g in candidate.get("gates", [])) or "-"
        print(f"  {candidate['role']:<12} {candidate['status']:<10} gates: {gates}")
    summary = store.run_dir / "summary.md"
    if summary.is_file():
        print(f"\nsummary: {summary}")
    return 0


def apply_command(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="absoloop apply")
    parser.add_argument("run_id")
    parser.add_argument("--candidate", default=None,
                        help="candidate role (default: the selected one)")
    args = parser.parse_args(argv)
    store = RunStore(_root(), args.run_id)
    manifest = store.read_manifest()
    if not manifest:
        print(f"error: no manifest for run {args.run_id}", file=sys.stderr)
        return 2
    role = args.candidate or manifest.get("selected_candidate")
    if not role:
        print("error: no candidate selected in this run; pass --candidate",
              file=sys.stderr)
        return 2
    patch = store.run_dir / "candidates" / role / "diff.patch"
    if not patch.is_file():
        print(f"error: no patch for candidate {role!r}", file=sys.stderr)
        return 2
    store.apply_patch(patch)
    print(f"applied {patch.relative_to(_root())} to the working tree "
          "(changes are unstaged — review and commit)")
    return 0


def config_command(argv: List[str]) -> int:
    cfg = load_config(_root())
    width = max((len(key) for key, _v, _s in cfg.flat()), default=20) + 2
    for key, value, source in cfg.flat():
        print(f"{key.ljust(width)} = {value!r:<40} # {source}")
    return 0


def _report_manifest(manifest: Dict[str, Any]) -> int:
    selected = manifest.get("selected_candidate")
    run_id = manifest.get("run_id")
    print(f"\nrun {run_id} finished — artifacts in .absoloop/runs/{run_id}/")
    if selected:
        print(f"selected candidate: {selected}")
        print(f"apply it with: absoloop apply {run_id}")
        return 0
    statuses = {c["role"]: c["status"] for c in manifest.get("candidates", [])}
    print(f"no candidate survived the gates ({statuses})")
    return 1


def dispatch(command: str, argv: List[str]) -> int:
    handlers = {
        "doctor": doctor_command,
        "providers": providers_command,
        "run": run_command,
        "build": build_command,
        "review": review_command,
        "cancel": cancel_command,
        "inspect": inspect_command,
        "apply": apply_command,
        "config": config_command,
    }
    return handlers[command](argv)
