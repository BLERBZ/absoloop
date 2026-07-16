"""Claude Code adapter.

Transport: `claude -p --output-format stream-json --verbose` with the prompt
delivered over stdin (Claude Code reads it in print mode). Resume maps
SessionRef.native_id to `--resume`. Auth is native: the claude CLI manages
its own login; Absoloop never reads or copies its credential store.

Do not vendor or copy Claude Code implementation code — this adapter only
speaks the CLI's documented flags and stream format.

stream-json events:
  {"type":"system","subtype":"init","session_id":...,"model":...} -> RUN_STARTED
  {"type":"assistant","message":{"content":[...]}}                -> TEXT_DELTA / TOOL_STARTED / FILE_CHANGED
  {"type":"user","message":{"content":[tool_result...]}}          -> TOOL_COMPLETED
  {"type":"result","is_error":bool,...,"usage","total_cost_usd"}  -> USAGE + RUN_COMPLETED/RUN_FAILED
"""
from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Optional

from ..core import (AgentEvent, AgentRequest, EventType, PermissionMappingError,
                    ProviderCapabilities, SessionRef)
from .base import ProviderAdapter

_FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


class ClaudeAdapter(ProviderAdapter):
    name = "claude"
    capabilities = ProviderCapabilities(
        streaming_json=True, session_resume=True, structured_output=True,
        permission_modes=True, native_sandbox=False, turn_limit=True,
        prompt_via_stdin=True, cost_reporting=True)

    def map_permissions(self, profile: str) -> List[str]:
        self.check_profile(profile)
        mapping = {
            "read": ["--permission-mode", "plan"],
            "edit": ["--permission-mode", "acceptEdits"],
            "full": ["--permission-mode", "bypassPermissions"],
        }
        if profile not in mapping:
            raise PermissionMappingError(f"no claude mapping for profile {profile!r}")
        return mapping[profile]

    def build_argv(self, request: AgentRequest, resume: Optional[SessionRef],
                   workdir: pathlib.Path):
        argv = [self.executable() or self.config.get("command", "claude"),
                "-p", "--output-format", "stream-json", "--verbose"]
        model = request.model or self.config.get("model") or ""
        if model:
            argv += ["--model", model]
        if request.max_turns:
            argv += ["--max-turns", str(request.max_turns)]
        if resume is not None:
            argv += ["--resume", resume.native_id]
        argv += self.map_permissions(request.permission_profile)
        return argv, request.prompt

    def normalize(self, raw: Dict[str, Any]) -> List[AgentEvent]:
        etype = str(raw.get("type", ""))
        if "_absoloop_unparsed" in raw:
            return [AgentEvent(type=EventType.UNKNOWN, provider=self.name,
                               text=raw["_absoloop_unparsed"][:200],
                               raw_type="_unparsed", data=raw)]
        if etype == "system" and raw.get("subtype") == "init":
            session_id = str(raw.get("session_id", "") or "")
            if session_id:
                self.last_session = SessionRef(provider=self.name, native_id=session_id)
            return [AgentEvent(type=EventType.RUN_STARTED, provider=self.name,
                               text=f"session started (model {raw.get('model', '?')})",
                               raw_type="system/init",
                               data={"session_id": session_id,
                                     "model": raw.get("model")})]
        if etype == "assistant":
            return self._assistant_events(raw)
        if etype == "user":
            return self._tool_results(raw)
        if etype == "result":
            return self._result_events(raw)
        return [AgentEvent(type=EventType.UNKNOWN, provider=self.name,
                           raw_type=etype or "?", data=raw)]

    def _assistant_events(self, raw: Dict[str, Any]) -> List[AgentEvent]:
        message = raw.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        events: List[AgentEvent] = []
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and str(block.get("text", "")).strip():
                events.append(AgentEvent(type=EventType.TEXT_DELTA, provider=self.name,
                                         text=str(block["text"]), raw_type="assistant/text"))
            elif block.get("type") == "tool_use":
                tool = str(block.get("name", "tool"))
                tool_input = block.get("input") if isinstance(block.get("input"), dict) else {}
                events.append(AgentEvent(
                    type=EventType.TOOL_STARTED, provider=self.name,
                    text=tool, raw_type="assistant/tool_use",
                    data={"tool": tool, "id": block.get("id"), "input": tool_input}))
                if tool in _FILE_TOOLS and tool_input.get("file_path"):
                    events.append(AgentEvent(
                        type=EventType.FILE_CHANGED, provider=self.name,
                        text=str(tool_input["file_path"]),
                        raw_type="assistant/tool_use",
                        data={"path": tool_input["file_path"], "tool": tool}))
        return events

    def _tool_results(self, raw: Dict[str, Any]) -> List[AgentEvent]:
        message = raw.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        events: List[AgentEvent] = []
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                events.append(AgentEvent(
                    type=EventType.TOOL_COMPLETED, provider=self.name,
                    raw_type="user/tool_result",
                    data={"tool_use_id": block.get("tool_use_id"),
                          "is_error": bool(block.get("is_error"))}))
        return events

    def _result_events(self, raw: Dict[str, Any]) -> List[AgentEvent]:
        session_id = str(raw.get("session_id", "") or "")
        if session_id:
            self.last_session = SessionRef(provider=self.name, native_id=session_id)
        self.last_result_payload = raw
        events: List[AgentEvent] = []
        if isinstance(raw.get("usage"), dict) or raw.get("total_cost_usd") is not None:
            events.append(AgentEvent(
                type=EventType.USAGE, provider=self.name, raw_type="result",
                data={"usage": raw.get("usage"),
                      "num_turns": raw.get("num_turns"),
                      "total_cost_usd": raw.get("total_cost_usd")}))
        failed = bool(raw.get("is_error"))
        events.append(AgentEvent(
            type=EventType.RUN_FAILED if failed else EventType.RUN_COMPLETED,
            provider=self.name, raw_type="result",
            text=str(raw.get("result", ""))[:2000],
            data={"session_id": session_id, "subtype": raw.get("subtype")}))
        return events
