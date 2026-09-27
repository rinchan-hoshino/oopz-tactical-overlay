import sys
from types import SimpleNamespace

import pytest

from oopz_overlay import sounds


def test_sounds_come_from_installed_media_and_keep_theme_paths(tmp_path, monkeypatch):
    media = tmp_path / "Media"
    theme = media / "Theme"
    theme.mkdir(parents=True)
    (media / "Windows Notify.wav").write_bytes(b"wave")
    (theme / "Windows Notify.wav").write_bytes(b"other wave")
    (media / "readme.txt").write_text("not audio")
    monkeypatch.setattr(sounds, "_media_root", lambda: media)

    available = dict((key, label) for label, key in sounds.system_sounds())

    assert set(available) == {"Windows Notify.wav", "Theme/Windows Notify.wav"}
    assert len(set(available.values())) == 2


def test_playback_is_async_does_not_overlap_and_preview_can_interrupt(
    tmp_path, monkeypatch
):
    path = tmp_path / "notify.wav"
    path.write_bytes(b"wave")
    calls = []
    backend = SimpleNamespace(
        SND_FILENAME=0x20000,
        SND_ASYNC=1,
        SND_NODEFAULT=2,
        SND_NOSTOP=16,
        PlaySound=lambda *args: calls.append(args),
    )
    monkeypatch.setattr(sounds, "_media_root", lambda: tmp_path)
    monkeypatch.setitem(sys.modules, "winsound", backend)

    assert sounds.play_sound("notify.wav")
    assert calls[-1] == (str(path), 0x20013)
    assert sounds.play_sound("notify.wav", preview=True)
    assert calls[-1] == (str(path), 0x20003)
    for key in ("", "missing.wav", "../outside.wav", "notify.mp3"):
        assert not sounds.play_sound(key)
    assert len(calls) == 2


@pytest.mark.parametrize("error", [OSError, RuntimeError])
def test_unavailable_audio_never_interrupts_chat(tmp_path, monkeypatch, error):
    (tmp_path / "notify.wav").write_bytes(b"wave")
    monkeypatch.setattr(sounds, "_media_root", lambda: tmp_path)

    def fail(*args):
        raise error("audio device unavailable")

    monkeypatch.setitem(
        sys.modules,
        "winsound",
        SimpleNamespace(
            SND_FILENAME=0x20000,
            SND_ASYNC=1,
            SND_NODEFAULT=2,
            SND_NOSTOP=16,
            PlaySound=fail,
        ),
    )
    assert not sounds.play_sound("notify.wav")
