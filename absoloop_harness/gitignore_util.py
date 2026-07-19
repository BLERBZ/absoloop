"""Project `.gitignore` helpers for Absoloop mission state.

The mission directory is ``.absoloop/`` (dot-prefixed). Operators sometimes
say "/absoloop"; we always recommend the real path ``.absoloop/``.
"""
from __future__ import annotations

import pathlib
from typing import Literal

from .briefing import ask, tint

# Canonical gitignore entry for mission state (runtime, reports, ledgers, tmp).
IGNORE_ENTRY = ".absoloop/"
IGNORE_BLOCK = (
    "# Absoloop mission state — runtime, reports, ledgers, live telemetry\n"
    f"{IGNORE_ENTRY}\n"
)

Result = Literal["added", "exists", "skipped", "declined", "no_project"]


def _normalize_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines()]


def already_ignores_absoloop(text: str) -> bool:
    """True when `.gitignore` already covers the mission directory."""
    for line in _normalize_lines(text):
        if line.startswith("#"):
            continue
        if line in (
            ".absoloop/",
            ".absoloop",
            "/.absoloop/",
            "/.absoloop",
            "**/.absoloop/",
            "**/.absoloop",
        ):
            return True
    return False


def ensure_absoloop_gitignore(
    project: pathlib.Path,
    *,
    yes: bool = False,
    ask_user: bool = True,
) -> Result:
    """Ensure ``.absoloop/`` is listed in the project's ``.gitignore``.

    With ``ask_user`` (TTY) and not ``yes``, prompts for approval and prints a
    short recommendation. ``yes`` / non-interactive best-effort adds the entry.
    """
    root = project.resolve()
    if not root.is_dir():
        return "no_project"

    gitignore = root / ".gitignore"
    existing = ""
    if gitignore.is_file():
        try:
            existing = gitignore.read_text(encoding="utf-8")
        except OSError:
            existing = ""

    if already_ignores_absoloop(existing):
        return "exists"

    # Recommend even when only `.absoloop/tmp/` was present historically —
    # full ignore keeps ledgers, reports, and live telemetry out of git.
    recommend = (
        "Recommended: ignore the Absoloop mission folder so runtime state, "
        "reports, ledgers, and live telemetry are not committed."
    )

    if ask_user and not yes:
        import sys
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            ask_user = False

    if ask_user and not yes:
        print()
        print("  " + tint("bold", "Gitignore · Absoloop mission folder"))
        print(tint("dim", f"  {recommend}"))
        print()
        print(tint("dim", "  Will append to .gitignore:"))
        for line in IGNORE_BLOCK.strip().splitlines():
            print(tint("dim", f"    {line}"))
        print()
        answer = ask(
            "  Add `.absoloop/` to .gitignore? [Y/n]",
            "y",
        ).strip().lower()
        if answer in ("n", "no", "skip"):
            print(tint("dim", "  Skipped — you can add it later."))
            return "declined"

    try:
        body = existing
        if body and not body.endswith("\n"):
            body += "\n"
        if body:
            body += "\n"
        body += IGNORE_BLOCK
        gitignore.write_text(body, encoding="utf-8")
    except OSError:
        return "skipped"
    return "added"
