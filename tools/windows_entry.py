from __future__ import annotations

import os
import sys
import traceback
import re
from datetime import UTC, datetime
from pathlib import Path


def _diagnostic_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    path = root / "RinChan" / "OopzTacticalOverlay" / "startup.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _record(message: str) -> None:
    timestamp = datetime.now(UTC).isoformat()
    message = re.sub(r"eyJ[\w-]+\.[\w-]+\.[\w-]+", "[redacted]", message)
    try:
        path = _diagnostic_path()
        if path.exists() and path.stat().st_size > 262144:
            path.replace(path.with_suffix(".log.1"))
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"{timestamp} pid={os.getpid()} {message}\n")
    except OSError:
        pass


def _startup_copy(value: str) -> str:
    return value


def _unhandled_exception(exception_type, exception, traceback_object) -> None:
    details = "".join(
        traceback.format_exception(exception_type, exception, traceback_object)
    ).rstrip()
    _record(f"UNHANDLED\n{details}")


if __name__ == "__main__":
    sys.excepthook = _unhandled_exception
    _record(f"START argv={sys.argv[1:]!r}")
    try:
        from oopz_overlay.i18n import tr as _startup_copy
        from oopz_overlay.main import main

        exit_code = main()
    except Exception:
        _unhandled_exception(*sys.exc_info())
        if os.name == "nt":
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                _startup_copy("纸条启动失败，请重新下载后再试。详情见 startup.log。"),
                _startup_copy("纸条"),
                0x10,
            )
        raise
    _record(f"EXIT code={exit_code}")
    one_shot_modes = {
        "--smoke-test",
        "--render-preview",
        "--render-settings",
        "--sdk-import-probe",
    }
    if one_shot_modes.intersection(sys.argv):
        os._exit(exit_code)
    raise SystemExit(exit_code)
