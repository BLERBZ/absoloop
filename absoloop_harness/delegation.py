"""Two-layer team guidance: Absoloop owns outer orchestration; the Builder
CLI is the team lead and must fan out with native subagents / agent teams
on complex work."""
from __future__ import annotations

_POSTURE = {
    "claude": (
        "## Builder role — you are the team lead\n"
        "Agent Teams are enabled. You are the Builder / lead, not a solo coder.\n"
        "For any multi-file, multi-component, or larger build (new feature, "
        "multi-game polish, cross-layer change, research+implement+test):\n"
        "1. Decompose into independent slices.\n"
        "2. Spawn teammates NOW with the Task tool (one message, multiple "
        "Task calls) — e.g. implementer, tester, polisher, reviewer.\n"
        "3. Give each teammate a clear owned slice and success criteria.\n"
        "4. Coordinate via the shared task list / SendMessage; synthesize "
        "results yourself.\n"
        "Do NOT implement the whole complex build serially alone. Solo only "
        "true one-file / one-function fixes."
    ),
    "codex": (
        "## Builder role — you are the team lead\n"
        "You are the Builder / lead, not a solo coder. For any multi-file, "
        "multi-component, or larger build: spawn subagents in parallel "
        "(implement / test / polish) before doing the work yourself. Ask for "
        "parallel agents explicitly. Solo only true one-file / one-function fixes."
    ),
    "grok": (
        "## Builder role — you are the team lead\n"
        "You are the Builder / lead, not a solo coder. For any multi-file, "
        "multi-component, or larger build: call `spawn_subagent` in parallel "
        "(research / build / review), prefer worktree isolation when files "
        "would conflict. Solo only true one-file / one-function fixes."
    ),
}

_GENERIC = (
    "## Builder role — you are the team lead\n"
    "For multi-file or larger builds, spawn native teammates / subagents in "
    "parallel and coordinate. Solo only true one-file / one-function fixes."
)


def delegation_posture(provider: str) -> str:
    """Engine-aware prompt block: Builder must lead a team on complex work."""
    return _POSTURE.get(provider, _GENERIC)


def with_delegation(prompt: str, provider: str, profile: str) -> str:
    """Append team-lead posture for write profiles; critics/readers stay lean."""
    if profile == "read":
        return prompt
    block = delegation_posture(provider)
    if not block.strip():
        return prompt
    return f"{prompt.rstrip()}\n\n{block}\n"
