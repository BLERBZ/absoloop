"""Harness configuration: absoloop.toml with project / user / CLI override
precedence and per-value source tracking for `absoloop config`.
"""
from __future__ import annotations

import copy
import os
import pathlib
from typing import Any, Dict, List, Optional, Tuple

from . import toml_lite

PROVIDERS = ("grok", "claude", "codex")

DEFAULTS: Dict[str, Any] = {
    "providers": {
        "grok": {"command": "grok", "model": "", "timeout_seconds": 1800,
                 "env_allowlist": []},
        "claude": {"command": "claude", "model": "", "timeout_seconds": 1800,
                   "env_allowlist": []},
        "codex": {"command": "codex", "model": "", "timeout_seconds": 1800,
                  "env_allowlist": [],
                  # exec-resume | exec-flags-then-resume — see docs/multi-provider.md
                  "resume_style": "exec-resume"},
    },
    "permissions": {"default_profile": "edit"},
    "gates": {
        "required": ["tests"],
        "commands": {
            "tests": "python3 -m unittest discover -s tests",
            "lint": "",
            "typecheck": "",
            "format": "",
            "security": "",
        },
    },
    "workflows": {
        "planner": "claude",
        "reviewer": "codex",
        "implementers": ["grok", "claude", "codex"],
        "integrator": "claude",
    },
    "artifacts": {"keep_worktrees": False, "retention_runs": 20},
}

USER_CONFIG = pathlib.Path(os.environ.get("ABSOLOOP_USER_CONFIG",
                                          str(pathlib.Path.home() / ".absoloop" / "absoloop.toml")))


class Config:
    """Resolved configuration plus the source of every value
    (default < user < project < cli)."""

    def __init__(self, values: Dict[str, Any], sources: Dict[str, str]):
        self.values = values
        self.sources = sources

    def get(self, *path: str, default: Any = None) -> Any:
        node: Any = self.values
        for part in path:
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def source(self, *path: str) -> str:
        return self.sources.get(".".join(path), "default")

    def flat(self) -> List[Tuple[str, Any, str]]:
        rows: List[Tuple[str, Any, str]] = []

        def walk(node: Dict[str, Any], prefix: str) -> None:
            for key in sorted(node):
                value = node[key]
                dotted = f"{prefix}{key}"
                if isinstance(value, dict):
                    walk(value, dotted + ".")
                else:
                    rows.append((dotted, value, self.sources.get(dotted, "default")))

        walk(self.values, "")
        return rows


def _merge(base: Dict[str, Any], overlay: Dict[str, Any],
           sources: Dict[str, str], label: str, prefix: str = "") -> None:
    for key, value in overlay.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value, sources, label, dotted + ".")
        else:
            base[key] = value
            if isinstance(value, dict):
                for sub, _val, _src in Config(value, {}).flat():
                    sources[f"{dotted}.{sub}"] = label
            else:
                sources[dotted] = label


def load_config(project_root: pathlib.Path,
                cli_overrides: Optional[Dict[str, Any]] = None) -> Config:
    values = copy.deepcopy(DEFAULTS)
    sources: Dict[str, str] = {}

    for path, label in ((USER_CONFIG, "user"),
                        (project_root / "absoloop.toml", "project")):
        if path.is_file():
            _merge(values, toml_lite.loads(path.read_text(encoding="utf-8")),
                   sources, label)

    if cli_overrides:
        _merge(values, cli_overrides, sources, "cli")

    return Config(values, sources)
