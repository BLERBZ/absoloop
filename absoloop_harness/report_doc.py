"""Absoloop mission report — Markdown document + lite HTML viewer.

`absoloop report` regenerates `.absoloop/report.md` (source of truth) and
`.absoloop/report.html` (infographic-style lite viewer), then opens the
viewer in the default browser.
"""
from __future__ import annotations

import html
import json
import os
import pathlib
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

STATUS_LABELS = {
    "COMPLETED": ("Accepted", "ok"),
    "AWAITING_APPROVAL": ("Needs review", "warn"),
    "BUDGET_EXHAUSTED": ("Budget spent", "warn"),
    "BLOCKED": ("Blocked", "err"),
    "RUNNING": ("In progress", "accent"),
    "IDLE": ("Idle", "dim"),
}


@dataclass
class TimelineItem:
    ts: float
    kind: str
    title: str
    detail: str = ""
    tone: str = "neutral"  # ok | warn | err | accent | neutral


@dataclass
class MissionReport:
    project: pathlib.Path
    mission_id: str
    loop_id: str
    objective: str
    status: str
    stop_reason: str
    delivery_mode: str
    delivery_detail: str
    iteration: int
    max_iterations: int
    cost_usd: float
    max_cost_usd: float
    tokens_total: Any
    engine: str
    generated_at: float
    changed_files: List[str] = field(default_factory=list)
    timeline: List[TimelineItem] = field(default_factory=list)
    agent_summaries: List[str] = field(default_factory=list)
    critic_path: str = ""
    latest_agent_path: str = ""
    next_step: str = ""
    wall_seconds: float = 0.0
    max_wall_seconds: float = 0.0
    agent_runs: int = 0
    integrity_ok: Optional[bool] = None
    human_decision: str = ""

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, (self.status or "Unknown", "dim"))[0]

    @property
    def status_tone(self) -> str:
        return STATUS_LABELS.get(self.status, (self.status or "Unknown", "dim"))[1]


# ---------------------------------------------------------------------------
# Collect
# ---------------------------------------------------------------------------

def _read_json(path: pathlib.Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _iter_ledger(target: pathlib.Path) -> Iterable[dict]:
    path = target / ".absoloop" / "ledger.jsonl"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            yield event


def _fmt_tokens(tokens: Any) -> str:
    if tokens is None:
        return ""
    if isinstance(tokens, dict):
        total = tokens.get("total") or tokens.get("total_tokens")
        if total is not None:
            try:
                return f"{int(total):,} tok"
            except (TypeError, ValueError):
                pass
        inp = tokens.get("input") or tokens.get("input_tokens")
        out = tokens.get("output") or tokens.get("output_tokens")
        parts = []
        for label, val in (("in", inp), ("out", out)):
            if val is None:
                continue
            try:
                parts.append(f"{int(val):,} {label}")
            except (TypeError, ValueError):
                continue
        return " · ".join(parts)
    try:
        return f"{int(tokens):,} tok"
    except (TypeError, ValueError):
        return str(tokens)


def _agent_summary(target: pathlib.Path, result_rel: str) -> str:
    if not result_rel:
        return ""
    try:
        payload = json.loads((target / result_rel).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    structured = payload.get("structured_output")
    structured = structured if isinstance(structured, dict) else payload
    summary = structured.get("summary") or payload.get("result") or ""
    return " ".join(str(summary).split())


def _git_changed(target: pathlib.Path) -> List[str]:
    if not _which("git"):
        return []
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=target, text=True, capture_output=True, check=False,
        )
    except OSError:
        return []
    files: List[str] = []
    for line in (result.stdout or "").splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path and not path.startswith(".absoloop/"):
            files.append(path)
    return files


def _which(name: str) -> bool:
    from shutil import which
    return which(name) is not None


def _next_step(status: str) -> str:
    if status == "AWAITING_APPROVAL":
        return ("Review the diff, then `absoloop approve` — or "
                "`absoloop reject \"what to change\"` and `absoloop resume`.")
    if status == "COMPLETED":
        return ("Results were delivered per the mission delivery mode. "
                "`absoloop resume --extend` starts a follow-on run with fresh budgets.")
    if status == "BUDGET_EXHAUSTED":
        return ("Raise `max_iterations` / `max_cost_usd` / `max_wall_seconds` in "
                "`.absoloop/runtime.json`, then `absoloop resume`.")
    if status == "BLOCKED":
        return ("Inspect `stop_reason` and latest logs, fix the cause "
                "(or `absoloop reject \"guidance\"`), then `absoloop resume`.")
    return "`absoloop resume` continues the loop from saved state."


def _delivery_detail(delivery: dict) -> str:
    mode = delivery.get("mode") or "local"
    if mode == "git":
        return delivery.get("branch") or "absoloop/<loop>"
    if mode == "out":
        return str(delivery.get("out_dir") or "~/absoloop/out/<loop>")
    return "working tree (unstaged)"


def _timeline_from_ledger(target: pathlib.Path) -> Tuple[List[TimelineItem], dict]:
    items: List[TimelineItem] = []
    stats: Dict[str, Any] = {
        "agent_runs": 0,
        "wall_seconds": 0.0,
        "integrity_ok": None,
        "human_decision": "",
        "summaries": [],
    }
    for event in _iter_ledger(target):
        ts = float(event.get("ts") or 0)
        kind = event.get("type")
        if kind == "agent_run":
            stats["agent_runs"] += 1
            stats["wall_seconds"] += float(event.get("wall_seconds") or 0)
            cost = float(event.get("cost_usd") or 0)
            exact = "" if event.get("cost_is_exact") else "~"
            tokens = _fmt_tokens(event.get("tokens"))
            limit = f" · hit {event['limit_reached']}" if event.get("limit_reached") else ""
            exit_code = event.get("exit_code")
            tone = "ok" if exit_code == 0 else "warn"
            title = f"{event.get('engine', 'agent')} run"
            detail = (
                f"exit {exit_code} · {exact}${cost:.2f}"
                + (f" · {tokens}" if tokens else "")
                + f" · {float(event.get('wall_seconds') or 0):.0f}s"
                + limit
            )
            summary = _agent_summary(target, str(event.get("result") or ""))
            if summary:
                stats["summaries"].append(summary)
                detail = f"{detail}\n{summary}"
            items.append(TimelineItem(ts, kind, title, detail, tone))
        elif kind == "iteration":
            done = bool(event.get("done"))
            items.append(TimelineItem(
                ts, kind,
                f"Iteration {event.get('iteration')}",
                "Builder reports DONE" if done else "Still in progress",
                "ok" if done else "neutral",
            ))
        elif kind == "early_done_claim":
            items.append(TimelineItem(
                ts, kind, "Early done claim held",
                f"Iteration {event.get('iteration')} below floor "
                f"({event.get('min_iterations')})",
                "warn",
            ))
        elif kind == "integrity_check":
            ok = event.get("exit_code") == 0
            if not ok:
                stats["integrity_ok"] = False
            elif stats["integrity_ok"] is None:
                stats["integrity_ok"] = True
            items.append(TimelineItem(
                ts, kind, "Integrity check",
                "Passed" if ok else "Violation",
                "ok" if ok else "err",
            ))
        elif kind == "human_gate":
            decision = str(event.get("decision") or "")
            stats["human_decision"] = decision
            note = event.get("feedback") or event.get("note") or ""
            tone = "ok" if decision.lower() in ("approve", "approved") else "warn"
            items.append(TimelineItem(
                ts, kind, f"Human gate · {decision}",
                str(note), tone,
            ))
        elif kind == "delivery":
            items.append(TimelineItem(
                ts, kind, f"Delivered ({event.get('mode')})",
                str(event.get("detail") or ""), "accent",
            ))
        elif kind == "mission_stop":
            items.append(TimelineItem(
                ts, kind, f"Stop · {event.get('status')}",
                str(event.get("reason") or ""), "neutral",
            ))
        elif kind == "extension":
            note = event.get("note") or ""
            items.append(TimelineItem(
                ts, kind, "Mission extended",
                f"{event.get('previous_loop_id')} → {event.get('loop_id')}"
                + (f" — {note}" if note else ""),
                "accent",
            ))
    return items, stats


def collect_report(project: pathlib.Path) -> Optional[MissionReport]:
    """Build a MissionReport from `.absoloop/` state. None if no mission."""
    target = project.expanduser().resolve()
    abs_dir = target / ".absoloop"
    if not abs_dir.is_dir():
        return None
    state = _read_json(abs_dir / "state.json")
    runtime = _read_json(abs_dir / "runtime.json")
    if not state and not runtime:
        return None

    delivery = runtime.get("delivery") if isinstance(runtime.get("delivery"), dict) else {}
    timeline, stats = _timeline_from_ledger(target)
    status = str(state.get("status") or "IDLE")

    return MissionReport(
        project=target,
        mission_id=str(state.get("mission_id") or runtime.get("mission_id") or "unknown"),
        loop_id=str(runtime.get("loop_id") or "—"),
        objective=str(runtime.get("objective") or ""),
        status=status,
        stop_reason=str(state.get("stop_reason") or ""),
        delivery_mode=str(delivery.get("mode") or "local"),
        delivery_detail=_delivery_detail(delivery),
        iteration=int(state.get("iteration") or 0),
        max_iterations=int(runtime.get("max_iterations") or 0),
        cost_usd=float(state.get("cost_usd") or 0),
        max_cost_usd=float(runtime.get("max_cost_usd") or 0),
        tokens_total=state.get("tokens_total"),
        engine=str(runtime.get("engine") or runtime.get("builder") or "—"),
        generated_at=time.time(),
        changed_files=_git_changed(target),
        timeline=timeline,
        agent_summaries=list(stats.get("summaries") or []),
        critic_path=str(state.get("latest_critic_findings") or ""),
        latest_agent_path=str(state.get("latest_agent_result") or ""),
        next_step=_next_step(status),
        wall_seconds=float(stats.get("wall_seconds") or 0),
        max_wall_seconds=float(runtime.get("max_wall_seconds") or 0),
        agent_runs=int(stats.get("agent_runs") or 0),
        integrity_ok=stats.get("integrity_ok"),
        human_decision=str(stats.get("human_decision") or ""),
    )


# ---------------------------------------------------------------------------
# Markdown (source document)
# ---------------------------------------------------------------------------

def _pct(used: float, cap: float) -> float:
    if not cap:
        return 0.0
    return min(100.0, max(0.0, 100.0 * used / cap))


def _bar_md(used: float, cap: float, width: int = 20) -> str:
    if not cap:
        return ""
    frac = min(1.0, max(0.0, used / cap))
    filled = int(round(frac * width))
    return f"`[{'█' * filled}{'░' * (width - filled)}]` {100 * frac:.0f}%"


def _ts_md(ts: float) -> str:
    if not ts:
        return "—"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def render_markdown(report: MissionReport) -> str:
    """Infographic-oriented Markdown — readable raw, great in the lite viewer."""
    tokens = _fmt_tokens(report.tokens_total)
    gen = time.strftime("%Y-%m-%d %H:%M", time.localtime(report.generated_at))
    lines: List[str] = [
        f"# Absoloop Report",
        "",
        f"**{report.status_label}** · `{report.mission_id}` · loop `{report.loop_id}`",
        "",
        f"> Generated {gen}",
        "",
        "---",
        "",
        "## Mission",
        "",
        report.objective.strip() or "_(no objective recorded)_",
        "",
        "| | |",
        "|---|---|",
        f"| **Engine** | `{report.engine}` |",
        f"| **Delivery** | `{report.delivery_mode}` → {report.delivery_detail} |",
        f"| **Status** | **{report.status}**"
        + (f" ({report.stop_reason})" if report.stop_reason else "")
        + " |",
        "",
        "---",
        "",
        "## At a glance",
        "",
        "| Metric | Used | Budget | Progress |",
        "|---|---:|---:|---|",
        f"| Iterations | {report.iteration} | {report.max_iterations or '—'} | "
        f"{_bar_md(report.iteration, report.max_iterations)} |",
        f"| Spend | ${report.cost_usd:.2f}"
        + (f" ({tokens})" if tokens else "")
        + f" | ${report.max_cost_usd:.2f} | "
        f"{_bar_md(report.cost_usd, report.max_cost_usd)} |",
    ]
    if report.max_wall_seconds or report.wall_seconds:
        lines.append(
            f"| Agent wall | {report.wall_seconds:.0f}s | "
            f"{report.max_wall_seconds:.0f}s | "
            f"{_bar_md(report.wall_seconds, report.max_wall_seconds)} |"
        )
    lines += [
        f"| Agent runs | {report.agent_runs} | — | — |",
        "",
    ]

    # Snapshot chips as a short list (renders as pills in HTML)
    chips: List[str] = [f"`{report.status_label}`"]
    if report.integrity_ok is True:
        chips.append("`Integrity ✓`")
    elif report.integrity_ok is False:
        chips.append("`Integrity ✗`")
    if report.human_decision:
        chips.append(f"`Gate: {report.human_decision}`")
    if report.agent_runs:
        chips.append(f"`{report.agent_runs} runs`")
    lines += ["### Snapshot", "", " · ".join(chips), "", "---", "", "## Run arc", ""]

    if not report.timeline:
        lines.append("_No ledger events yet — the loop has not run._")
        lines.append("")
    else:
        for item in report.timeline:
            mark = {
                "ok": "✓", "warn": "!", "err": "✗", "accent": "◆", "neutral": "·",
            }.get(item.tone, "·")
            detail = item.detail.replace("\n", " — ") if item.detail else ""
            lines.append(f"- **{_ts_md(item.ts)}** {mark} **{item.title}**"
                         + (f" — {detail}" if detail else ""))
        lines.append("")

    if report.agent_summaries:
        lines += ["---", "", "## Builder highlights", ""]
        for i, summary in enumerate(report.agent_summaries[-5:], 1):
            lines.append(f"{i}. {summary}")
        lines.append("")

    lines += ["---", "", "## Changed files", ""]
    if report.changed_files:
        for path in report.changed_files:
            lines.append(f"- `{path}`")
    else:
        lines.append("_None detected (or clean tree)._")
    lines.append("")

    lines += ["---", "", "## Pointers", ""]
    if report.latest_agent_path:
        lines.append(f"- Latest agent result: `{report.latest_agent_path}`")
    if report.critic_path:
        lines.append(f"- Latest critic findings: `{report.critic_path}`")
    if not report.latest_agent_path and not report.critic_path:
        lines.append("_No saved agent/critic artifacts yet._")
    lines += [
        "",
        "---",
        "",
        "## Next",
        "",
        report.next_step,
        "",
        "---",
        "",
        f"_Absoloop · {report.project.name} · `{report.mission_id}`_",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML lite viewer (infographic)
# ---------------------------------------------------------------------------

_HTML_CSS = """
:root {
  --bg0: #0c1118;
  --bg1: #121a24;
  --bg2: #1a2533;
  --ink: #e8eef6;
  --muted: #8a9bb0;
  --line: rgba(255,255,255,0.08);
  --ok: #28cd78;
  --warn: #ff9114;
  --err: #ff195f;
  --accent: #00cde1;
  --gold: #ffbe0f;
  --blue: #0069ff;
  --card: rgba(255,255,255,0.03);
  --shadow: 0 18px 50px rgba(0,0,0,0.35);
  --radius: 18px;
  --font: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --mono: "IBM Plex Mono", "SF Mono", ui-monospace, monospace;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: var(--bg0); color: var(--ink); }
body {
  font-family: var(--font);
  line-height: 1.45;
  min-height: 100vh;
  background:
    radial-gradient(1100px 500px at 10% -10%, rgba(0,205,225,0.14), transparent 55%),
    radial-gradient(900px 420px at 95% 0%, rgba(40,205,120,0.10), transparent 50%),
    radial-gradient(700px 400px at 50% 100%, rgba(255,145,20,0.08), transparent 55%),
    var(--bg0);
}
.wrap { max-width: 880px; margin: 0 auto; padding: 32px 20px 64px; }
.hero {
  position: relative;
  overflow: hidden;
  border-radius: calc(var(--radius) + 4px);
  padding: 28px 28px 24px;
  background:
    linear-gradient(135deg, rgba(0,205,225,0.12), transparent 40%),
    linear-gradient(320deg, rgba(255,25,95,0.10), transparent 45%),
    var(--bg1);
  border: 1px solid var(--line);
  box-shadow: var(--shadow);
  margin-bottom: 22px;
}
.brand {
  display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
  letter-spacing: 0.04em; text-transform: uppercase;
  font-size: 12px; color: var(--muted); font-weight: 600;
}
.brand strong { color: var(--accent); font-size: 13px; letter-spacing: 0.12em; }
.status-pill {
  display: inline-flex; align-items: center; gap: 8px;
  margin-top: 14px; padding: 8px 14px; border-radius: 999px;
  font-weight: 700; font-size: 14px; letter-spacing: 0.02em;
  border: 1px solid transparent;
}
.status-pill.ok { background: rgba(40,205,120,0.15); color: var(--ok); border-color: rgba(40,205,120,0.35); }
.status-pill.warn { background: rgba(255,145,20,0.15); color: var(--warn); border-color: rgba(255,145,20,0.35); }
.status-pill.err { background: rgba(255,25,95,0.15); color: var(--err); border-color: rgba(255,25,95,0.35); }
.status-pill.accent { background: rgba(0,205,225,0.15); color: var(--accent); border-color: rgba(0,205,225,0.35); }
.status-pill.dim { background: rgba(255,255,255,0.06); color: var(--muted); border-color: var(--line); }
.hero h1 {
  margin: 12px 0 8px; font-size: clamp(1.55rem, 3.5vw, 2.1rem);
  font-weight: 750; letter-spacing: -0.02em; line-height: 1.2;
}
.meta { color: var(--muted); font-size: 13px; font-family: var(--mono); }
.meta code { color: var(--ink); }
.objective {
  margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--line);
  font-size: 1.05rem; max-width: 62ch;
}
.grid {
  display: grid; gap: 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-bottom: 22px;
}
@media (min-width: 720px) {
  .grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
.card {
  background: var(--card); border: 1px solid var(--line);
  border-radius: var(--radius); padding: 16px 16px 14px;
  backdrop-filter: blur(6px);
}
.card .label {
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--muted); font-weight: 650; margin-bottom: 6px;
}
.card .value {
  font-size: 1.45rem; font-weight: 750; letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}
.card .sub { margin-top: 4px; font-size: 12px; color: var(--muted); font-family: var(--mono); }
.bar {
  margin-top: 10px; height: 7px; border-radius: 999px;
  background: rgba(255,255,255,0.06); overflow: hidden;
}
.bar > i {
  display: block; height: 100%; border-radius: inherit;
  background: linear-gradient(90deg, var(--accent), var(--ok) 55%, var(--gold));
}
.bar.warn > i { background: linear-gradient(90deg, var(--warn), var(--err)); }
.section {
  background: var(--bg1); border: 1px solid var(--line);
  border-radius: var(--radius); padding: 22px 22px 18px;
  margin-bottom: 16px; box-shadow: var(--shadow);
}
.section h2 {
  margin: 0 0 14px; font-size: 13px; text-transform: uppercase;
  letter-spacing: 0.1em; color: var(--muted); font-weight: 700;
}
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 4px; }
.chip {
  font-size: 12px; font-weight: 650; padding: 6px 10px; border-radius: 999px;
  background: rgba(255,255,255,0.05); border: 1px solid var(--line); color: var(--ink);
}
.chip.ok { color: var(--ok); border-color: rgba(40,205,120,0.3); }
.chip.warn { color: var(--warn); border-color: rgba(255,145,20,0.3); }
.chip.err { color: var(--err); border-color: rgba(255,25,95,0.3); }
.chip.accent { color: var(--accent); border-color: rgba(0,205,225,0.3); }
.kv { display: grid; gap: 8px; }
.kv row, .kv .row {
  display: grid; grid-template-columns: 110px 1fr; gap: 10px;
  font-size: 14px; padding: 6px 0; border-bottom: 1px solid var(--line);
}
.kv .k { color: var(--muted); font-weight: 600; }
.kv .v { font-family: var(--mono); font-size: 13px; word-break: break-word; }
.timeline { list-style: none; margin: 0; padding: 0; }
.timeline li {
  position: relative; padding: 0 0 18px 22px;
  border-left: 2px solid rgba(255,255,255,0.08);
}
.timeline li:last-child { padding-bottom: 0; }
.timeline li::before {
  content: ""; position: absolute; left: -6px; top: 4px;
  width: 10px; height: 10px; border-radius: 50%;
  background: var(--muted); box-shadow: 0 0 0 3px rgba(18,26,36,0.9);
}
.timeline li.ok::before { background: var(--ok); }
.timeline li.warn::before { background: var(--warn); }
.timeline li.err::before { background: var(--err); }
.timeline li.accent::before { background: var(--accent); }
.t-time { font-family: var(--mono); font-size: 11px; color: var(--muted); }
.t-title { font-weight: 700; margin-top: 2px; }
.t-detail { color: var(--muted); font-size: 13px; margin-top: 3px; white-space: pre-wrap; }
.files { columns: 1; gap: 8px; }
@media (min-width: 640px) { .files { columns: 2; } }
.files code {
  display: block; break-inside: avoid; font-family: var(--mono);
  font-size: 12px; padding: 6px 8px; margin-bottom: 6px;
  background: rgba(255,255,255,0.03); border-radius: 8px;
  border: 1px solid var(--line); color: #c9d7e8;
}
.next {
  border-left: 3px solid var(--accent);
  padding: 4px 0 4px 14px; font-size: 15px;
}
.footer {
  margin-top: 10px; text-align: center; color: var(--muted);
  font-size: 12px; font-family: var(--mono);
}
.highlights { margin: 0; padding-left: 18px; }
.highlights li { margin: 0 0 8px; color: #d5e0ec; }
.empty { color: var(--muted); font-style: italic; }
"""


def _esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def _bar_html(used: float, cap: float) -> str:
    pct = _pct(used, cap)
    warn = " warn" if pct >= 90 else ""
    return f'<div class="bar{warn}"><i style="width:{pct:.1f}%"></i></div>'


def render_html(report: MissionReport) -> str:
    tokens = _fmt_tokens(report.tokens_total)
    gen = time.strftime("%Y-%m-%d %H:%M", time.localtime(report.generated_at))
    title = f"Absoloop Report · {report.mission_id}"

    chips: List[str] = [
        f'<span class="chip {report.status_tone}">{_esc(report.status_label)}</span>',
        f'<span class="chip">{_esc(report.engine)}</span>',
        f'<span class="chip">{_esc(report.delivery_mode)}</span>',
    ]
    if report.integrity_ok is True:
        chips.append('<span class="chip ok">Integrity ✓</span>')
    elif report.integrity_ok is False:
        chips.append('<span class="chip err">Integrity ✗</span>')
    if report.human_decision:
        chips.append(f'<span class="chip">{_esc("Gate: " + report.human_decision)}</span>')
    if report.agent_runs:
        chips.append(f'<span class="chip accent">{report.agent_runs} agent runs</span>')

    timeline_html: List[str] = []
    if not report.timeline:
        timeline_html.append('<p class="empty">No ledger events yet — the loop has not run.</p>')
    else:
        timeline_html.append('<ol class="timeline">')
        for item in report.timeline:
            timeline_html.append(
                f'<li class="{_esc(item.tone)}">'
                f'<div class="t-time">{_esc(_ts_md(item.ts))}</div>'
                f'<div class="t-title">{_esc(item.title)}</div>'
                + (f'<div class="t-detail">{_esc(item.detail)}</div>' if item.detail else "")
                + "</li>"
            )
        timeline_html.append("</ol>")

    files_html: List[str] = []
    if report.changed_files:
        files_html.append('<div class="files">')
        for path in report.changed_files:
            files_html.append(f"<code>{_esc(path)}</code>")
        files_html.append("</div>")
    else:
        files_html.append('<p class="empty">None detected (or clean tree).</p>')

    highlights = ""
    if report.agent_summaries:
        items = "".join(f"<li>{_esc(s)}</li>" for s in report.agent_summaries[-5:])
        highlights = (
            '<section class="section"><h2>Builder highlights</h2>'
            f'<ol class="highlights">{items}</ol></section>'
        )

    stop = f" · {_esc(report.stop_reason)}" if report.stop_reason else ""
    spend_sub = f"of ${_esc(f'{report.max_cost_usd:.2f}')}"
    if tokens:
        spend_sub = f"{_esc(tokens)} · {spend_sub}"

    body = f"""
<div class="wrap">
  <header class="hero">
    <div class="brand"><strong>Absoloop</strong><span>mission report</span></div>
    <div class="status-pill {report.status_tone}">{_esc(report.status_label)}</div>
    <h1>{_esc(report.project.name)}</h1>
    <div class="meta">
      <code>{_esc(report.mission_id)}</code> · loop <code>{_esc(report.loop_id)}</code>
      · {_esc(gen)}{stop}
    </div>
    <div class="objective">{_esc(report.objective or "No objective recorded.")}</div>
  </header>

  <div class="grid">
    <div class="card">
      <div class="label">Iterations</div>
      <div class="value">{report.iteration}<span style="color:var(--muted);font-size:1rem"> / {report.max_iterations or "—"}</span></div>
      {_bar_html(report.iteration, report.max_iterations)}
    </div>
    <div class="card">
      <div class="label">Spend</div>
      <div class="value">${report.cost_usd:.2f}</div>
      <div class="sub">{spend_sub}</div>
      {_bar_html(report.cost_usd, report.max_cost_usd)}
    </div>
    <div class="card">
      <div class="label">Agent wall</div>
      <div class="value">{report.wall_seconds:.0f}s</div>
      <div class="sub">budget {report.max_wall_seconds:.0f}s</div>
      {_bar_html(report.wall_seconds, report.max_wall_seconds)}
    </div>
    <div class="card">
      <div class="label">Delivery</div>
      <div class="value" style="font-size:1.15rem">{_esc(report.delivery_mode)}</div>
      <div class="sub">{_esc(report.delivery_detail)}</div>
    </div>
  </div>

  <section class="section">
    <h2>Snapshot</h2>
    <div class="chips">{"".join(chips)}</div>
    <div class="kv" style="margin-top:14px">
      <div class="row"><div class="k">Engine</div><div class="v">{_esc(report.engine)}</div></div>
      <div class="row"><div class="k">Status</div><div class="v">{_esc(report.status)}{_esc(" (" + report.stop_reason + ")" if report.stop_reason else "")}</div></div>
      <div class="row"><div class="k">Project</div><div class="v">{_esc(str(report.project))}</div></div>
    </div>
  </section>

  <section class="section">
    <h2>Run arc</h2>
    {"".join(timeline_html)}
  </section>

  {highlights}

  <section class="section">
    <h2>Changed files</h2>
    {"".join(files_html)}
  </section>

  <section class="section">
    <h2>Next</h2>
    <div class="next">{_esc(report.next_step)}</div>
  </section>

  <p class="footer">Absoloop report · source <code>report.md</code> · viewer <code>report.html</code></p>
</div>
"""
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{_esc(title)}</title>\n"
        "<style>\n" + _HTML_CSS + "\n</style>\n"
        "</head>\n<body>\n" + body + "\n</body>\n</html>\n"
    )


# ---------------------------------------------------------------------------
# Terminal lite preview (optional)
# ---------------------------------------------------------------------------

def render_terminal(report: MissionReport, *, color: bool = True) -> str:
    use = color and sys_stdout_tty() and not os.environ.get("NO_COLOR")
    c = {
        "reset": "\x1b[0m" if use else "",
        "bold": "\x1b[1m" if use else "",
        "dim": "\x1b[2m" if use else "",
        "cyan": "\x1b[38;2;0;205;225m" if use else "",
        "green": "\x1b[38;2;40;205;120m" if use else "",
        "gold": "\x1b[38;2;255;190;15m" if use else "",
        "orange": "\x1b[38;2;255;145;20m" if use else "",
        "pink": "\x1b[38;2;255;25;95m" if use else "",
    }
    tone_color = {
        "ok": c["green"], "warn": c["orange"], "err": c["pink"],
        "accent": c["cyan"], "dim": c["dim"],
    }.get(report.status_tone, c["cyan"])

    w = 64
    lines = [
        f"{c['cyan']}{'═' * w}{c['reset']}",
        f"{c['bold']} ABSOLOOP REPORT{c['reset']}  "
        f"{tone_color}{report.status_label}{c['reset']}",
        f"{c['dim']} {report.mission_id} · {report.loop_id}{c['reset']}",
        f"{c['cyan']}{'─' * w}{c['reset']}",
    ]
    if report.objective:
        lines.append(f" {report.objective[: w - 2]}")
        lines.append(f"{c['cyan']}{'─' * w}{c['reset']}")
    tokens = _fmt_tokens(report.tokens_total)
    lines += [
        f" iterations  {report.iteration}/{report.max_iterations or '—'}  "
        f"{_bar_md(report.iteration, report.max_iterations).replace('`', '')}",
        f" spend       ${report.cost_usd:.2f}"
        + (f" ({tokens})" if tokens else "")
        + f" / ${report.max_cost_usd:.2f}  "
        + _bar_md(report.cost_usd, report.max_cost_usd).replace("`", ""),
        f" delivery    {report.delivery_mode} → {report.delivery_detail}",
        f" engine      {report.engine}",
        f"{c['cyan']}{'─' * w}{c['reset']}",
        f"{c['bold']} run arc{c['reset']}",
    ]
    if not report.timeline:
        lines.append(" (no ledger yet)")
    else:
        for item in report.timeline[-12:]:
            mark = {"ok": "✓", "warn": "!", "err": "✗", "accent": "◆"}.get(item.tone, "·")
            detail = item.detail.split("\n", 1)[0] if item.detail else ""
            lines.append(f"  {_ts_md(item.ts)[5:]}  {mark} {item.title}"
                         + (f" — {detail[:48]}" if detail else ""))
    lines += [
        f"{c['cyan']}{'─' * w}{c['reset']}",
        f" next: {report.next_step}",
        f"{c['cyan']}{'═' * w}{c['reset']}",
    ]
    return "\n".join(lines)


def sys_stdout_tty() -> bool:
    import sys
    return bool(sys.stdout.isatty())


# ---------------------------------------------------------------------------
# Write + open
# ---------------------------------------------------------------------------

@dataclass
class WrittenReport:
    markdown_path: pathlib.Path
    html_path: pathlib.Path
    report: MissionReport


def write_report_docs(
    project: pathlib.Path,
    *,
    write_html: bool = True,
) -> Optional[WrittenReport]:
    """Regenerate report.md (+ report.html) under `.absoloop/`. None if no mission."""
    report = collect_report(project)
    if report is None:
        return None
    abs_dir = report.project / ".absoloop"
    abs_dir.mkdir(parents=True, exist_ok=True)
    md_path = abs_dir / "report.md"
    html_path = abs_dir / "report.html"
    md_path.write_text(render_markdown(report), encoding="utf-8")
    if write_html:
        html_path.write_text(render_html(report), encoding="utf-8")
    return WrittenReport(md_path, html_path, report)


def open_viewer(html_path: pathlib.Path) -> bool:
    """Open the lite HTML viewer with the platform default handler."""
    from .platform_util import open_path
    return open_path(pathlib.Path(html_path))
