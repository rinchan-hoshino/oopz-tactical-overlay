from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

MANIFEST_URL = "https://acv.k-neco.com/tools/oopz-tactical-overlay/latest.json"
USER_AGENT = "OopzTacticalOverlay-Updater/1"


def is_packaged() -> bool:
    return bool(getattr(sys, "frozen", False) or "__compiled__" in globals())


def _running_executable() -> Path:
    if is_packaged():
        return Path(sys.argv[0]).resolve()
    return Path(sys.executable).resolve()


def _clean_onefile_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("NUITKA_ONEFILE_PARENT", None)
    return environment


@dataclass(frozen=True, slots=True)
class UpdateManifest:
    version: str
    url: str
    sha256: str
    size: int


@dataclass(frozen=True, slots=True)
class UpdateProgress:
    phase: str
    version: str = ""
    downloaded: int = 0
    total: int = 0


def version_key(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError as exc:
        raise ValueError("version must contain only decimal components") from exc


def parse_manifest(payload: bytes) -> UpdateManifest:
    data = json.loads(payload.decode("utf-8"))
    manifest = UpdateManifest(
        version=str(data["version"]),
        url=str(data["url"]),
        sha256=str(data["sha256"]).casefold(),
        size=int(data["size"]),
    )
    version_key(manifest.version)
    if not manifest.url.startswith("https://acv.k-neco.com/"):
        raise ValueError("update URL must use the ACV HTTPS origin")
    if len(manifest.sha256) != 64 or any(
        character not in "0123456789abcdef" for character in manifest.sha256
    ):
        raise ValueError("invalid update SHA-256")
    if manifest.size <= 0:
        raise ValueError("invalid update size")
    return manifest


def _open(url: str, timeout: float) -> BinaryIO:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=timeout)


def fetch_manifest(
    *,
    opener: Callable[[str, float], BinaryIO] = _open,
    timeout: float = 6.0,
) -> UpdateManifest:
    with opener(MANIFEST_URL, timeout) as response:
        return parse_manifest(response.read())


def download_verified(
    manifest: UpdateManifest,
    destination: Path,
    *,
    opener: Callable[[str, float], BinaryIO] = _open,
    timeout: float = 25.0,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    digest = hashlib.sha256()
    size = 0
    try:
        with opener(manifest.url, timeout) as response, temporary.open("wb") as output:
            if progress is not None:
                progress(0, manifest.size)
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
                if progress is not None:
                    progress(size, manifest.size)
        if size != manifest.size or digest.hexdigest() != manifest.sha256:
            raise ValueError("downloaded update failed size or SHA-256 verification")
        temporary.replace(destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def stage_update(
    current_version: str,
    state_root: Path,
    *,
    progress: Callable[[UpdateProgress], None] | None = None,
) -> UpdateManifest | None:
    if progress is not None:
        progress(UpdateProgress("checking"))
    manifest = fetch_manifest()
    if version_key(manifest.version) <= version_key(current_version):
        if progress is not None:
            progress(UpdateProgress("current", current_version))
        return None
    update_path = state_root / "updates" / f"OopzTacticalOverlay-{manifest.version}.exe"

    def report_download(downloaded: int, total: int) -> None:
        if progress is not None:
            progress(UpdateProgress("downloading", manifest.version, downloaded, total))

    download_verified(manifest, update_path, progress=report_download)
    pending = {
        "version": manifest.version,
        "path": str(update_path),
        "sha256": manifest.sha256,
        "size": manifest.size,
    }
    pending_path = state_root / "pending-update.json"
    temporary = pending_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(pending, separators=(",", ":")), encoding="utf-8")
    temporary.replace(pending_path)
    if progress is not None:
        progress(
            UpdateProgress("ready", manifest.version, manifest.size, manifest.size)
        )
    return manifest


def _verify_file(path: Path, sha256: str, size: int) -> bool:
    if not path.is_file() or path.stat().st_size != size:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest() == sha256


def _wait_for_process(process_id: int, timeout_seconds: float = 60.0) -> None:
    if os.name != "nt":
        return
    import ctypes

    synchronize = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, process_id)
    if handle:
        try:
            ctypes.windll.kernel32.WaitForSingleObject(
                handle, int(timeout_seconds * 1000)
            )
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)


def _replace_with_retry(
    source: Path, target: Path, *, timeout_seconds: float = 60.0
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            os.replace(source, target)
            return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.25)


def _launch_target(target: Path) -> None:
    subprocess.Popen(
        [str(target), "--cleanup-updater", str(_running_executable())],
        env=_clean_onefile_environment(),
    )


def _record_update_error(pending_path: Path, code: int, message: str) -> None:
    error_path = pending_path.with_name("update-error.json")
    error_path.write_text(
        json.dumps({"code": code, "message": message}, separators=(",", ":")),
        encoding="utf-8",
    )


def run_update_helper(arguments: list[str]) -> int:
    target = Path(arguments[0])
    source = Path(arguments[1])
    parent_pid = int(arguments[2])
    pending_path = Path(arguments[3])
    expected_sha = arguments[4]
    expected_size = int(arguments[5])
    error_path = pending_path.with_name("update-error.json")
    _wait_for_process(parent_pid)
    if not _verify_file(source, expected_sha, expected_size):
        pending_path.unlink(missing_ok=True)
        source.unlink(missing_ok=True)
        _record_update_error(pending_path, 21, "download verification failed")
        _launch_target(target)
        return 21
    if not _replace_with_retry(source, target):
        pending_path.unlink(missing_ok=True)
        _record_update_error(pending_path, 22, "target executable remained locked")
        _launch_target(target)
        return 22
    pending_path.unlink(missing_ok=True)
    error_path.unlink(missing_ok=True)
    _launch_target(target)
    return 0


def start_pending_update(state_root: Path, current_version: str) -> bool:
    if not is_packaged():
        return False
    pending_path = state_root / "pending-update.json"
    if not pending_path.is_file():
        return False
    try:
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        pending_version = str(pending["version"])
        source = Path(pending["path"])
        sha256 = str(pending["sha256"])
        size = int(pending["size"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        pending_path.unlink(missing_ok=True)
        return False
    if version_key(pending_version) <= version_key(current_version):
        pending_path.unlink(missing_ok=True)
        source.unlink(missing_ok=True)
        return False
    if not _verify_file(source, sha256, size):
        pending_path.unlink(missing_ok=True)
        source.unlink(missing_ok=True)
        return False

    updater = (
        Path(tempfile.gettempdir()) / f"OopzTacticalOverlay-updater-{os.getpid()}.exe"
    )
    executable = _running_executable()
    shutil.copy2(executable, updater)
    subprocess.Popen(
        [
            str(updater),
            "--apply-update",
            str(executable),
            str(source),
            str(os.getpid()),
            str(pending_path),
            sha256,
            str(size),
        ],
        env=_clean_onefile_environment(),
    )
    return True


def cleanup_updater_later(path: Path) -> None:
    def remove() -> None:
        for _attempt in range(20):
            try:
                path.unlink(missing_ok=True)
                return
            except OSError:
                time.sleep(0.25)

    threading.Thread(target=remove, name="updater-cleanup", daemon=True).start()
