"""AbsoLoop mission report — Markdown document + lite HTML viewer.

`absoloop report` regenerates `.absoloop/report.md` (source of truth) and
`.absoloop/report.html` (infographic-style lite viewer), then opens the
viewer in the default browser.
"""
from __future__ import annotations

import base64
import html
import json
import math
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
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_JUNK_NAMES = {
    ".ds_store", ".cfusertextencoding", ".bash_history", ".zsh_history",
    ".viminfo", ".lesshst",
}
_MAX_EVIDENCE_IMAGES = 6
_MAX_SHIPPED = 12
_MAX_CHANGED_FILES = 40
_MAX_THUMB_PX = 960
_MAX_THUMB_BYTES = 180_000

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
    evidence: List[str] = field(default_factory=list)
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


def _parse_evidence(value: Any) -> List[str]:
    """Normalize evidence field: strings or {path/caption} dicts → path list."""
    if value is None:
        return []
    if isinstance(value, str):
        text = " ".join(value.split())
        return [text] if text else []
    if not isinstance(value, (list, tuple)):
        return []
    out: List[str] = []
    for item in value:
        if isinstance(item, str):
            text = " ".join(item.split())
            if text:
                out.append(text)
            continue
        if isinstance(item, dict):
            path = item.get("path") or item.get("file") or item.get("src") or ""
            text = " ".join(str(path).split())
            if text:
                out.append(text)
    return out


def _is_image_path(path: str) -> bool:
    return pathlib.Path(path).suffix.lower() in _IMAGE_EXTS


def _is_junk_path(path: str) -> bool:
    name = pathlib.Path(path).name.lower()
    if name in _JUNK_NAMES:
        return True
    return name.endswith(".pyc") or name == "__pycache__"


def _short_path(path: str) -> str:
    """Display-friendly basename-heavy path."""
    text = path.replace("\\", "/").rstrip("/")
    if not text:
        return path
    parts = [p for p in text.split("/") if p]
    if len(parts) <= 2:
        return "/".join(parts) if parts else text
    return "/".join(parts[-2:])


def _evidence_caption(path: str) -> str:
    stem = pathlib.Path(path).stem
    stem = re.sub(r"^q[-_]", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"^p[-_]", "", stem, flags=re.IGNORECASE)
    stem = stem.replace("_", " ").replace("-", " ").strip()
    if not stem:
        return pathlib.Path(path).name
    return stem[:1].upper() + stem[1:]


def _resolve_evidence_path(project: pathlib.Path, path: str) -> Optional[pathlib.Path]:
    raw = pathlib.Path(path).expanduser()
    if raw.is_absolute():
        return raw if raw.is_file() else None
    cand = (project / raw).resolve()
    if cand.is_file():
        return cand
    # Absolute-looking paths stored without leading slash quirks
    if pathlib.Path(path).is_file():
        return pathlib.Path(path)
    return None


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
        "evidence": _parse_evidence(structured.get("evidence")),
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
        if _is_junk_path(path):
            continue
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


def _artifact_paths_from_highlights(highlights: Sequence[AgentHighlight]) -> List[str]:
    """Union of builder artifacts + evidence, latest-first, deduped."""
    builders = [h for h in highlights if h.role == "builder"]
    ordered: List[str] = []
    seen: set = set()
    for hl in reversed(builders):
        for path in list(hl.artifacts) + list(hl.evidence):
            key = path.replace("\\", "/")
            if not path or key in seen or _is_junk_path(path):
                continue
            seen.add(key)
            ordered.append(path)
    return ordered


def _shipped_artifacts(highlights: Sequence[AgentHighlight], *, limit: int = _MAX_SHIPPED) -> List[str]:
    """Primary non-image deliverables (latest builder first)."""
    out: List[str] = []
    for path in _artifact_paths_from_highlights(highlights):
        if _is_image_path(path):
            continue
        out.append(path)
        if len(out) >= limit:
            break
    return out


def _collect_evidence_images(
    highlights: Sequence[AgentHighlight], *, limit: int = _MAX_EVIDENCE_IMAGES,
) -> List[str]:
    """Image paths from evidence + artifacts, latest builder first."""
    builders = [h for h in highlights if h.role == "builder"]
    out: List[str] = []
    seen: set = set()
    for hl in reversed(builders):
        # Prefer explicit evidence, then image artifacts
        for path in list(hl.evidence) + list(hl.artifacts):
            if not _is_image_path(path):
                continue
            key = path.replace("\\", "/")
            if key in seen:
                continue
            seen.add(key)
            out.append(path)
            if len(out) >= limit:
                return out
    return out


def _nuggets_for_highlight(hl: AgentHighlight, *, limit: int = 4) -> List[str]:
    """Bite-sized result bullets — artifacts, verifies, risks/findings."""
    nuggets: List[str] = []
    if hl.role == "critic":
        if hl.recommendation:
            nuggets.append(f"Verdict: {hl.recommendation}")
        for finding in hl.blocking_findings[:2]:
            nuggets.append(finding)
        if hl.recommendation == "PASS" and not hl.blocking_findings:
            nuggets.append("No blocking findings")
        return nuggets[:limit]

    for path in hl.artifacts:
        if _is_image_path(path):
            continue
        nuggets.append(_short_path(path))
        if len(nuggets) >= 2:
            break
    for cmd in hl.commands[:2]:
        short = cmd if len(cmd) <= 90 else cmd[:87].rstrip() + "…"
        nuggets.append(f"Verified: {short}")
        if len(nuggets) >= limit:
            break
    for risk in hl.risks[:2]:
        if len(nuggets) >= limit:
            break
        short = risk if len(risk) <= 110 else risk[:107].rstrip() + "…"
        nuggets.append(short)
    if not nuggets and hl.summary:
        nuggets.append(_headline(hl.summary, max_len=120))
    return nuggets[:limit]


def _select_changed_files(
    git_files: Sequence[str],
    highlights: Sequence[AgentHighlight],
) -> List[str]:
    """Prefer builder artifacts when git porcelain is a noisy home-tree dump."""
    artifacts = _artifact_paths_from_highlights(highlights)
    clean_git = [p for p in git_files if not _is_junk_path(p)]
    # Home-directory missions often return hundreds of unrelated paths.
    if artifacts and (not clean_git or len(clean_git) > _MAX_CHANGED_FILES):
        return artifacts[:_MAX_CHANGED_FILES]
    if len(clean_git) > _MAX_CHANGED_FILES:
        # Keep skill-adjacent + first N
        return clean_git[:_MAX_CHANGED_FILES]
    return clean_git


def _which(name: str) -> bool:
    from shutil import which
    return which(name) is not None


def _next_step(status: str) -> str:
    if status == "AWAITING_APPROVAL":
        return ("Review the diff, then `absoloop approve` — or "
                "`absoloop reject \"what to change\"` and `absoloop resume`.")
    if status == "COMPLETED":
        return ("Results were delivered per the mission delivery mode. "
                "`absoloop extend` starts a follow-on run with fresh budgets.")
    if status == "BUDGET_EXHAUSTED":
        return ("Raise `max_iterations` / `max_cost_usd` / `max_wall_seconds` in "
                "`.absoloop/runtime.json`, then `absoloop resume` — or "
                "`absoloop extend` for a follow-on run with fresh budgets.")
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


def _current_run_start_ts(events: Sequence[dict]) -> float:
    """Timestamp of the latest mission extension; 0.0 when this is the first run.

    Results sections (Evidence, What shipped, Builder work, Critic) must refresh
    per run. The ledger is append-only across `--extend`, so anything at or
    before this boundary belongs to prior runs.
    """
    start = 0.0
    for event in events:
        if event.get("type") == "extension":
            start = float(event.get("ts") or 0)
    return start


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

    events = list(_iter_ledger(target))
    run_start = _current_run_start_ts(events)
    # Collapse noisy iteration markers across the full ledger, even though
    # result highlights are scoped to the current run.
    seen_builder_iters: set = set()

    for event in events:
        ts = float(event.get("ts") or 0)
        kind = event.get("type")
        # Full mission arc stays continuous; result highlights/stats are
        # scoped to the active run so Evidence and peers refresh each loop.
        in_current_run = ts > run_start

        if kind == "agent_run":
            wall = float(event.get("wall_seconds") or 0)
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
                    seen_builder_iters.add(iteration)
                    if in_current_run:
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

            if not in_current_run:
                continue

            stats["agent_runs"] += 1
            stats["wall_seconds"] += wall
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
                evidence=list(structured.get("evidence") or []),
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
            if iteration in seen_builder_iters:
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
            if iteration in seen_builder_iters:
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
            if in_current_run:
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
            if in_current_run:
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
    git_files, skills = _split_files_and_skills(_git_changed_paths(target))
    changed_files = _select_changed_files(git_files, highlights)

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


def _render_builder_nuggets_markdown(report: MissionReport) -> List[str]:
    builders = [h for h in report.highlights if h.role == "builder"]
    if not builders:
        return ["_No builder reports recorded yet._", ""]
    lines: List[str] = []
    for hl in builders:
        lines.append(f"### {_highlight_heading(hl)}")
        lines.append("")
        exact = "" if hl.cost_exact else "~"
        meta = f"`{hl.engine}` · {exact}${hl.cost_usd:.2f} · {hl.wall_seconds:.0f}s"
        lines.append(meta)
        lines.append("")
        if hl.headline:
            lines.append(f"**{hl.headline}**")
            lines.append("")
        nuggets = _nuggets_for_highlight(hl)
        for nugget in nuggets:
            lines.append(f"- {nugget}")
        if not nuggets and hl.summary:
            lines.append(f"- {_headline(hl.summary, max_len=140)}")
        lines.append("")
    return lines


def _render_critic_markdown(report: MissionReport) -> List[str]:
    critics = [h for h in report.highlights if h.role == "critic"]
    if not critics:
        return ["_No critic review yet._", ""]
    hl = critics[-1]
    lines = [
        f"**Verdict:** `{hl.recommendation or hl.status_label}`"
        + (f" · iteration {hl.iteration}" if hl.iteration is not None else ""),
        "",
    ]
    if hl.headline:
        lines += [hl.headline, ""]
    if hl.blocking_findings:
        lines.append("Blocking findings:")
        for finding in hl.blocking_findings:
            lines.append(f"- {finding}")
    elif hl.recommendation == "PASS":
        lines.append("- Blocking findings: none")
    lines.append("")
    return lines


def render_markdown(report: MissionReport) -> str:
    """Results-first Markdown — outcome, shipped work, evidence, then ops."""
    tokens = _fmt_tokens(report.tokens_total)
    gen = time.strftime("%Y-%m-%d %H:%M", time.localtime(report.generated_at))
    critic = _latest_critic(report)
    verdict = (critic.recommendation if critic else "") or "—"
    shipped = _shipped_artifacts(report.highlights)
    evidence = _collect_evidence_images(report.highlights)
    objective = report.objective.strip() or "_(no objective recorded)_"

    lines: List[str] = [
        f"# {BRAND_NAME} Report",
        "",
        f"**{report.status_label}** · `{report.mission_id}` · loop `{report.loop_id}`",
        "",
        f"> Generated {gen}",
        "",
        objective,
        "",
        "---",
        "",
        "## Outcome",
        "",
        f"**{report.status_label}** · critic `{verdict}`"
        + (f" · gate `{report.human_decision}`" if report.human_decision else ""),
        "",
        _outcome_line(report),
        "",
        f"- Iterations: {report.iteration}/{report.max_iterations or '—'}",
        f"- Spend: ${report.cost_usd:.2f}"
        + (f" ({tokens})" if tokens else "")
        + f" / ${report.max_cost_usd:.2f}",
        f"- Delivery: `{report.delivery_mode}` → {report.delivery_detail}",
        "",
        "---",
        "",
        "## What shipped",
        "",
    ]
    if shipped:
        for path in shipped:
            lines.append(f"- `{path}`")
    else:
        lines.append("_No primary artifacts recorded._")
    lines += ["", "---", "", "## Evidence", ""]
    if evidence:
        for path in evidence:
            lines.append(f"- **{_evidence_caption(path)}** — `{path}`")
    else:
        lines.append("_No screenshots or visual proof attached._")
    lines += ["", "---", "", "## Builder work", ""]
    lines += _render_builder_nuggets_markdown(report)
    lines += ["---", "", "## Critic", ""]
    lines += _render_critic_markdown(report)
    lines += [
        "---",
        "",
        "## Mission ops",
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
        "### Run arc",
        "",
    ]
    lines += _render_arc_markdown(report)
    if report.changed_files:
        lines += ["### Changed files", ""]
        for path in report.changed_files[:_MAX_CHANGED_FILES]:
            lines.append(f"- `{path}`")
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
.wrap { max-width: 960px; margin: 0 auto; padding: 32px 20px 64px; }
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
.hero-top {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 20px; margin-bottom: 8px; flex-wrap: wrap;
}
@media (max-width: 520px) {
  .hero-top { flex-direction: column-reverse; align-items: flex-start; }
  .brand { align-items: flex-start; text-align: left; }
  .brand-logo { height: 58px; }
  .report-mark { letter-spacing: 0.32em; }
}
.report-mark {
  font-size: clamp(1.35rem, 3.2vw, 1.85rem);
  font-weight: 750; letter-spacing: 0.42em;
  color: var(--ink);
  line-height: 1.1;
  padding-top: 6px;
  text-indent: 0.08em;
  background: linear-gradient(110deg, #e8eef6 0%, var(--accent) 45%, var(--ok) 100%);
  -webkit-background-clip: text; background-clip: text;
  color: transparent;
  text-transform: uppercase;
}
.brand {
  display: flex; flex-direction: column; align-items: center;
  gap: 8px; flex: 0 0 auto; text-align: center;
}
.brand-logo {
  display: block; height: 72px; width: auto;
  flex: 0 0 auto;
  filter: drop-shadow(0 8px 18px rgba(0,0,0,0.35));
}
.brand-name {
  color: var(--ink); font-size: 1.15rem; letter-spacing: -0.01em;
  font-weight: 750; line-height: 1;
}
.hero h1 {
  margin: 10px 0 8px; font-size: clamp(1.7rem, 4vw, 2.35rem);
  font-weight: 750; letter-spacing: -0.02em; line-height: 1.15;
  max-width: 16ch;
}
.meta { color: var(--muted); font-size: 13px; font-family: var(--mono); }
.meta code { color: var(--ink); }
.objective {
  margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--line);
  font-size: 1.02rem; max-width: 68ch; color: #d5e0ec;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}
.outcome-strip {
  display: grid; gap: 12px;
  grid-template-columns: 1fr;
  margin-bottom: 16px;
}
@media (min-width: 720px) {
  .outcome-strip { grid-template-columns: 1.4fr repeat(3, minmax(0, 1fr)); }
}
.outcome-main .value { font-size: 1.55rem; }
.outcome-main .lead {
  margin: 8px 0 0; font-size: 14px; font-weight: 500; color: #c9d7e8;
  line-height: 1.4;
}
.ship-list, .nugget-list {
  list-style: none; margin: 0; padding: 0; display: grid; gap: 8px;
}
.ship-list li, .nugget-list li {
  font-size: 13px; color: #d5e0ec; line-height: 1.4;
  padding: 8px 10px; border-radius: 10px;
  background: rgba(255,255,255,0.03); border: 1px solid var(--line);
}
.ship-list code {
  font-family: var(--mono); font-size: 12px; color: #c9d7e8; word-break: break-all;
}
.evidence-grid {
  display: grid; gap: 12px;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
}
.evidence-card {
  margin: 0; border-radius: 12px; overflow: hidden;
  background: rgba(255,255,255,0.03); border: 1px solid var(--line);
}
.evidence-card img {
  display: block; width: 100%; aspect-ratio: 16 / 10; object-fit: cover;
  background: #0a0f16;
}
.evidence-card figcaption {
  padding: 8px 10px 10px; font-size: 12px; color: #c9d7e8;
}
.evidence-card .cap { font-weight: 650; display: block; margin-bottom: 2px; }
.evidence-card .path {
  font-family: var(--mono); font-size: 10px; color: var(--muted);
  word-break: break-all;
}
.ops-details {
  background: var(--bg1); border: 1px solid var(--line);
  border-radius: var(--radius); padding: 0; margin-bottom: 16px;
  box-shadow: var(--shadow);
}
.ops-details > summary {
  cursor: pointer; list-style: none; padding: 16px 22px;
  font-size: 13px; text-transform: uppercase; letter-spacing: 0.1em;
  color: var(--muted); font-weight: 700; user-select: none;
}
.ops-details > summary::-webkit-details-marker { display: none; }
.ops-details > summary::after {
  content: "▸"; float: right; color: var(--accent);
}
.ops-details[open] > summary::after { content: "▾"; }
.ops-body { padding: 0 22px 18px; }
.metrics-block { margin-bottom: 22px; }
.grid {
  display: grid; gap: 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-bottom: 12px;
}
@media (min-width: 720px) {
  .grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
.summary-grid {
  display: grid; gap: 12px;
  grid-template-columns: 1fr;
  margin-bottom: 12px;
}
@media (min-width: 720px) {
  .summary-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
.viz-grid {
  display: grid; gap: 12px;
  grid-template-columns: 1fr;
  margin-bottom: 12px;
}
@media (min-width: 720px) {
  .viz-grid { grid-template-columns: 1fr 1fr; }
}
.card {
  background: var(--card); border: 1px solid var(--line);
  border-radius: var(--radius); padding: 16px 16px 14px;
  backdrop-filter: blur(6px);
  position: relative;
}
.card.viz { padding: 18px 18px 16px; min-height: 0; }
.card.summary { padding: 18px 18px 16px; }
.card .label {
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--muted); font-weight: 650; margin-bottom: 6px;
}
.card .value {
  font-size: 1.45rem; font-weight: 750; letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}
.card .sub { margin-top: 4px; font-size: 12px; color: var(--muted); font-family: var(--mono); }
.card .lead {
  font-size: 14px; font-weight: 650; color: #e7eef7; line-height: 1.4;
  margin: 4px 0 10px;
}
.stat-row {
  display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 10px;
}
.stat-pill {
  font-size: 11px; font-family: var(--mono); font-weight: 650;
  padding: 4px 8px; border-radius: 999px;
  background: rgba(255,255,255,0.05); border: 1px solid var(--line);
  color: #c9d7e8;
}
.stat-pill.ok { color: var(--ok); border-color: rgba(40,205,120,0.3); }
.stat-pill.warn { color: var(--warn); border-color: rgba(255,145,20,0.3); }
.stat-pill.err { color: var(--err); border-color: rgba(255,25,95,0.3); }
.stat-pill.accent { color: var(--accent); border-color: rgba(0,205,225,0.3); }
.pulse-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.pulse-list li {
  font-size: 13px; color: #d5e0ec; line-height: 1.4;
  padding-left: 14px; position: relative;
}
.pulse-list li::before {
  content: ""; position: absolute; left: 0; top: 0.55em;
  width: 6px; height: 6px; border-radius: 50%; background: var(--accent);
}
.pulse-list li.warn::before { background: var(--warn); }
.pulse-list li.ok::before { background: var(--ok); }
.pulse-list li.err::before { background: var(--err); }
.pulse-list li.accent::before { background: var(--accent); }
.pulse-list li.muted { color: var(--muted); font-style: italic; }
.pulse-list li.muted::before { display: none; }
.pulse-list li .tag {
  font-family: var(--mono); font-size: 10px; color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.04em; margin-right: 6px;
}
.bar {
  margin-top: 10px; height: 7px; border-radius: 999px;
  background: rgba(255,255,255,0.06); overflow: hidden;
}
.bar > i {
  display: block; height: 100%; border-radius: inherit;
  background: linear-gradient(90deg, var(--accent), var(--ok) 55%, var(--gold));
}
.bar.warn > i { background: linear-gradient(90deg, var(--warn), var(--err)); }
.donut-wrap {
  display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
  margin-top: 8px;
}
.donut-svg { width: 148px; height: 148px; flex: 0 0 auto; }
.donut-center-label {
  font-size: 1.35rem; font-weight: 750; letter-spacing: -0.02em;
  fill: var(--ink); font-family: var(--font);
}
.donut-center-sub {
  font-size: 10px; fill: var(--muted); font-family: var(--mono);
  letter-spacing: 0.06em; text-transform: uppercase;
}
.legend { display: grid; gap: 8px; flex: 1 1 140px; min-width: 120px; }
.legend-row {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px; color: #c9d7e8;
}
.legend-swatch {
  width: 10px; height: 10px; border-radius: 3px; flex: 0 0 auto;
}
.legend-val {
  margin-left: auto; font-family: var(--mono); color: var(--muted); font-size: 11px;
}
.iter-bars { display: grid; gap: 8px; margin-top: 10px; }
.iter-bar-row {
  display: grid; grid-template-columns: 42px 1fr auto; gap: 10px;
  align-items: center;
}
.iter-bar-row .ib-label {
  font-family: var(--mono); font-size: 11px; color: var(--muted);
}
.iter-bar-row .ib-track {
  height: 18px; border-radius: 8px; background: rgba(255,255,255,0.05);
  overflow: hidden; position: relative; display: flex;
}
.iter-bar-row .ib-fill {
  height: 100%;
  background: linear-gradient(90deg, rgba(0,105,255,0.85), rgba(0,205,225,0.9));
}
.iter-bar-row .ib-fill.critic {
  background: linear-gradient(90deg, rgba(255,145,20,0.75), rgba(255,190,15,0.9));
}
.iter-bar-row .ib-meta {
  font-family: var(--mono); font-size: 11px; color: var(--muted);
  white-space: nowrap;
}
.verdict-chip {
  display: inline-flex; align-items: center; padding: 2px 7px; border-radius: 999px;
  font-size: 10px; font-weight: 750; letter-spacing: 0.04em;
  border: 1px solid var(--line); margin-left: 6px;
}
.verdict-chip.ok { color: var(--ok); border-color: rgba(40,205,120,0.35); }
.verdict-chip.warn { color: var(--warn); border-color: rgba(255,145,20,0.35); }
.verdict-chip.err { color: var(--err); border-color: rgba(255,25,95,0.35); }
.verdict-chip.accent { color: var(--accent); border-color: rgba(0,205,225,0.35); }
.viz-empty {
  margin-top: 18px; color: var(--muted); font-style: italic; font-size: 13px;
}
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
.nugget-list { margin-top: 10px; }
.nugget-list li {
  padding: 6px 10px; font-size: 13px;
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
        f'<img class="brand-logo" src="{uri}" alt="{_esc(BRAND_NAME)}" width="220" height="96">'
        if uri else ""
    )
    return (
        f'<div class="brand">{logo}'
        f'<strong class="brand-name">{_esc(BRAND_NAME)}</strong></div>'
    )


def _thumbnail_bytes(path: pathlib.Path) -> Optional[Tuple[bytes, str]]:
    """Return (jpeg_bytes, mime) thumbnail, or None if unavailable."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if not raw:
        return None

    # Prefer Pillow when present (tests + Linux); fall back to sips on macOS.
    try:
        from io import BytesIO
        from PIL import Image

        with Image.open(BytesIO(raw)) as img:
            img = img.convert("RGB") if img.mode not in ("RGB", "L") else img.convert("RGB")
            img.thumbnail((_MAX_THUMB_PX, _MAX_THUMB_PX))
            quality = 82
            while quality >= 55:
                buf = BytesIO()
                img.save(buf, format="JPEG", quality=quality, optimize=True)
                data = buf.getvalue()
                if len(data) <= _MAX_THUMB_BYTES or quality <= 55:
                    return data, "image/jpeg"
                quality -= 8
    except Exception:
        pass

    if not _which("sips"):
        # Last resort: embed small originals only.
        if len(raw) <= _MAX_THUMB_BYTES:
            ext = path.suffix.lower().lstrip(".") or "png"
            mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
            return raw, mime
        return None

    import tempfile

    try:
        with tempfile.TemporaryDirectory(prefix="absoloop-thumb-") as tmp:
            out = pathlib.Path(tmp) / "thumb.jpg"
            # Resize longest edge, then convert to JPEG.
            subprocess.run(
                ["sips", "-Z", str(_MAX_THUMB_PX), str(path), "--out", str(out)],
                capture_output=True, check=False,
            )
            if not out.is_file():
                subprocess.run(
                    ["sips", "-s", "format", "jpeg", str(path), "--out", str(out)],
                    capture_output=True, check=False,
                )
            else:
                # Ensure JPEG even if source was PNG already resized in place.
                if out.suffix.lower() != ".jpg":
                    jpg = pathlib.Path(tmp) / "thumb2.jpg"
                    subprocess.run(
                        ["sips", "-s", "format", "jpeg", str(out), "--out", str(jpg)],
                        capture_output=True, check=False,
                    )
                    if jpg.is_file():
                        out = jpg
            if not out.is_file():
                return None
            data = out.read_bytes()
            if not data:
                return None
            if len(data) > _MAX_THUMB_BYTES:
                # One more downscale pass
                small = pathlib.Path(tmp) / "thumb-sm.jpg"
                subprocess.run(
                    ["sips", "-Z", "640", str(out), "--out", str(small)],
                    capture_output=True, check=False,
                )
                if small.is_file():
                    data = small.read_bytes()
            return data, "image/jpeg"
    except OSError:
        return None


def _image_data_uri(path: pathlib.Path) -> str:
    thumb = _thumbnail_bytes(path)
    if not thumb:
        return ""
    data, mime = thumb
    return f"data:{mime};base64," + base64.standard_b64encode(data).decode("ascii")


def _latest_critic(report: MissionReport) -> Optional[AgentHighlight]:
    for hl in reversed(report.highlights):
        if hl.role == "critic":
            return hl
    return None


def _latest_builder(report: MissionReport) -> Optional[AgentHighlight]:
    for hl in reversed(report.highlights):
        if hl.role == "builder":
            return hl
    return None


def _outcome_line(report: MissionReport) -> str:
    critic = _latest_critic(report)
    builder = _latest_builder(report)
    if critic and critic.headline:
        return critic.headline
    if builder and builder.headline:
        return builder.headline
    if report.stop_reason:
        return report.stop_reason
    return report.status_label


def _truncate_objective(text: str, *, max_len: int = 220) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= max_len:
        return clean
    cut = clean[: max_len - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:") + "…"


def _bar_html(used: float, cap: float) -> str:
    pct = _pct(used, cap)
    warn = " warn" if pct >= 90 else ""
    return f'<div class="bar{warn}"><i style="width:{pct:.1f}%"></i></div>'


def _polar(cx: float, cy: float, r: float, deg: float) -> Tuple[float, float]:
    rad = math.radians(deg - 90)
    return cx + r * math.cos(rad), cy + r * math.sin(rad)


def _donut_arc_path(
    cx: float, cy: float, r_outer: float, r_inner: float,
    start_deg: float, sweep_deg: float,
) -> str:
    if sweep_deg <= 0:
        return ""
    sweep = min(359.999, sweep_deg)
    large = 1 if sweep > 180 else 0
    x0, y0 = _polar(cx, cy, r_outer, start_deg)
    x1, y1 = _polar(cx, cy, r_outer, start_deg + sweep)
    x2, y2 = _polar(cx, cy, r_inner, start_deg + sweep)
    x3, y3 = _polar(cx, cy, r_inner, start_deg)
    return (
        f"M {x0:.2f} {y0:.2f} A {r_outer:.2f} {r_outer:.2f} 0 {large} 1 "
        f"{x1:.2f} {y1:.2f} L {x2:.2f} {y2:.2f} "
        f"A {r_inner:.2f} {r_inner:.2f} 0 {large} 0 {x3:.2f} {y3:.2f} Z"
    )


def _render_budget_donut_html(report: MissionReport) -> str:
    """Donut of budget utilization across iterations / spend / wall."""
    colors = ("#00cde1", "#28cd78", "#ffbe0f")
    segments: List[Tuple[str, float, float, str]] = []
    # (label, used_pct 0-100, display value, color)
    segments.append((
        "Iterations",
        _pct(report.iteration, report.max_iterations),
        f"{report.iteration}/{report.max_iterations or '—'}",
        colors[0],
    ))
    segments.append((
        "Spend",
        _pct(report.cost_usd, report.max_cost_usd),
        f"${report.cost_usd:.2f}",
        colors[1],
    ))
    if report.max_wall_seconds or report.wall_seconds:
        segments.append((
            "Agent wall",
            _pct(report.wall_seconds, report.max_wall_seconds),
            f"{report.wall_seconds:.0f}s",
            colors[2],
        ))
    weights = [max(0.0, s[1]) for s in segments]
    total_w = sum(weights)
    if total_w <= 0:
        # Empty ring — show unused budgets.
        weights = [1.0 for _ in segments]
        total_w = float(len(weights))
        ring_colors = ["rgba(255,255,255,0.08)"] * len(segments)
    else:
        ring_colors = [s[3] for s in segments]

    avg_pct = sum(s[1] for s in segments) / max(1, len(segments))
    cx = cy = 74.0
    r_outer, r_inner = 66.0, 42.0
    paths: List[str] = []
    angle = 0.0
    gap = 2.5 if len(segments) > 1 else 0.0
    usable = 360.0 - gap * len(segments)
    for i, seg in enumerate(segments):
        sweep = usable * (weights[i] / total_w)
        d = _donut_arc_path(cx, cy, r_outer, r_inner, angle, sweep)
        if d:
            paths.append(
                f'<path d="{d}" fill="{ring_colors[i]}" '
                f'stroke="rgba(12,17,24,0.55)" stroke-width="1.5"/>'
            )
        angle += sweep + gap

    legend = "".join(
        f'<div class="legend-row">'
        f'<span class="legend-swatch" style="background:{_esc(seg[3])}"></span>'
        f'<span>{_esc(seg[0])}</span>'
        f'<span class="legend-val">{_esc(seg[2])} · {seg[1]:.0f}%</span>'
        f"</div>"
        for seg in segments
    )
    svg = (
        f'<svg class="donut-svg" viewBox="0 0 148 148" role="img" '
        f'aria-label="Budget utilization donut">'
        f'<circle cx="{cx}" cy="{cy}" r="{(r_outer + r_inner) / 2:.1f}" '
        f'fill="none" stroke="rgba(255,255,255,0.06)" '
        f'stroke-width="{r_outer - r_inner:.1f}"/>'
        + "".join(paths)
        + f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" '
        f'class="donut-center-label">{avg_pct:.0f}%</text>'
        f'<text x="{cx}" y="{cy + 14}" text-anchor="middle" '
        f'class="donut-center-sub">budget used</text>'
        f"</svg>"
    )
    return (
        f'<div class="card viz">'
        f'<div class="label">Budget mix</div>'
        f'<div class="donut-wrap">{svg}<div class="legend">{legend}</div></div>'
        f"</div>"
    )


def _unique_keep_order(items: Sequence[str], *, limit: int = 5) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        text = " ".join(str(item or "").split())
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _verdict_tone(rec: str) -> str:
    rec = (rec or "").upper()
    if rec == "PASS":
        return "ok"
    if rec == "HOLD":
        return "warn"
    if rec == "REJECT":
        return "err"
    return "accent"


def _render_mission_pulse_html(report: MissionReport) -> str:
    """Narrative Tasks / Decisions / Results summary cards."""
    builders = [h for h in report.highlights if h.role == "builder"]
    critics = [h for h in report.highlights if h.role == "critic"]
    latest_builder = builders[-1] if builders else None
    latest_critic = critics[-1] if critics else None

    done_yes = sum(1 for h in builders if h.done is True)
    done_no = sum(1 for h in builders if h.done is False)
    artifacts = _unique_keep_order(
        [a for h in builders for a in h.artifacts], limit=4,
    )
    commands = _unique_keep_order(
        [c for h in builders for c in h.commands], limit=3,
    )
    risks = _unique_keep_order(
        [r for h in builders for r in h.risks], limit=3,
    )
    blocking = _unique_keep_order(
        [b for h in critics for b in h.blocking_findings], limit=3,
    )

    # --- Tasks ---
    task_lead = (
        (latest_builder.headline if latest_builder and latest_builder.headline else "")
        or (latest_builder.summary if latest_builder else "")
        or "No builder work recorded yet."
    )
    task_stats = [
        f'<span class="stat-pill accent">{len(builders)} builder runs</span>',
        f'<span class="stat-pill ok">{done_yes} done claimed</span>',
        f'<span class="stat-pill warn">{done_no} still open</span>',
        f'<span class="stat-pill">{len(artifacts)} artifacts</span>',
    ]
    task_items: List[str] = []
    for path in artifacts:
        task_items.append(
            f'<li><span class="tag">file</span><code>{_esc(path)}</code></li>'
        )
    for cmd in commands:
        task_items.append(
            f'<li class="warn"><span class="tag">cmd</span>{_esc(cmd)}</li>'
        )
    if not task_items:
        task_items.append('<li class="muted">No artifacts or commands yet.</li>')
    tasks_html = (
        '<div class="card summary">'
        '<div class="label">Tasks</div>'
        f'<div class="lead">{_esc(task_lead)}</div>'
        f'<div class="stat-row">{"".join(task_stats)}</div>'
        f'<ul class="pulse-list">{"".join(task_items)}</ul>'
        "</div>"
    )

    # --- Decisions ---
    if latest_critic and latest_critic.recommendation:
        dec_lead = (
            f"Latest critic · {latest_critic.recommendation}"
            + (f" (iteration {latest_critic.iteration})"
               if latest_critic.iteration is not None else "")
        )
        if latest_critic.headline:
            dec_lead = latest_critic.headline
    elif report.human_decision:
        dec_lead = f"Human gate · {report.human_decision}"
    elif latest_builder and latest_builder.done is True:
        dec_lead = "Builder claimed done — awaiting critic / gate."
    else:
        dec_lead = "No critic or gate decisions yet."

    pass_n = sum(1 for h in critics if (h.recommendation or "").upper() == "PASS")
    hold_n = sum(1 for h in critics if (h.recommendation or "").upper() == "HOLD")
    reject_n = sum(1 for h in critics if (h.recommendation or "").upper() == "REJECT")
    dec_stats = [
        f'<span class="stat-pill ok">PASS {pass_n}</span>',
        f'<span class="stat-pill warn">HOLD {hold_n}</span>',
        f'<span class="stat-pill err">REJECT {reject_n}</span>',
    ]
    if report.human_decision:
        tone = "ok" if report.human_decision.lower() in ("approve", "approved") else "warn"
        dec_stats.append(
            f'<span class="stat-pill {tone}">Gate: {_esc(report.human_decision)}</span>'
        )
    if report.integrity_ok is True:
        dec_stats.append('<span class="stat-pill ok">Integrity ✓</span>')
    elif report.integrity_ok is False:
        dec_stats.append('<span class="stat-pill err">Integrity ✗</span>')

    dec_items: List[str] = []
    for h in critics[-4:]:
        rec = (h.recommendation or h.status_label or "reviewed").upper()
        tone = _verdict_tone(rec)
        iter_bit = f"i{h.iteration}" if h.iteration is not None else "run"
        detail = h.headline or h.status_label or rec
        dec_items.append(
            f'<li class="{tone}"><span class="tag">{_esc(iter_bit)} · {_esc(rec)}</span>'
            f"{_esc(detail)}</li>"
        )
    if latest_builder and latest_builder.done is not None:
        tone = "ok" if latest_builder.done else "warn"
        claim = "Done claimed" if latest_builder.done else "Work remains"
        dec_items.append(
            f'<li class="{tone}"><span class="tag">builder</span>{claim}</li>'
        )
    for finding in blocking:
        dec_items.append(
            f'<li class="err"><span class="tag">block</span>{_esc(finding)}</li>'
        )
    if not dec_items:
        dec_items.append('<li class="muted">No decisions recorded.</li>')
    decisions_html = (
        '<div class="card summary">'
        '<div class="label">Decisions</div>'
        f'<div class="lead">{_esc(dec_lead)}</div>'
        f'<div class="stat-row">{"".join(dec_stats)}</div>'
        f'<ul class="pulse-list">{"".join(dec_items)}</ul>'
        "</div>"
    )

    # --- Results ---
    status_line = report.status
    if report.stop_reason:
        status_line = f"{report.status} ({report.stop_reason})"
    result_lead = (
        (latest_critic.headline if latest_critic and latest_critic.headline else "")
        or (latest_builder.headline if latest_builder and latest_builder.headline else "")
        or status_line
    )
    file_n = len(report.changed_files)
    skill_n = len(report.skills)
    result_stats = [
        f'<span class="stat-pill {report.status_tone}">{_esc(report.status_label)}</span>',
        f'<span class="stat-pill">{file_n} files changed</span>',
        f'<span class="stat-pill">{skill_n} skills</span>',
        f'<span class="stat-pill accent">{report.agent_runs} agent runs</span>',
    ]
    result_items: List[str] = [
        f'<li class="{report.status_tone}"><span class="tag">status</span>'
        f"{_esc(status_line)}</li>",
        f'<li><span class="tag">delivery</span>{_esc(report.delivery_mode)}'
        f" → {_esc(report.delivery_detail)}</li>",
    ]
    for path in report.changed_files[:3]:
        result_items.append(
            f'<li class="ok"><span class="tag">diff</span><code>{_esc(path)}</code></li>'
        )
    for risk in risks:
        result_items.append(
            f'<li class="warn"><span class="tag">risk</span>{_esc(risk)}</li>'
        )
    if report.next_step:
        result_items.append(
            f'<li class="accent"><span class="tag">next</span>{_esc(report.next_step)}</li>'
        )
    results_html = (
        '<div class="card summary">'
        '<div class="label">Results</div>'
        f'<div class="lead">{_esc(result_lead)}</div>'
        f'<div class="stat-row">{"".join(result_stats)}</div>'
        f'<ul class="pulse-list">{"".join(result_items)}</ul>'
        "</div>"
    )
    return (
        f'<div class="summary-grid">{tasks_html}{decisions_html}{results_html}</div>'
    )


def _render_outcome_donut_html(report: MissionReport) -> str:
    """Donut of critic verdicts + builder done claims."""
    critics = [h for h in report.highlights if h.role == "critic"]
    builders = [h for h in report.highlights if h.role == "builder"]
    counts = {
        "PASS": sum(1 for h in critics if (h.recommendation or "").upper() == "PASS"),
        "HOLD": sum(1 for h in critics if (h.recommendation or "").upper() == "HOLD"),
        "REJECT": sum(1 for h in critics if (h.recommendation or "").upper() == "REJECT"),
        "Done": sum(1 for h in builders if h.done is True),
        "Open": sum(1 for h in builders if h.done is False),
    }
    palette = {
        "PASS": "#28cd78",
        "HOLD": "#ff9114",
        "REJECT": "#ff195f",
        "Done": "#00cde1",
        "Open": "#8a9bb0",
    }
    segments = [(k, float(v), palette[k]) for k, v in counts.items() if v > 0]
    if not segments:
        return (
            '<div class="card viz">'
            '<div class="label">Outcomes</div>'
            '<p class="viz-empty">No verdicts or done claims yet.</p>'
            "</div>"
        )

    total = sum(v for _, v, _ in segments) or 1.0
    cx = cy = 74.0
    r_outer, r_inner = 66.0, 42.0
    paths: List[str] = []
    angle = 0.0
    gap = 2.5 if len(segments) > 1 else 0.0
    usable = 360.0 - gap * len(segments)
    for label, value, color in segments:
        sweep = usable * (value / total)
        d = _donut_arc_path(cx, cy, r_outer, r_inner, angle, sweep)
        if d:
            paths.append(
                f'<path d="{d}" fill="{color}" '
                f'stroke="rgba(12,17,24,0.55)" stroke-width="1.5"/>'
            )
        angle += sweep + gap

    primary = max(segments, key=lambda s: s[1])
    legend = "".join(
        f'<div class="legend-row">'
        f'<span class="legend-swatch" style="background:{color}"></span>'
        f'<span>{_esc(label)}</span>'
        f'<span class="legend-val">{int(value)}</span>'
        f"</div>"
        for label, value, color in segments
    )
    svg = (
        f'<svg class="donut-svg" viewBox="0 0 148 148" role="img" '
        f'aria-label="Outcome mix donut">'
        f'<circle cx="{cx}" cy="{cy}" r="{(r_outer + r_inner) / 2:.1f}" '
        f'fill="none" stroke="rgba(255,255,255,0.06)" '
        f'stroke-width="{r_outer - r_inner:.1f}"/>'
        + "".join(paths)
        + f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" '
        f'class="donut-center-label">{_esc(primary[0])}</text>'
        f'<text x="{cx}" y="{cy + 14}" text-anchor="middle" '
        f'class="donut-center-sub">top outcome</text>'
        f"</svg>"
    )
    return (
        '<div class="card viz">'
        '<div class="label">Outcomes</div>'
        '<div class="sub">Critic verdicts · builder claims</div>'
        f'<div class="donut-wrap">{svg}<div class="legend">{legend}</div></div>'
        "</div>"
    )


def _render_iteration_bars_html(report: MissionReport) -> str:
    """Per-iteration spend bars with latest critic verdict chip."""
    by_iter: Dict[int, Dict[str, Any]] = {}
    for hl in report.highlights:
        if hl.iteration is None:
            continue
        bucket = by_iter.setdefault(hl.iteration, {
            "builder_cost": 0.0, "critic_cost": 0.0, "verdict": "", "tone": "accent",
        })
        if hl.role == "builder":
            bucket["builder_cost"] += float(hl.cost_usd or 0)
        else:
            bucket["critic_cost"] += float(hl.cost_usd or 0)
            if hl.recommendation:
                bucket["verdict"] = hl.recommendation.upper()
                bucket["tone"] = _verdict_tone(hl.recommendation)

    if not by_iter:
        return (
            '<div class="card viz">'
            '<div class="label">Iteration spend</div>'
            '<p class="viz-empty">No iteration spend yet.</p>'
            "</div>"
        )

    max_cost = max(
        (b["builder_cost"] + b["critic_cost"]) for b in by_iter.values()
    ) or 1.0
    rows: List[str] = []
    for it in sorted(by_iter):
        bucket = by_iter[it]
        total = bucket["builder_cost"] + bucket["critic_cost"]
        builder_pct = 100.0 * bucket["builder_cost"] / max_cost
        critic_pct = 100.0 * bucket["critic_cost"] / max_cost
        chip = ""
        if bucket["verdict"]:
            chip = (
                f'<span class="verdict-chip {bucket["tone"]}">'
                f'{_esc(bucket["verdict"])}</span>'
            )
        fills = (
            f'<div class="ib-fill" style="width:{builder_pct:.1f}%"></div>'
            if builder_pct > 0 else ""
        )
        if critic_pct > 0:
            fills += (
                f'<div class="ib-fill critic" style="width:{critic_pct:.1f}%"></div>'
            )
        rows.append(
            f'<div class="iter-bar-row">'
            f'<div class="ib-label">i{it}</div>'
            f'<div class="ib-track" title="builder ${bucket["builder_cost"]:.2f}'
            f' · critic ${bucket["critic_cost"]:.2f}">{fills}</div>'
            f'<div class="ib-meta">${total:.2f}{chip}</div>'
            f"</div>"
        )

    return (
        '<div class="card viz">'
        '<div class="label">Iteration spend</div>'
        '<div class="sub">Builder (teal) · critic (gold) · verdict</div>'
        f'<div class="iter-bars">{"".join(rows)}</div>'
        "</div>"
    )


def _render_run_heatmap_html(report: MissionReport) -> str:
    """Heatmap of cost intensity by iteration × role."""
    cells: Dict[Tuple[int, str], float] = {}
    iters: List[int] = []
    for hl in report.highlights:
        if hl.iteration is None:
            continue
        key = (hl.iteration, hl.role)
        cells[key] = cells.get(key, 0.0) + max(0.0, float(hl.cost_usd or 0))
        if hl.iteration not in iters:
            iters.append(hl.iteration)
    if not cells:
        # Fall back to empty placeholder still structured for layout.
        return (
            '<div class="card viz">'
            '<div class="label">Run heatmap</div>'
            '<p class="viz-empty">No timed agent runs yet.</p>'
            "</div>"
        )
    iters = sorted(iters)
    roles = ["builder", "critic"]
    max_v = max(cells.values()) or 1.0
    parts = [
        f'<div class="heatmap" style="--hm-cols:{len(roles)}">'
        '<div class="hm-corner"></div>'
    ]
    for role in roles:
        parts.append(f'<div class="hm-col">{_esc(role)}</div>')
    for it in iters:
        parts.append(f'<div class="hm-row">i{it}</div>')
        for role in roles:
            val = cells.get((it, role), 0.0)
            intensity = val / max_v if max_v else 0.0
            if role == "builder":
                bg = (
                    f"rgba(0,205,225,{0.12 + 0.72 * intensity:.2f})"
                )
            else:
                bg = (
                    f"rgba(255,145,20,{0.12 + 0.72 * intensity:.2f})"
                )
            label = f"${val:.2f}" if val else "—"
            parts.append(
                f'<div class="hm-cell" style="background:{bg}">{_esc(label)}</div>'
            )
    parts.append("</div>")
    return (
        '<div class="card viz">'
        '<div class="label">Run heatmap</div>'
        '<div class="sub">Cost by iteration × role</div>'
        + "".join(parts)
        + "</div>"
    )


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


def _render_builder_nuggets_html(report: MissionReport) -> str:
    builders = [h for h in report.highlights if h.role == "builder"]
    if not builders:
        return '<p class="empty">No builder reports recorded yet.</p>'
    cards: List[str] = []
    for hl in builders:
        exact = "" if hl.cost_exact else "~"
        meta = f"{hl.engine} · {exact}${hl.cost_usd:.2f} · {hl.wall_seconds:.0f}s"
        nuggets = _nuggets_for_highlight(hl)
        if not nuggets and hl.summary:
            nuggets = [_headline(hl.summary, max_len=140)]
        nugget_html = ""
        if nuggets:
            items = "".join(f"<li>{_esc(n)}</li>" for n in nuggets)
            nugget_html = f'<ul class="nugget-list">{items}</ul>'
        cards.append(
            f'<article class="hl-card {hl.tone}">'
            f'<div class="hl-head">'
            f'<div class="hl-title">{_esc(_highlight_heading(hl))}</div>'
            f'<div class="hl-meta">{_esc(meta)}</div>'
            f"</div>"
            + (f'<div class="hl-headline">{_esc(hl.headline)}</div>' if hl.headline else "")
            + nugget_html
            + "</article>"
        )
    return f'<div class="hl-list">{"".join(cards)}</div>'


def _render_critic_html(report: MissionReport) -> str:
    critic = _latest_critic(report)
    if not critic:
        return '<p class="empty">No critic review yet.</p>'
    tone = _verdict_tone(critic.recommendation)
    findings = ""
    if critic.blocking_findings:
        findings = _hl_list_block("Blocking findings", critic.blocking_findings)
    elif critic.recommendation == "PASS":
        findings = (
            '<div class="hl-block"><h3>Blocking findings</h3>'
            '<ul><li class="empty">none</li></ul></div>'
        )
    return (
        f'<article class="hl-card {tone}">'
        f'<div class="hl-head">'
        f'<div class="hl-title">Critic · {_esc(critic.status_label)}</div>'
        f'<div class="hl-meta">{_esc(critic.engine)} · ${critic.cost_usd:.2f}'
        f' · {critic.wall_seconds:.0f}s</div>'
        f"</div>"
        + (f'<div class="hl-headline">{_esc(critic.headline)}</div>'
           if critic.headline else "")
        + findings
        + "</article>"
    )


def _render_shipped_html(report: MissionReport) -> str:
    shipped = _shipped_artifacts(report.highlights)
    if not shipped:
        return '<p class="empty">No primary artifacts recorded.</p>'
    items = "".join(
        f"<li><code>{_esc(path)}</code></li>" for path in shipped
    )
    return f'<ul class="ship-list">{items}</ul>'


def _render_evidence_gallery_html(report: MissionReport) -> str:
    paths = _collect_evidence_images(report.highlights)
    if not paths:
        return '<p class="empty">No screenshots or visual proof attached.</p>'
    cards: List[str] = []
    for path in paths:
        resolved = _resolve_evidence_path(report.project, path)
        uri = _image_data_uri(resolved) if resolved else ""
        caption = _evidence_caption(path)
        short = _short_path(path)
        if uri:
            img = (
                f'<img src="{uri}" alt="{_esc(caption)}" loading="lazy">'
            )
        else:
            img = (
                f'<div class="hl-summary" style="padding:24px 12px;text-align:center">'
                f'Missing file<br><code>{_esc(short)}</code></div>'
            )
        cards.append(
            f'<figure class="evidence-card">{img}'
            f'<figcaption><span class="cap">{_esc(caption)}</span>'
            f'<span class="path">{_esc(short)}</span></figcaption></figure>'
        )
    return f'<div class="evidence-grid">{"".join(cards)}</div>'


def _render_outcome_strip_html(report: MissionReport) -> str:
    critic = _latest_critic(report)
    verdict = (critic.recommendation if critic else "") or "—"
    tone = _verdict_tone(verdict) if critic else report.status_tone
    tokens = _fmt_tokens(report.tokens_total)
    spend_sub = f"of ${report.max_cost_usd:.2f}"
    if tokens:
        spend_sub = f"{tokens} · {spend_sub}"
    return (
        '<div class="outcome-strip">'
        f'<div class="card outcome-main {report.status_tone}">'
        '<div class="label">Outcome</div>'
        f'<div class="value">{_esc(report.status_label)}</div>'
        f'<div class="lead">{_esc(_outcome_line(report))}</div>'
        f'<div class="stat-row" style="margin-top:10px">'
        f'<span class="stat-pill {tone}">Critic {_esc(verdict)}</span>'
        + (f'<span class="stat-pill ok">Gate: {_esc(report.human_decision)}</span>'
           if report.human_decision else "")
        + "</div></div>"
        '<div class="card">'
        '<div class="label">Iterations</div>'
        f'<div class="value">{report.iteration}'
        f'<span style="color:var(--muted);font-size:1rem"> / '
        f'{report.max_iterations or "—"}</span></div>'
        f'{_bar_html(report.iteration, report.max_iterations)}'
        "</div>"
        '<div class="card">'
        '<div class="label">Spend</div>'
        f'<div class="value">${report.cost_usd:.2f}</div>'
        f'<div class="sub">{_esc(spend_sub)}</div>'
        f'{_bar_html(report.cost_usd, report.max_cost_usd)}'
        "</div>"
        '<div class="card">'
        '<div class="label">Delivery</div>'
        f'<div class="value" style="font-size:1.15rem">{_esc(report.delivery_mode)}</div>'
        f'<div class="sub">{_esc(report.delivery_detail)}</div>'
        "</div></div>"
    )


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
    gen = time.strftime("%Y-%m-%d %H:%M", time.localtime(report.generated_at))
    title = f"{BRAND_NAME} Report · {report.mission_id}"
    stop = f" · {_esc(report.stop_reason)}" if report.stop_reason else ""
    objective = _truncate_objective(report.objective or "No objective recorded.")

    outcome_html = _render_outcome_strip_html(report)
    shipped_html = _render_shipped_html(report)
    evidence_html = _render_evidence_gallery_html(report)
    builder_html = _render_builder_nuggets_html(report)
    critic_html = _render_critic_html(report)
    skills_html = _render_skills_html(report.skills)
    timeline_html = _render_arc_html(report)
    files_html = _render_files_html(report.changed_files)
    donut_html = _render_budget_donut_html(report)
    outcome_donut_html = _render_outcome_donut_html(report)
    iter_bars_html = _render_iteration_bars_html(report)
    wall_card = ""
    if report.max_wall_seconds or report.wall_seconds:
        wall_card = (
            '<div class="card">'
            '<div class="label">Agent wall</div>'
            f'<div class="value">{report.wall_seconds:.0f}s</div>'
            f'<div class="sub">budget {report.max_wall_seconds:.0f}s</div>'
            f'{_bar_html(report.wall_seconds, report.max_wall_seconds)}'
            "</div>"
        )

    body = f"""
<div class="wrap">
  <header class="hero">
    <div class="hero-top">
      <div class="report-mark" aria-label="Report">R E P O R T</div>
      {_brand_html()}
    </div>
    <h1>{_esc(report.project.name)}</h1>
    <div class="meta">
      <code>{_esc(report.mission_id)}</code> · loop <code>{_esc(report.loop_id)}</code>
      · {_esc(gen)}{stop}
    </div>
    <div class="objective">{_esc(objective)}</div>
  </header>

  {outcome_html}

  <section class="section">
    <h2>What shipped</h2>
    {shipped_html}
  </section>

  <section class="section">
    <h2>Evidence</h2>
    {evidence_html}
  </section>

  <section class="section">
    <h2>Builder work</h2>
    {builder_html}
  </section>

  <section class="section">
    <h2>Critic</h2>
    {critic_html}
  </section>

  <details class="ops-details">
    <summary>Mission ops</summary>
    <div class="ops-body">
      <div class="metrics-block">
        <div class="grid">
          <div class="card">
            <div class="label">Iterations</div>
            <div class="value">{report.iteration}<span style="color:var(--muted);font-size:1rem"> / {report.max_iterations or "—"}</span></div>
            {_bar_html(report.iteration, report.max_iterations)}
          </div>
          <div class="card">
            <div class="label">Spend</div>
            <div class="value">${report.cost_usd:.2f}</div>
            {_bar_html(report.cost_usd, report.max_cost_usd)}
          </div>
          {wall_card}
          <div class="card">
            <div class="label">Agent runs</div>
            <div class="value">{report.agent_runs}</div>
            <div class="sub">engine {_esc(report.engine)}</div>
          </div>
        </div>
        <div class="viz-grid">
          {donut_html}
          {outcome_donut_html}
        </div>
        <div class="viz-grid">
          {iter_bars_html}
        </div>
      </div>
      <h2 style="margin:8px 0 14px;font-size:13px;text-transform:uppercase;letter-spacing:0.1em;color:var(--muted);font-weight:700">Run arc</h2>
      {timeline_html}
      <h2 style="margin:18px 0 14px;font-size:13px;text-transform:uppercase;letter-spacing:0.1em;color:var(--muted);font-weight:700">Changed files</h2>
      {files_html}
    </div>
  </details>

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
        lines.append(f" {_truncate_objective(report.objective, max_len=w - 2)}")
        lines.append(f"{c['cyan']}{'─' * w}{c['reset']}")
    tokens = _fmt_tokens(report.tokens_total)
    critic = _latest_critic(report)
    verdict = (critic.recommendation if critic else "") or "—"
    shipped = _shipped_artifacts(report.highlights, limit=4)
    evidence = _collect_evidence_images(report.highlights, limit=4)
    lines += [
        f" outcome     {_outcome_line(report)[: w - 14]}",
        f" critic      {verdict}",
        f" iterations  {report.iteration}/{report.max_iterations or '—'}  "
        f"{_bar_md(report.iteration, report.max_iterations).replace('`', '')}",
        f" spend       ${report.cost_usd:.2f}"
        + (f" ({tokens})" if tokens else "")
        + f" / ${report.max_cost_usd:.2f}",
        f" delivery    {report.delivery_mode} → {report.delivery_detail}",
        f"{c['cyan']}{'─' * w}{c['reset']}",
        f"{c['bold']} shipped{c['reset']}",
    ]
    if shipped:
        for path in shipped:
            lines.append(f"  · {_short_path(path)}")
    else:
        lines.append("  (none)")
    lines.append(f"{c['bold']} evidence{c['reset']}")
    if evidence:
        for path in evidence:
            lines.append(f"  · {_evidence_caption(path)}")
    else:
        lines.append("  (none)")
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
