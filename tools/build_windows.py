from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = "OopzTacticalOverlay"
PUBLIC_BASE = "https://acv.k-neco.com/tools/oopz-tactical-overlay"


def main() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = str(project["project"]["version"])
    windows_version = ".".join([*version.split("."), "0"])
    dist = ROOT / "dist"
    release = ROOT / "release"
    build = ROOT / "build" / "nuitka"
    for directory in (dist, build):
        shutil.rmtree(directory, ignore_errors=True)
    dist.mkdir(parents=True)
    build.mkdir(parents=True)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "nuitka",
            "--mode=onefile",
            "--onefile-cache-mode=cached",
            f"--onefile-tempdir-spec={{CACHE_DIR}}/RinChan/{PRODUCT}/{{VERSION}}",
            f"--onefile-windows-splash-screen-image={ROOT / 'assets' / 'splash.png'}",
            "--assume-yes-for-downloads",
            "--enable-plugin=pyside6",
            "--windows-console-mode=disable",
            f"--windows-icon-from-ico={ROOT / 'assets' / 'icon.ico'}",
            f"--output-dir={dist}",
            f"--output-filename={PRODUCT}.exe",
            "--company-name=RinChan",
            "--product-name=Oopz Tactical Link",
            "--file-description=Oopz tactical text HUD",
            f"--file-version={windows_version}",
            f"--product-version={windows_version}",
            "--copyright=Copyright 2026 RinChan",
            "--include-package=uiautomation",
            "--include-package-data=certifi",
            f"--report={build / 'compilation-report.xml'}",
            str(ROOT / "tools" / "windows_entry.py"),
        ],
        cwd=ROOT,
        check=True,
    )

    built = dist / f"{PRODUCT}.exe"
    release.mkdir(parents=True, exist_ok=True)
    target = release / f"{PRODUCT}.exe"
    shutil.copy2(built, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest = {
        "schemaVersion": 1,
        "version": version,
        "url": f"{PUBLIC_BASE}/{PRODUCT}.exe",
        "sha256": digest,
        "size": target.stat().st_size,
        "publishedAt": datetime.now(UTC).isoformat(),
    }
    (release / "latest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Release: {target}")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
