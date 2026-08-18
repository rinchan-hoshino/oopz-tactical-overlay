from __future__ import annotations

import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

from oopz_overlay.main import main


def _diagnostic_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    path = root / "RinChan" / "OopzTacticalOverlay" / "startup.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _record(message: str) -> None:
    timestamp = datetime.now(UTC).isoformat()
    with _diagnostic_path().open("a", encoding="utf-8") as stream:
        stream.write(f"{timestamp} pid={os.getpid()} {message}\n")


def _unhandled_exception(exception_type, exception, traceback_object) -> None:
    details = "".join(
        traceback.format_exception(exception_type, exception, traceback_object)
    ).rstrip()
    _record(f"UNHANDLED\n{details}")


if __name__ == "__main__":
    sys.excepthook = _unhandled_exception
    _record(f"START argv={sys.argv[1:]!r}")
    try:
        exit_code = main()
    except BaseException:
        _unhandled_exception(*sys.exc_info())
        raise
    _record(f"EXIT code={exit_code}")
    raise SystemExit(exit_code)
