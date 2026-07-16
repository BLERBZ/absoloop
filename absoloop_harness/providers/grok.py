"""Grok Build adapter — the reference adapter.

Transport: headless `grok --prompt-file <f> --output-format streaming-json`.
Long prompts always travel via --prompt-file (per Grok's own guidance);
resume maps SessionRef.native_id to `-r/--resume`. Auth stays native: the
grok CLI reads ~/.grok/auth.json or XAI_API_KEY itself; Absoloop never
touches either.

Grok streaming-json events (docs: user-guide/14-headless-mode.md):
  {"type":"text","data":"..."}          -> TEXT_DELTA
  {"type":"thought","data":"..."}       -> PROGRESS (provider-supplied summary)
  {"type":"end", ... sessionId, usage}  -> USAGE + RUN_COMPLETED
  {"type":"error","message":"..."}      -> RUN_FAILED
Anything else (e.g. max_turns_reached, auto_compact_*) -> UNKNOWN.
"""
from __future__ import annotations

import os
import pathlib
from typing import Any, Dict, List, Optional

from ..core import (AgentEvent, AgentRequest, EventType, PermissionMappingError,
                    ProviderCapabilities, SessionRef)
from ..process import write_prompt_file
from .base import ProviderAdapter


class GrokAdapter(ProviderAdapter):
    name = "grok"
    capabilities = ProviderCapabilities(
        streaming_json=True, session_resume=True, structured_output=True,
        permission_modes=True, native_sandbox=True, turn_limit=True,
        prompt_via_stdin=False, cost_reporting=True)

    def auth_hint(self) -> str:
        if os.environ.get("XAI_API_KEY"):
            return "XAI_API_KEY set"
        grok_home = pathlib.Path(
            os.environ.get("GROK_HOME", str(pathlib.Path.home() / ".grok")))
        auth = grok_home / "auth.json"
        if auth.is_file():
            return f"cached login found ({auth})"
        return "no credentials detected — run 'grok login' or set XAI_API_KEY"

    def map_permissions(self, profile: str) -> List[str]:
        self.check_profile(profile)
        if profile == "read":
            # Tool allowlist restricts to read-only tools; no approval bypass.
            return ["--tools", "read_file,grep,list_dir,glob"]
        if profile == "edit":
            # Auto-approve edits/writes inside the worktree, keep dangerous
            # shell patterns denied; no blanket bypass.
            return ["--allow", "Edit", "--allow", "Write", "--allow", "Read",
                    "--allow", "Grep", "--allow", "Bash",
                    "--deny", "Bash(sudo*)", "--deny", "Bash(rm -rf /*)"]
        if profile == "full":
            return ["--yolo"]
        raise PermissionMappingError(f"no grok mapping for profile {profile!r}")

    def build_argv(self, request: AgentRequest, resume: Optional[SessionRef],
                   workdir: pathlib.Path):
        prompt_path = write_prompt_file(workdir, request.prompt)
        argv = [self.argv_program(),
                "--prompt-file", str(prompt_path),
                "--output-format", "streaming-json",
                "--cwd", request.cwd,
                "--no-auto-update"]
        model = request.model or self.config.get("model") or ""
        if model:
            argv += ["-m", model]
        if request.max_turns:
            argv += ["--max-turns", str(request.max_turns)]
        if resume is not None:
            argv += ["--resume", resume.native_id]
        argv += self.map_permissions(request.permission_profile)
        return argv, None

    def normalize(self, raw: Dict[str, Any]) -> List[AgentEvent]:
        etype = str(raw.get("type", ""))
        if "_absoloop_unparsed" in raw:
            return [AgentEvent(type=EventType.UNKNOWN, provider=self.name,
                               text=raw["_absoloop_unparsed"][:200],
                               raw_type="_unparsed", data=raw)]
        if etype == "text":
            return [AgentEvent(type=EventType.TEXT_DELTA, provider=self.name,
                               text=str(raw.get("data", "")), raw_type=etype)]
        if etype == "thought":
            return [AgentEvent(type=EventType.PROGRESS, provider=self.name,
                               text=str(raw.get("data", "")), raw_type=etype)]
        if etype == "end":
            session_id = str(raw.get("sessionId", "") or "")
            if session_id:
                self.last_session = SessionRef(provider=self.name, native_id=session_id)
            self.last_result_payload = raw
            events: List[AgentEvent] = []
            if isinstance(raw.get("usage"), dict):
                events.append(AgentEvent(
                    type=EventType.USAGE, provider=self.name, raw_type=etype,
                    data={"usage": raw["usage"],
                          "num_turns": raw.get("num_turns"),
                          "total_cost_usd": raw.get("total_cost_usd")}))
            events.append(AgentEvent(
                type=EventType.RUN_COMPLETED, provider=self.name, raw_type=etype,
                text=f"stop reason: {raw.get('stopReason', '?')}",
                data={"session_id": session_id,
                      "stop_reason": raw.get("stopReason")}))
            return events
        if etype == "error":
            return [AgentEvent(type=EventType.RUN_FAILED, provider=self.name,
                               text=str(raw.get("message", "engine error")),
                               raw_type=etype, data=raw)]
        return [AgentEvent(type=EventType.UNKNOWN, provider=self.name,
                           raw_type=etype or "?", data=raw)]
