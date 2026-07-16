"""Provider adapters: grok (reference), claude, codex."""
from __future__ import annotations

from typing import Dict

from .base import ProviderAdapter
from .grok import GrokAdapter
from .claude import ClaudeAdapter
from .codex import CodexAdapter

ADAPTERS: Dict[str, type] = {
    "grok": GrokAdapter,
    "claude": ClaudeAdapter,
    "codex": CodexAdapter,
}


def make_adapter(name: str, provider_config: dict) -> ProviderAdapter:
    if name not in ADAPTERS:
        raise ValueError(f"unknown provider {name!r}; expected one of {sorted(ADAPTERS)}")
    return ADAPTERS[name](provider_config)
