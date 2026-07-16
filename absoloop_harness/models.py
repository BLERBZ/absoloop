"""Curated engine models — Absoloop defaults to the best available per engine.

Aliases track each CLI's own "best / flagship" naming where it exists
(Claude `best`, Codex Sol, Grok Build). Operators can still pick a
lighter tier or type a custom id at the mission / run briefing.
"""
from __future__ import annotations

from typing import Dict, Sequence, Tuple

# First entry in each tuple is the Absoloop default ("best available").
ENGINE_MODELS: Dict[str, Tuple[str, ...]] = {
    # Claude Code: `best` → Fable 5 when the org has it, else latest Opus.
    "claude": ("best", "fable", "opus", "sonnet", "haiku"),
    # Codex: Sol is the GPT-5.6 flagship coding model.
    "codex": ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"),
    # Grok Build: purpose-built coding model for the CLI.
    "grok": ("grok-build-0.1",),
}

MODEL_LABELS: Dict[str, Dict[str, str]] = {
    "claude": {
        "best": "highest available (Fable 5 → Opus)",
        "fable": "Claude Fable 5 — longest-horizon agents",
        "opus": "latest Opus — complex coding",
        "sonnet": "latest Sonnet — fast daily work",
        "haiku": "latest Haiku — quick / cheap",
    },
    "codex": {
        "gpt-5.6-sol": "flagship — complex / open-ended",
        "gpt-5.6-terra": "balanced everyday coding",
        "gpt-5.6-luna": "fast / high-volume",
    },
    "grok": {
        "grok-build-0.1": "Grok Build coding model",
    },
}


def models_for(engine: str) -> Tuple[str, ...]:
    return ENGINE_MODELS.get(engine, ())


def default_model(engine: str) -> str:
    """Best model Absoloop will request for this engine."""
    models = models_for(engine)
    return models[0] if models else ""


def model_labels(engine: str) -> Dict[str, str]:
    return dict(MODEL_LABELS.get(engine, {}))


def resolve_model(engine: str, requested: str = "") -> str:
    """Return a usable model id — requested if set, else engine best."""
    requested = (requested or "").strip()
    return requested or default_model(engine)


def all_known_models() -> Sequence[str]:
    seen = []
    for models in ENGINE_MODELS.values():
        for model in models:
            if model not in seen:
                seen.append(model)
    return seen
