from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_release_includes_and_probes_comtypes_runtime() -> None:
    build_source = (ROOT / "tools" / "build_windows.py").read_text(encoding="utf-8")
    entry_source = (ROOT / "tools" / "windows_entry.py").read_text(encoding="utf-8")

    assert '"--include-package=comtypes"' in build_source
    assert '"--nofollow-import-to=comtypes.test"' in build_source
    assert '"--automation-import-probe"' in build_source
    assert '"--automation-import-probe"' in entry_source
