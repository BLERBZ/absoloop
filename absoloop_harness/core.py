"""absoloop-core: provider-neutral request, capability, event, result,
session, permission, and artifact types, plus secret redaction.

Pure stdlib, no I/O — every other harness module builds on these types.
"""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class EventType(str, enum.Enum):
    RUN_STARTED = "run_started"
    TEXT_DELTA = "text_delta"
    # Provider-supplied progress/reasoning *summary* — never hidden
    # chain-of-thought, which the harness neither requires nor displays.
    PROGRESS = "progress"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    FILE_CHANGED = "file_changed"
    APPROVAL_REQUESTED = "approval_requested"
    USAGE = "usage"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    # Opaque unknown-provider event kept for forward compatibility.
    UNKNOWN = "unknown"


@dataclass
class AgentEvent:
    type: EventType
    provider: str
    text: str = ""                     # human-facing detail (redacted)
    data: Dict[str, Any] = field(default_factory=dict)  # structured payload (redacted)
    raw_type: str = ""                 # the provider's own event type string
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "provider": self.provider,
            "text": self.text,
            "data": self.data,
            "raw_type": self.raw_type,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Provider identity and capabilities
# ---------------------------------------------------------------------------

@dataclass
class ProviderInfo:
    name: str                          # "grok" | "claude" | "codex"
    executable: Optional[str]          # resolved path, None when not found
    version: str = ""
    auth_hint: str = ""                # human hint, never a credential


@dataclass
class ProviderCapabilities:
    streaming_json: bool = False
    session_resume: bool = False
    structured_output: bool = False
    permission_modes: bool = False
    native_sandbox: bool = False
    turn_limit: bool = False
    prompt_via_stdin: bool = False
    cost_reporting: bool = False

    def to_json(self) -> Dict[str, bool]:
        return dataclasses.asdict(self)


@dataclass
class ProviderProbe:
    info: ProviderInfo
    capabilities: ProviderCapabilities
    problems: List[str] = field(default_factory=list)   # actionable issues

    @property
    def available(self) -> bool:
        return self.info.executable is not None


# ---------------------------------------------------------------------------
# Requests, sessions, results
# ---------------------------------------------------------------------------

PERMISSION_PROFILES = ("read", "edit", "full")


class PermissionMappingError(Exception):
    """No safe provider-native mapping exists for the requested profile.

    Adapters raise this before spawning anything: fail closed."""


@dataclass
class AgentRequest:
    prompt: str
    cwd: str
    permission_profile: str = "edit"
    model: str = ""
    timeout_seconds: float = 1800.0
    max_turns: int = 0                 # 0 = provider default
    extra_env: Dict[str, str] = field(default_factory=dict)  # allowlisted only

    def prompt_hash(self) -> str:
        return hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()[:16]


@dataclass
class SessionRef:
    provider: str
    native_id: str                     # provider's own session/thread id


@dataclass
class RunResult:
    run_id: str
    provider: str
    status: str                        # "completed" | "failed" | "cancelled" | "timeout"
    exit_code: Optional[int]
    session: Optional[SessionRef]
    final_text: str = ""
    usage: Dict[str, Any] = field(default_factory=dict)
    cost_usd: Optional[float] = None   # None = unreported, never "free"
    duration_seconds: float = 0.0
    events_count: int = 0

    def to_json(self) -> Dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["session"] = dataclasses.asdict(self.session) if self.session else None
        return payload


def new_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


# ---------------------------------------------------------------------------
# Secret redaction
# ---------------------------------------------------------------------------

# Env var *names* whose values must never appear anywhere.
_SECRET_NAME = re.compile(
    r"(TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|API_?KEY|AUTH|PRIVATE)", re.IGNORECASE)

# Literal token shapes redacted from free text regardless of origin.
_SECRET_LITERALS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),          # OpenAI/Anthropic style
    re.compile(r"\bxai-[A-Za-z0-9_-]{8,}"),         # xAI API keys
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"),    # GitHub tokens
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),  # Slack tokens
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),            # AWS access key ids
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
]

REDACTED = "[REDACTED]"


def is_secret_name(name: str) -> bool:
    return bool(_SECRET_NAME.search(name))


def redact_text(text: str, extra_values: Optional[List[str]] = None) -> str:
    """Strip token-shaped literals and any explicitly-known secret values."""
    if not text:
        return text
    for value in extra_values or []:
        if value and len(value) >= 6:
            text = text.replace(value, REDACTED)
    for pattern in _SECRET_LITERALS:
        text = pattern.sub(REDACTED, text)
    return text


def redact_env(env: Dict[str, str]) -> Dict[str, str]:
    """Env snapshot safe for logs/manifests: secret-named values redacted."""
    return {key: (REDACTED if is_secret_name(key) else value)
            for key, value in env.items()}


def secret_values(env: Dict[str, str]) -> List[str]:
    """The values (not names) that must never appear in any artifact."""
    return [value for key, value in env.items()
            if is_secret_name(key) and value]


def redact_event(event: AgentEvent, extra_values: Optional[List[str]] = None) -> AgentEvent:
    event.text = redact_text(event.text, extra_values)
    event.data = _redact_value(event.data, extra_values)
    return event


def _redact_value(value: Any, extra_values: Optional[List[str]]) -> Any:
    if isinstance(value, str):
        return redact_text(value, extra_values)
    if isinstance(value, dict):
        return {k: (REDACTED if isinstance(k, str) and is_secret_name(k)
                    else _redact_value(v, extra_values))
                for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(item, extra_values) for item in value]
    return value
