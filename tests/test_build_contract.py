from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_release_includes_and_probes_only_the_sdk_transport() -> None:
    build_source = (ROOT / "tools" / "build_windows.py").read_text(encoding="utf-8")
    entry_source = (ROOT / "tools" / "windows_entry.py").read_text(encoding="utf-8")
    main_source = (ROOT / "src" / "oopz_overlay" / "main.py").read_text(
        encoding="utf-8"
    )
    gateway_source = (ROOT / "src" / "oopz_overlay" / "gateway.py").read_text(
        encoding="utf-8"
    )

    assert '"--include-package=oopz_sdk"' in build_source
    assert '"--sdk-import-probe"' in build_source
    assert '"--sdk-import-probe"' in entry_source
    assert 'importlib.import_module("oopz_sdk")' in main_source
    assert "uiautomation" not in build_source
    assert "comtypes" not in build_source
    assert "WindowsOopzBackend" not in gateway_source
