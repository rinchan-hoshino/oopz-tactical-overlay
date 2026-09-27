"""Discover and play the sounds installed with the current Windows system."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _media_root() -> Path | None:
    if sys.platform != "win32":
        return None
    return Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Media"


def system_sounds() -> list[tuple[str, str]]:
    """Return display names and relative filenames, without bundling audio."""
    root = _media_root()
    if root is None:
        return []
    try:
        files = sorted(root.rglob("*.wav"), key=lambda path: str(path).casefold())
        return [
            (
                str(path.relative_to(root).with_suffix("")),
                path.relative_to(root).as_posix(),
            )
            for path in files
            if path.is_file() and path.resolve().is_relative_to(root.resolve())
        ]
    except OSError:
        return []


def play_sound(key: str, *, preview: bool = False) -> bool:
    root = _media_root()
    if not key or root is None:
        return False
    try:
        path = (root / key).resolve()
        if (
            not path.is_relative_to(root.resolve())
            or path.suffix.casefold() != ".wav"
            or not path.is_file()
        ):
            return False
        import winsound

        flags = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
        if not preview:
            flags |= winsound.SND_NOSTOP
        winsound.PlaySound(str(path), flags)
        return True
    except (OSError, RuntimeError, ValueError):
        # A removed file, busy sound, or unavailable device must not affect chat.
        return False
