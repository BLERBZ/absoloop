"""AbsoLoop mission report — Markdown document + lite HTML viewer.

`absoloop report` regenerates `.absoloop/report.md` (source of truth) and
`.absoloop/report.html` (infographic-style lite viewer), then opens the
viewer in the default browser.
"""
from __future__ import annotations

import base64
import html
import json
import os
import pathlib
import re
import subprocess
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

BRAND_NAME = "AbsoLoop"
_LOGO_MARK_REL = pathlib.Path("docs") / "assets" / "absoloop-logo-mark.png"
_ITER_RE = re.compile(r"iteration-(\d+)", re.IGNORECASE)
_SKILL_RE = re.compile(
    r"^\.(claude|codex|agents)/skills/([^/]+)",
    re.IGNORECASE,
)

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
    meta: str = ""  # compact metrics / status chips


@dataclass
class AgentHighlight:
    """One builder or critic report, parsed from structured agent output."""
    ts: float
    role: str  # builder | critic
    iteration: Optional[int]
    engine: str
    headline: str
    summary: str
    status_label: str
    tone: str
    done: Optional[bool] = None
    recommendation: str = ""
    artifacts: List[str] = field(default_factory=list)
    commands: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    blocking_findings: List[str] = field(default_factory=list)
    cost_usd: float = 0.0
    cost_exact: bool = True
    wall_seconds: float = 0.0
    tokens_label: str = ""
    result_path: str = ""
    exit_code: Optional[int] = None
    limit_reached: str = ""


@dataclass
class SkillEntry:
    name: str
    engines: List[str] = field(default_factory=list)
    paths: List[str] = field(default_factory=list)


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
    skills: List[SkillEntry] = field(default_factory=list)
    timeline: List[TimelineItem] = field(default_factory=list)
    highlights: List[AgentHighlight] = field(default_factory=list)
    agent_summaries: List[str] = field(default_factory=list)  # legacy: headlines
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


def _as_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = " ".join(value.split())
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        out: List[str] = []
        for item in value:
            text = " ".join(str(item).split())
            if text:
                out.append(text)
        return out
    text = " ".join(str(value).split())
    return [text] if text else []


def _headline(summary: str, *, max_len: int = 160) -> str:
    text = " ".join(str(summary or "").split())
    if not text:
        return ""
    for sep in (". ", "! ", "? "):
        if sep in text:
            first = text.split(sep, 1)[0].strip()
            if len(first) >= 28:
                text = first + sep.strip()
                break
    if len(text) > max_len:
        cut = text[: max_len - 1]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        text = cut.rstrip(" ,;:") + "…"
    return text


def _role_and_iteration(result_rel: str) -> Tuple[str, Optional[int]]:
    name = pathlib.Path(result_rel or "").name.lower()
    role = "critic" if "critic" in name else "builder"
    match = _ITER_RE.search(result_rel or "")
    iteration = int(match.group(1)) if match else None
    return role, iteration


def _parse_json_maybe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "{[":
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _load_agent_structured(
    target: pathlib.Path, result_rel: str,
) -> Tuple[dict, dict]:
    """Return (structured fields, raw payload). Empty dicts when missing."""
    if not result_rel:
        return {}, {}
    path = target / result_rel
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, {}
    if not isinstance(payload, dict):
        return {}, {}

    structured = _parse_json_maybe(payload.get("structured_output"))
    if not isinstance(structured, dict):
        structured = {}
    if not structured:
        nested = _parse_json_maybe(payload.get("result"))
        if isinstance(nested, dict) and (
            "summary" in nested or "recommendation" in nested or "done" in nested
        ):
            structured = nested

    errors = payload.get("errors")
    if isinstance(errors, list):
        error_text = "; ".join(str(e) for e in errors if e)
    else:
        error_text = str(errors or "").strip()

    summary = structured.get("summary")
    if summary is None and isinstance(payload.get("result"), str):
        raw_result = payload["result"].strip()
        if raw_result and not raw_result.startswith("{"):
            summary = raw_result

    return {
        "summary": " ".join(str(summary or "").split()),
        "done": structured.get("done") if isinstance(structured.get("done"), bool) else None,
        "changed_artifacts": _as_str_list(structured.get("changed_artifacts")),
        "commands_run": _as_str_list(structured.get("commands_run")),
        "risks": _as_str_list(structured.get("risks")),
        "recommendation": str(structured.get("recommendation") or "").strip().upper(),
        "blocking_findings": _as_str_list(structured.get("blocking_findings")),
        "is_error": bool(payload.get("is_error")),
        "errors": error_text,
        "num_turns": payload.get("num_turns"),
    }, payload


def _builder_status(
    *,
    exit_code: Any,
    limit_reached: Any,
    done: Optional[bool],
    is_error: bool,
    errors: str,
) -> Tuple[str, str]:
    """Return (status_label, tone) for a builder run."""
    if limit_reached:
        label = str(limit_reached).replace("error_", "").replace("_", " ")
        return f"Failed · {label}", "warn"
    if exit_code not in (0, None) or is_error:
        detail = errors or f"exit {exit_code}"
        return f"Failed · {detail}", "err" if exit_code not in (0, None) else "warn"
    if done is True:
        return "Done claimed", "ok"
    if done is False:
        return "In progress", "accent"
    return "Completed run", "ok"


def _critic_status(recommendation: str, exit_code: Any) -> Tuple[str, str]:
    rec = (recommendation or "").upper()
    if rec == "PASS":
        return "PASS", "ok"
    if rec == "HOLD":
        return "HOLD", "warn"
    if rec == "REJECT":
        return "REJECT", "err"
    if exit_code not in (0, None):
        return f"Unreadable · exit {exit_code}", "err"
    return (rec or "Reviewed"), "accent" if rec else "neutral"


def _git_changed_paths(target: pathlib.Path) -> List[str]:
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


def _split_files_and_skills(
    paths: Sequence[str],
) -> Tuple[List[str], List[SkillEntry]]:
    files: List[str] = []
    grouped: Dict[str, SkillEntry] = {}
    for path in paths:
        match = _SKILL_RE.match(path.replace("\\", "/"))
        if not match:
            files.append(path)
            continue
        engine = match.group(1).lower()
        if engine == "agents":
            engine = "agents"
        name = match.group(2)
        entry = grouped.get(name)
        if entry is None:
            entry = SkillEntry(name=name)
            grouped[name] = entry
        if engine not in entry.engines:
            entry.engines.append(engine)
        if path not in entry.paths:
            entry.paths.append(path)
    skills = sorted(grouped.values(), key=lambda s: s.name.lower())
    return files, skills


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


def _metrics_line(
    *,
    cost_usd: float,
    cost_exact: bool,
    tokens_label: str,
    wall_seconds: float,
    exit_code: Any = None,
    limit_reached: Any = None,
    num_turns: Any = None,
) -> str:
    exact = "" if cost_exact else "~"
    parts = [f"{exact}${cost_usd:.2f}"]
    if tokens_label:
        parts.append(tokens_label)
    parts.append(f"{wall_seconds:.0f}s")
    if isinstance(num_turns, int):
        parts.append(f"{num_turns} turns")
    if exit_code not in (0, None):
        parts.append(f"exit {exit_code}")
    if limit_reached:
        parts.append(f"hit {limit_reached}")
    return " · ".join(parts)


def _timeline_from_ledger(
    target: pathlib.Path,
) -> Tuple[List[TimelineItem], List[AgentHighlight], dict]:
    items: List[TimelineItem] = []
    highlights: List[AgentHighlight] = []
    stats: Dict[str, Any] = {
        "agent_runs": 0,
        "wall_seconds": 0.0,
        "integrity_ok": None,
        "human_decision": "",
        "summaries": [],
        "builder_iters": set(),
    }

    for event in _iter_ledger(target):
        ts = float(event.get("ts") or 0)
        kind = event.get("type")

        if kind == "agent_run":
            stats["agent_runs"] += 1
            wall = float(event.get("wall_seconds") or 0)
            stats["wall_seconds"] += wall
            cost = float(event.get("cost_usd") or 0)
            cost_exact = bool(event.get("cost_is_exact", True))
            tokens_label = _fmt_tokens(event.get("tokens"))
            exit_code = event.get("exit_code")
            limit_reached = event.get("limit_reached") or ""
            engine = str(event.get("engine") or "agent")
            result_rel = str(event.get("result") or "")
            role, iteration = _role_and_iteration(result_rel)
            structured, _payload = _load_agent_structured(target, result_rel)

            if role == "builder":
                status_label, tone = _builder_status(
                    exit_code=exit_code,
                    limit_reached=limit_reached,
                    done=structured.get("done"),
                    is_error=bool(structured.get("is_error")),
                    errors=str(structured.get("errors") or ""),
                )
                if iteration is not None:
                    stats["builder_iters"].add(iteration)
            else:
                status_label, tone = _critic_status(
                    str(structured.get("recommendation") or ""), exit_code,
                )

            headline = _headline(str(structured.get("summary") or ""))
            if not headline and structured.get("errors"):
                headline = _headline(str(structured.get("errors")))
            if not headline and limit_reached:
                headline = f"Run stopped early ({limit_reached})."
            if not headline and exit_code not in (0, None):
                headline = f"Agent exited with code {exit_code}."

            iter_label = f"Iteration {iteration}" if iteration is not None else "Agent"
            role_label = "Builder" if role == "builder" else "Critic"
            title = f"{iter_label} · {role_label}"
            if status_label:
                title = f"{title} · {status_label}"

            meta = _metrics_line(
                cost_usd=cost,
                cost_exact=cost_exact,
                tokens_label=tokens_label,
                wall_seconds=wall,
                exit_code=exit_code,
                limit_reached=limit_reached,
                num_turns=structured.get("num_turns"),
            )
            detail_bits = [f"{engine} · {meta}"]
            if headline:
                detail_bits.append(headline)
            items.append(TimelineItem(
                ts, role, title, "\n".join(detail_bits), tone, meta,
            ))

            highlight = AgentHighlight(
                ts=ts,
                role=role,
                iteration=iteration,
                engine=engine,
                headline=headline or status_label,
                summary=str(structured.get("summary") or ""),
                status_label=status_label,
                tone=tone,
                done=structured.get("done"),
                recommendation=str(structured.get("recommendation") or ""),
                artifacts=list(structured.get("changed_artifacts") or []),
                commands=list(structured.get("commands_run") or []),
                risks=list(structured.get("risks") or []),
                blocking_findings=list(structured.get("blocking_findings") or []),
                cost_usd=cost,
                cost_exact=cost_exact,
                wall_seconds=wall,
                tokens_label=tokens_label,
                result_path=result_rel,
                exit_code=int(exit_code) if isinstance(exit_code, int) else None,
                limit_reached=str(limit_reached or ""),
            )
            highlights.append(highlight)
            if highlight.headline:
                stats["summaries"].append(highlight.headline)

        elif kind == "iteration":
            # Builder agent_run already carries the rich arc entry; only keep
            # a compact done marker when we somehow lack that run.
            iteration = event.get("iteration")
            done = bool(event.get("done"))
            if iteration in stats["builder_iters"]:
                continue
            items.append(TimelineItem(
                ts, kind,
                f"Iteration {iteration} · {'Done claimed' if done else 'Recorded'}",
                "Builder reports DONE" if done else "No builder artifact linked",
                "ok" if done else "neutral",
            ))

        elif kind == "bounded_agent_failure":
            # Duplicate of agent_run failure signals — skip unless isolated.
            iteration = event.get("iteration")
            if iteration in stats["builder_iters"]:
                continue
            limit = event.get("limit_reached") or f"exit {event.get('exit_code')}"
            items.append(TimelineItem(
                ts, kind,
                f"Iteration {iteration} · Builder · Failed",
                str(limit), "warn",
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

        elif kind == "schedule_due":
            items.append(TimelineItem(
                ts, kind,
                f"Schedule · {event.get('schedule_id') or 'due'}",
                str(event.get("action") or event.get("detail") or ""),
                "accent",
            ))

    return items, highlights, stats


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
    timeline, highlights, stats = _timeline_from_ledger(target)
    status = str(state.get("status") or "IDLE")
    changed_files, skills = _split_files_and_skills(_git_changed_paths(target))

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
        changed_files=changed_files,
        skills=skills,
        timeline=timeline,
        highlights=highlights,
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


def _render_arc_markdown(report: MissionReport) -> List[str]:
    if not report.timeline:
        return ["_No ledger events yet — the loop has not run._", ""]
    lines: List[str] = []
    for item in report.timeline:
        mark = {
            "ok": "✓", "warn": "!", "err": "✗", "accent": "◆", "neutral": "·",
        }.get(item.tone, "·")
        lines.append(f"- **{_ts_md(item.ts)}** {mark} **{item.title}**")
        if item.detail:
            for part in item.detail.split("\n"):
                part = part.strip()
                if part:
                    lines.append(f"  - {part}")
    lines.append("")
    return lines


def _highlight_heading(hl: AgentHighlight) -> str:
    iter_label = f"Iteration {hl.iteration}" if hl.iteration is not None else "Run"
    role = "Builder" if hl.role == "builder" else "Critic"
    return f"{iter_label} · {role} · {hl.status_label}"


def _render_highlights_markdown(report: MissionReport) -> List[str]:
    if not report.highlights:
        return ["_No builder/critic reports recorded yet._", ""]
    lines: List[str] = []
    for hl in report.highlights:
        lines.append(f"### {_highlight_heading(hl)}")
        lines.append("")
        exact = "" if hl.cost_exact else "~"
        meta = (
            f"`{hl.engine}` · {exact}${hl.cost_usd:.2f}"
            + (f" · {hl.tokens_label}" if hl.tokens_label else "")
            + f" · {hl.wall_seconds:.0f}s"
        )
        if hl.result_path:
            meta += f" · `{hl.result_path}`"
        lines.append(meta)
        lines.append("")
        if hl.headline:
            lines.append(f"**{hl.headline}**")
            lines.append("")
        if hl.summary and hl.summary != hl.headline:
            lines.append(hl.summary)
            lines.append("")
        if hl.role == "critic":
            if hl.recommendation:
                lines.append(f"- **Verdict:** `{hl.recommendation}`")
            if hl.blocking_findings:
                lines.append("- **Blocking findings:**")
                for finding in hl.blocking_findings:
                    lines.append(f"  - {finding}")
            elif hl.recommendation == "PASS":
                lines.append("- **Blocking findings:** none")
        else:
            if hl.done is True:
                lines.append("- **Done claim:** yes")
            elif hl.done is False:
                lines.append("- **Done claim:** no — work remains")
            if hl.limit_reached:
                lines.append(f"- **Limit:** `{hl.limit_reached}`")
        if hl.artifacts:
            lines.append("- **Artifacts:**")
            for path in hl.artifacts[:12]:
                lines.append(f"  - `{path}`")
            if len(hl.artifacts) > 12:
                lines.append(f"  - _+{len(hl.artifacts) - 12} more_")
        if hl.commands:
            lines.append("- **Verified commands:**")
            for cmd in hl.commands[:10]:
                lines.append(f"  - `{cmd}`")
            if len(hl.commands) > 10:
                lines.append(f"  - _+{len(hl.commands) - 10} more_")
        if hl.risks:
            lines.append("- **Risks / remaining:**")
            for risk in hl.risks[:8]:
                lines.append(f"  - {risk}")
            if len(hl.risks) > 8:
                lines.append(f"  - _+{len(hl.risks) - 8} more_")
        lines.append("")
    return lines


def render_markdown(report: MissionReport) -> str:
    """Infographic-oriented Markdown — readable raw, great in the lite viewer."""
    tokens = _fmt_tokens(report.tokens_total)
    gen = time.strftime("%Y-%m-%d %H:%M", time.localtime(report.generated_at))
    lines: List[str] = [
        f"# {BRAND_NAME} Report",
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
    lines += _render_arc_markdown(report)
    lines += ["---", "", "## Builder highlights", ""]
    lines += _render_highlights_markdown(report)
    lines += ["---", "", "## Changed files", ""]
    if report.changed_files:
        for path in report.changed_files:
            lines.append(f"- `{path}`")
    else:
        lines.append("_None detected (or clean tree)._")
    lines.append("")

    lines += ["---", "", "## Skills", ""]
    if report.skills:
        for skill in report.skills:
            engines = ", ".join(skill.engines) if skill.engines else "—"
            lines.append(f"- `{skill.name}` · {engines}")
            for path in skill.paths[:4]:
                lines.append(f"  - `{path}`")
            if len(skill.paths) > 4:
                lines.append(f"  - _+{len(skill.paths) - 4} more paths_")
    else:
        lines.append("_No skill tree changes detected._")
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
        f"_{BRAND_NAME} · {report.project.name} · `{report.mission_id}`_",
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
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
}
.brand-logo {
  display: block; height: 44px; width: auto;
  flex: 0 0 auto;
}
.brand-copy {
  display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
  letter-spacing: 0.04em; font-size: 12px; color: var(--muted); font-weight: 600;
}
.brand-copy strong {
  color: var(--ink); font-size: 15px; letter-spacing: -0.01em;
  font-weight: 750; text-transform: none;
}
.brand-copy span { text-transform: uppercase; letter-spacing: 0.1em; }
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
.t-meta {
  margin-top: 4px; font-family: var(--mono); font-size: 11px; color: var(--muted);
}
.t-detail { color: #c5d2e0; font-size: 13px; margin-top: 4px; line-height: 1.45; }
.files { columns: 1; gap: 8px; }
@media (min-width: 640px) { .files { columns: 2; } }
.files code, .skill-paths code {
  display: block; break-inside: avoid; font-family: var(--mono);
  font-size: 12px; padding: 6px 8px; margin-bottom: 6px;
  background: rgba(255,255,255,0.03); border-radius: 8px;
  border: 1px solid var(--line); color: #c9d7e8;
}
.skill-list { display: grid; gap: 12px; }
.skill-item {
  padding: 12px 14px; border-radius: 10px;
  background: rgba(255,255,255,0.03); border: 1px solid var(--line);
}
.skill-item .name { font-weight: 700; margin-bottom: 4px; }
.skill-item .engines { font-size: 12px; color: var(--muted); font-family: var(--mono); }
.next {
  border-left: 3px solid var(--accent);
  padding: 4px 0 4px 14px; font-size: 15px;
}
.footer {
  margin-top: 10px; text-align: center; color: var(--muted);
  font-size: 12px; font-family: var(--mono);
}
.hl-list { display: grid; gap: 14px; }
.hl-card {
  padding: 16px 16px 14px; border-radius: 12px;
  background: rgba(255,255,255,0.03); border: 1px solid var(--line);
}
.hl-card.ok { border-color: rgba(40,205,120,0.28); }
.hl-card.warn { border-color: rgba(255,145,20,0.28); }
.hl-card.err { border-color: rgba(255,25,95,0.28); }
.hl-card.accent { border-color: rgba(0,205,225,0.28); }
.hl-head {
  display: flex; flex-wrap: wrap; gap: 8px 12px;
  align-items: baseline; justify-content: space-between;
}
.hl-title { font-weight: 750; font-size: 15px; }
.hl-meta { font-family: var(--mono); font-size: 11px; color: var(--muted); }
.hl-headline {
  margin-top: 10px; font-size: 14px; color: #e7eef7; line-height: 1.45;
}
.hl-summary {
  margin-top: 8px; font-size: 13px; color: var(--muted); line-height: 1.5;
}
.hl-block { margin-top: 12px; }
.hl-block h3 {
  margin: 0 0 6px; font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.08em; color: var(--muted); font-weight: 700;
}
.hl-block ul { margin: 0; padding-left: 18px; }
.hl-block li { margin: 0 0 4px; font-size: 13px; color: #d5e0ec; }
.hl-block code {
  font-family: var(--mono); font-size: 12px; color: #c9d7e8;
}
.empty { color: var(--muted); font-style: italic; }
"""


def _esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


@lru_cache(maxsize=1)
def _brand_logo_data_uri() -> str:
    """Embed the HQ infinity mark so file:// report.html stays self-contained."""
    from .platform_util import tooling_home

    path = tooling_home() / _LOGO_MARK_REL
    if not path.is_file():
        # Package-relative fallback when ABSOLOOP_HOME points elsewhere.
        alt = pathlib.Path(__file__).resolve().parent.parent / _LOGO_MARK_REL
        path = alt if alt.is_file() else path
    if not path.is_file():
        return ""
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    return "data:image/png;base64," + base64.standard_b64encode(raw).decode("ascii")


def _brand_html() -> str:
    uri = _brand_logo_data_uri()
    logo = (
        f'<img class="brand-logo" src="{uri}" alt="{_esc(BRAND_NAME)}" width="160" height="70">'
        if uri else ""
    )
    return (
        f'<div class="brand">{logo}'
        f'<div class="brand-copy"><strong>{_esc(BRAND_NAME)}</strong>'
        f'<span>mission report</span></div></div>'
    )


def _bar_html(used: float, cap: float) -> str:
    pct = _pct(used, cap)
    warn = " warn" if pct >= 90 else ""
    return f'<div class="bar{warn}"><i style="width:{pct:.1f}%"></i></div>'


def _render_arc_html(report: MissionReport) -> str:
    if not report.timeline:
        return '<p class="empty">No ledger events yet — the loop has not run.</p>'
    parts = ['<ol class="timeline">']
    for item in report.timeline:
        detail_lines = [ln.strip() for ln in item.detail.split("\n") if ln.strip()]
        meta = ""
        headline = ""
        if detail_lines:
            meta = detail_lines[0]
            if len(detail_lines) > 1:
                headline = detail_lines[1]
        parts.append(
            f'<li class="{_esc(item.tone)}">'
            f'<div class="t-time">{_esc(_ts_md(item.ts))}</div>'
            f'<div class="t-title">{_esc(item.title)}</div>'
            + (f'<div class="t-meta">{_esc(meta)}</div>' if meta else "")
            + (f'<div class="t-detail">{_esc(headline)}</div>' if headline else "")
            + "</li>"
        )
    parts.append("</ol>")
    return "".join(parts)


def _hl_list_block(title: str, items: Sequence[str], *, code: bool = False,
                   limit: int = 12) -> str:
    if not items:
        return ""
    shown = list(items[:limit])
    lis = []
    for item in shown:
        body = f"<code>{_esc(item)}</code>" if code else _esc(item)
        lis.append(f"<li>{body}</li>")
    extra = len(items) - limit
    if extra > 0:
        lis.append(f'<li class="empty">+{extra} more</li>')
    return (
        f'<div class="hl-block"><h3>{_esc(title)}</h3>'
        f'<ul>{"".join(lis)}</ul></div>'
    )


def _render_highlights_html(report: MissionReport) -> str:
    if not report.highlights:
        return '<p class="empty">No builder/critic reports recorded yet.</p>'
    cards: List[str] = []
    for hl in report.highlights:
        exact = "" if hl.cost_exact else "~"
        meta = (
            f"{hl.engine} · {exact}${hl.cost_usd:.2f}"
            + (f" · {hl.tokens_label}" if hl.tokens_label else "")
            + f" · {hl.wall_seconds:.0f}s"
        )
        blocks: List[str] = []
        if hl.role == "critic":
            if hl.recommendation:
                blocks.append(
                    '<div class="hl-block"><h3>Verdict</h3>'
                    f'<ul><li><code>{_esc(hl.recommendation)}</code></li></ul></div>'
                )
            if hl.blocking_findings:
                blocks.append(_hl_list_block("Blocking findings", hl.blocking_findings))
            elif hl.recommendation == "PASS":
                blocks.append(
                    '<div class="hl-block"><h3>Blocking findings</h3>'
                    '<ul><li class="empty">none</li></ul></div>'
                )
        else:
            claim = (
                "yes" if hl.done is True
                else "no — work remains" if hl.done is False
                else ""
            )
            if claim:
                blocks.append(
                    '<div class="hl-block"><h3>Done claim</h3>'
                    f"<ul><li>{_esc(claim)}</li></ul></div>"
                )
            if hl.limit_reached:
                blocks.append(
                    '<div class="hl-block"><h3>Limit</h3>'
                    f'<ul><li><code>{_esc(hl.limit_reached)}</code></li></ul></div>'
                )
        blocks.append(_hl_list_block("Artifacts", hl.artifacts, code=True))
        blocks.append(_hl_list_block("Verified commands", hl.commands, code=True, limit=10))
        blocks.append(_hl_list_block("Risks / remaining", hl.risks, limit=8))
        summary = ""
        if hl.summary and hl.summary != hl.headline:
            summary = f'<div class="hl-summary">{_esc(hl.summary)}</div>'
        cards.append(
            f'<article class="hl-card {hl.tone}">'
            f'<div class="hl-head">'
            f'<div class="hl-title">{_esc(_highlight_heading(hl))}</div>'
            f'<div class="hl-meta">{_esc(meta)}</div>'
            f"</div>"
            + (f'<div class="hl-headline">{_esc(hl.headline)}</div>' if hl.headline else "")
            + summary
            + "".join(blocks)
            + "</article>"
        )
    return f'<div class="hl-list">{"".join(cards)}</div>'


def _render_files_html(paths: Sequence[str]) -> str:
    if not paths:
        return '<p class="empty">None detected (or clean tree).</p>'
    body = "".join(f"<code>{_esc(path)}</code>" for path in paths)
    return f'<div class="files">{body}</div>'


def _render_skills_html(skills: Sequence[SkillEntry]) -> str:
    if not skills:
        return '<p class="empty">No skill tree changes detected.</p>'
    cards: List[str] = []
    for skill in skills:
        engines = ", ".join(skill.engines) if skill.engines else "—"
        paths = "".join(
            f"<code>{_esc(path)}</code>" for path in skill.paths[:6]
        )
        extra = len(skill.paths) - 6
        if extra > 0:
            paths += f'<p class="empty">+{extra} more paths</p>'
        cards.append(
            f'<div class="skill-item">'
            f'<div class="name"><code>{_esc(skill.name)}</code></div>'
            f'<div class="engines">{_esc(engines)}</div>'
            f'<div class="skill-paths" style="margin-top:8px">{paths}</div>'
            f"</div>"
        )
    return f'<div class="skill-list">{"".join(cards)}</div>'


def render_html(report: MissionReport) -> str:
    tokens = _fmt_tokens(report.tokens_total)
    gen = time.strftime("%Y-%m-%d %H:%M", time.localtime(report.generated_at))
    title = f"{BRAND_NAME} Report · {report.mission_id}"

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

    timeline_html = _render_arc_html(report)
    highlights_html = _render_highlights_html(report)
    files_html = _render_files_html(report.changed_files)
    skills_html = _render_skills_html(report.skills)

    stop = f" · {_esc(report.stop_reason)}" if report.stop_reason else ""
    spend_sub = f"of ${_esc(f'{report.max_cost_usd:.2f}')}"
    if tokens:
        spend_sub = f"{_esc(tokens)} · {spend_sub}"

    body = f"""
<div class="wrap">
  <header class="hero">
    {_brand_html()}
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
    {timeline_html}
  </section>

  <section class="section">
    <h2>Builder highlights</h2>
    {highlights_html}
  </section>

  <section class="section">
    <h2>Changed files</h2>
    {files_html}
  </section>

  <section class="section">
    <h2>Skills</h2>
    {skills_html}
  </section>

  <section class="section">
    <h2>Next</h2>
    <div class="next">{_esc(report.next_step)}</div>
  </section>

  <p class="footer">{_esc(BRAND_NAME)} report · source <code>report.md</code> · viewer <code>report.html</code></p>
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
        f"{c['bold']} {BRAND_NAME} REPORT{c['reset']}  "
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
            parts = [ln.strip() for ln in item.detail.split("\n") if ln.strip()]
            # Prefer the headline line when present; else the metrics line.
            detail = parts[1] if len(parts) > 1 else (parts[0] if parts else "")
            lines.append(f"  {_ts_md(item.ts)[5:]}  {mark} {item.title}"
                         + (f" — {detail[:56]}" if detail else ""))
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
