from __future__ import annotations

import hashlib
import errno
import io
import json
from pathlib import Path

import pytest

from oopz_overlay.adapters import updater
from oopz_overlay.adapters.updater import (
    UpdateManifest,
    _replace_with_retry,
    download_verified,
    parse_manifest,
    run_update_helper,
    stage_update,
    start_pending_update,
    version_key,
)


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_manifest_requires_acv_https_hash_and_newer_version_shape() -> None:
    payload = b"binary update"
    manifest = parse_manifest(
        json.dumps(
            {
                "version": "0.3.0",
                "url": "https://acv.k-neco.com/tools/oopz-tactical-overlay/OopzTacticalOverlay.exe",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": len(payload),
            }
        ).encode()
    )

    assert manifest.version == "0.3.0"
    assert version_key(manifest.version) > version_key("0.2.0")

    with pytest.raises(ValueError, match="ACV HTTPS"):
        parse_manifest(
            json.dumps(
                {
                    "version": "0.3.0",
                    "url": "https://example.com/update.exe",
                    "sha256": "0" * 64,
                    "size": 1,
                }
            ).encode()
        )


def test_download_is_published_only_after_size_and_hash_verification(tmp_path) -> None:
    payload = b"verified executable bytes"
    manifest = UpdateManifest(
        "0.3.0",
        "https://acv.k-neco.com/tools/oopz-tactical-overlay/OopzTacticalOverlay.exe",
        hashlib.sha256(payload).hexdigest(),
        len(payload),
    )
    target = tmp_path / "update.exe"

    progress: list[tuple[int, int]] = []
    download_verified(
        manifest,
        target,
        opener=lambda _url, _timeout: Response(payload),
        progress=lambda downloaded, total: progress.append((downloaded, total)),
    )

    assert target.read_bytes() == payload
    assert progress == [(0, len(payload)), (len(payload), len(payload))]
    assert not (tmp_path / "update.exe.part").exists()

    bad = UpdateManifest(manifest.version, manifest.url, "0" * 64, len(payload))
    with pytest.raises(ValueError, match="verification"):
        download_verified(bad, target, opener=lambda _url, _timeout: Response(payload))


def test_stage_update_reports_current_download_and_ready_states(
    tmp_path, monkeypatch
) -> None:
    payload = b"new executable"
    manifest = UpdateManifest(
        "9.9.9",
        "https://acv.k-neco.com/tools/oopz-tactical-overlay/OopzTacticalOverlay.exe",
        hashlib.sha256(payload).hexdigest(),
        len(payload),
    )
    monkeypatch.setattr(updater, "fetch_manifest", lambda: manifest)

    current_events = []
    assert stage_update("9.9.9", tmp_path, progress=current_events.append) is None
    assert [event.phase for event in current_events] == ["checking", "current"]

    def fake_download(item, destination, *, progress=None, **_kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        if progress is not None:
            progress(0, item.size)
        destination.write_bytes(payload)
        if progress is not None:
            progress(item.size, item.size)
        return destination

    monkeypatch.setattr(updater, "download_verified", fake_download)
    update_events = []
    assert stage_update("1.0.0", tmp_path, progress=update_events.append) == manifest
    assert [event.phase for event in update_events] == [
        "checking",
        "downloading",
        "downloading",
        "ready",
    ]
    assert update_events[-2].downloaded == len(payload)


def test_stale_pending_update_is_discarded_instead_of_downgrading(
    tmp_path, monkeypatch
) -> None:
    payload = b"older executable"
    source = tmp_path / "updates" / "OopzTacticalOverlay-0.4.0.exe"
    source.parent.mkdir()
    source.write_bytes(payload)
    (tmp_path / "pending-update.json").write_text(
        json.dumps(
            {
                "version": "0.4.0",
                "path": str(source),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": len(payload),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(updater, "is_packaged", lambda: True)

    assert start_pending_update(tmp_path, "0.4.2") is False
    assert not (tmp_path / "pending-update.json").exists()
    assert not source.exists()


def test_locked_executable_replacement_retries(monkeypatch, tmp_path) -> None:
    source = tmp_path / "new.exe"
    target = tmp_path / "app.exe"
    source.write_bytes(b"new")
    target.write_bytes(b"old")
    attempts = 0
    real_replace = updater.os.replace

    def temporarily_locked(incoming, destination) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("still running")
        real_replace(incoming, destination)

    monkeypatch.setattr(updater.os, "replace", temporarily_locked)
    monkeypatch.setattr(updater.time, "sleep", lambda _seconds: None)

    assert _replace_with_retry(source, target, timeout_seconds=1.0)
    assert attempts == 3
    assert target.read_bytes() == b"new"


def test_failed_helper_recovers_old_app_and_records_visible_error(
    tmp_path, monkeypatch
) -> None:
    target = tmp_path / "app.exe"
    source = tmp_path / "bad-update.exe"
    pending = tmp_path / "pending-update.json"
    helper = tmp_path / "helper.exe"
    target.write_bytes(b"old app")
    source.write_bytes(b"corrupt")
    pending.write_text("{}", encoding="utf-8")
    launched: list[list[str]] = []
    monkeypatch.setattr(updater, "_wait_for_process", lambda _pid: None)
    monkeypatch.setattr(updater, "_running_executable", lambda: helper)
    monkeypatch.setattr(
        updater.subprocess,
        "Popen",
        lambda arguments, **_kwargs: launched.append(arguments),
    )

    result = run_update_helper(
        [
            str(target),
            str(source),
            "123",
            str(pending),
            hashlib.sha256(b"expected").hexdigest(),
            str(len(b"expected")),
        ]
    )

    assert result == 21
    assert target.read_bytes() == b"old app"
    assert not pending.exists()
    assert not source.exists()
    assert json.loads((tmp_path / "update-error.json").read_text())["code"] == 21
    assert launched == [[str(target), "--cleanup-updater", str(helper)]]


@pytest.mark.parametrize("corrupt_copy", [False, True])
def test_helper_stages_and_verifies_on_install_volume_before_replacement(
    tmp_path, monkeypatch, corrupt_copy
) -> None:
    download = tmp_path / "C" / "download.exe"
    target = tmp_path / "D" / "installed.exe"
    download.parent.mkdir()
    target.parent.mkdir()
    payload = b"verified new version"
    download.write_bytes(payload)
    target.write_bytes(b"working old version")
    pending = download.parent / "pending-update.json"
    pending.write_text("{}")
    launched = []
    real_replace = updater.os.replace
    real_copy = updater.shutil.copyfile

    def replace_on_same_volume(source, destination):
        if not Path(source).is_relative_to(target.parent):
            raise OSError(errno.EXDEV, "different Windows volumes")
        assert Path(source).read_bytes() == payload
        assert target.read_bytes() == b"working old version"
        real_replace(source, destination)

    def copy(source, destination):
        real_copy(source, destination)
        if corrupt_copy:
            Path(destination).write_bytes(b"incomplete copy")

    monkeypatch.setattr(updater.os, "replace", replace_on_same_volume)
    monkeypatch.setattr(updater.shutil, "copyfile", copy)
    monkeypatch.setattr(updater, "_wait_for_process", lambda _pid: None)
    monkeypatch.setattr(updater, "_launch_target", launched.append)
    result = run_update_helper(
        [
            str(target),
            str(download),
            "0",
            str(pending),
            hashlib.sha256(payload).hexdigest(),
            str(len(payload)),
        ]
    )
    assert result == (22 if corrupt_copy else 0)
    assert target.read_bytes() == (b"working old version" if corrupt_copy else payload)
    assert not pending.exists()
    assert not list(target.parent.glob(".zhitiao-update-*"))
    assert launched == [target]
