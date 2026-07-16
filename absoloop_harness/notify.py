"""Minimal out-of-CLI alerts: a short chime + optional desktop banner.

Fire-and-forget. Never blocks the mission loop. Disable with ABSOLOOP_CHIME=0.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Optional

# macOS system sounds (always present on stock macOS).
_MAC_SOUNDS = {
    "attention": "/System/Library/Sounds/Glass.aiff",
    "done": "/System/Library/Sounds/Hero.aiff",
    "fail": "/System/Library/Sounds/Basso.aiff",
}


def enabled() -> bool:
    raw = os.environ.get("ABSOLOOP_CHIME")
    if raw is not None:
        return raw.strip().lower() not in ("0", "false", "no", "off")
    # Quiet in CI; interactive terminals get chimes by default.
    if os.environ.get("CI", "").strip().lower() in ("1", "true", "yes"):
        return False
    return True


def notify(title: str, body: str = "", *, kind: str = "attention") -> None:
    """Chime (and banner when the OS supports it). Safe to call anywhere."""
    if not enabled():
        return
    kind = kind if kind in _MAC_SOUNDS else "attention"
    try:
        _chime(kind)
    except Exception:
        pass
    try:
        _banner(title, body)
    except Exception:
        pass


def _spawn(argv: list[str]) -> None:
    subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _chime(kind: str) -> None:
    if sys.platform == "darwin":
        path = _MAC_SOUNDS.get(kind) or _MAC_SOUNDS["attention"]
        if os.path.isfile(path) and shutil.which("afplay"):
            _spawn(["afplay", path])
            return
    if sys.platform.startswith("linux"):
        for player, args in (
            ("paplay", ["/usr/share/sounds/freedesktop/stereo/complete.oga"]),
            ("pw-play", ["/usr/share/sounds/freedesktop/stereo/complete.oga"]),
            ("aplay", ["/usr/share/sounds/alsa/Front_Left.wav"]),
        ):
            if shutil.which(player) and os.path.isfile(args[0]):
                _spawn([player, *args])
                return
    if os.name == "nt":
        try:
            import winsound  # type: ignore
            # Asynchronous system default beep.
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            return
        except Exception:
            pass
    # Last resort: terminal BEL (may be audible even when the pane is buried).
    try:
        sys.stdout.write("\a")
        sys.stdout.flush()
    except Exception:
        pass


def _banner(title: str, body: str) -> None:
    title = (title or "AbsoLoop")[:80]
    body = (body or "")[:160]
    if sys.platform == "darwin" and shutil.which("osascript"):
        # AppleScript strings: escape backslash and quote only.
        def esc(text: str) -> str:
            return text.replace("\\", "\\\\").replace('"', '\\"')
        script = f'display notification "{esc(body)}" with title "{esc(title)}"'
        _spawn(["osascript", "-e", script])
        return
    if sys.platform.startswith("linux") and shutil.which("notify-send"):
        _spawn(["notify-send", "--app-name=AbsoLoop", title, body or title])
        return
    if os.name == "nt":
        # PowerShell toast is heavy; MessageBeep already covered sound.
        return


def kind_for_status(status: str) -> str:
    if status == "AWAITING_APPROVAL":
        return "attention"
    if status == "COMPLETED":
        return "done"
    if status in ("BLOCKED", "REJECTED", "BUDGET_EXHAUSTED"):
        return "fail"
    return "attention"


def notify_mission(status: str, mission_id: str = "",
                   detail: Optional[str] = None) -> None:
    """Convenience for mission-loop terminal states."""
    kind = kind_for_status(status)
    titles = {
        "AWAITING_APPROVAL": "AbsoLoop — needs your approval",
        "COMPLETED": "AbsoLoop — mission complete",
        "BLOCKED": "AbsoLoop — mission blocked",
        "REJECTED": "AbsoLoop — mission rejected",
        "BUDGET_EXHAUSTED": "AbsoLoop — budget exhausted",
    }
    title = titles.get(status, f"AbsoLoop — {status}")
    body = detail or (mission_id and f"{mission_id}: {status}") or status
    notify(title, body, kind=kind)
