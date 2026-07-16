"""Two-layer team guidance: Absoloop owns outer orchestration; each provider
CLI is prompted to fan out with its native subagents / agent teams."""
from __future__ import annotations

_POSTURE = {
    "claude": (
        "## Native delegation (Claude Agent Teams)\n"
        "Agent Teams are enabled for this session. When the task fans out across "
        "independent workstreams (research, implement, test, review), spawn "
        "teammates in parallel rather than doing every step serially. Keep the "
        "lead focused on coordination and synthesis; give each teammate a clear "
        "owned slice. Do not spawn teams for trivial single-file edits."
    ),
    "codex": (
        "## Native delegation (Codex subagents)\n"
        "When the task fans out across independent workstreams, spawn subagents "
        "in parallel (e.g. explore vs implement vs test) rather than serial tool "
        "loops. Ask for parallel agents explicitly when useful. Do not spawn "
        "subagents for trivial single-file edits."
    ),
    "grok": (
        "## Native delegation (Grok subagents)\n"
        "When the task fans out across independent workstreams, use "
        "`spawn_subagent` in parallel (research / build / review) rather than "
        "serial tool loops. Prefer worktree isolation when subagents would "
        "conflict on the same files. Do not spawn subagents for trivial "
        "single-file edits."
    ),
}

_GENERIC = (
    "## Native delegation\n"
    "When the task fans out across independent workstreams, spawn native "
    "subagents or teammates in parallel rather than serial tool loops. "
    "Do not spawn workers for trivial single-file edits."
)


def delegation_posture(provider: str) -> str:
    """Engine-aware prompt block encouraging heavy native team/subagent use."""
    return _POSTURE.get(provider, _GENERIC)


def with_delegation(prompt: str, provider: str, profile: str) -> str:
    """Append delegation posture for write profiles; critics/readers stay lean."""
    if profile == "read":
        return prompt
    block = delegation_posture(provider)
    if not block.strip():
        return prompt
    return f"{prompt.rstrip()}\n\n{block}\n"
