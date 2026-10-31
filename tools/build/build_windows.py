from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PRODUCT = "OopzTacticalOverlay"
PUBLIC_BASE = "https://acv.k-neco.com/tools/oopz-tactical-overlay"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--incremental", action="store_true", help="Reuse Nuitka's build cache"
    )
    options = parser.parse_args()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = str(project["project"]["version"])
    windows_version = ".".join([*version.split("."), "0"])
    dist = ROOT / "dist"
    release = ROOT / "release"
    build = ROOT / "build" / "nuitka"
    if not options.incremental:
        for directory in (dist, build):
            shutil.rmtree(directory, ignore_errors=True)
    dist.mkdir(parents=True, exist_ok=True)
    build.mkdir(parents=True, exist_ok=True)
    icon_path = ROOT / 'src' / 'oopz_overlay' / 'assets' / 'icon.ico'

    subprocess.run(
        [
            sys.executable,
            "-m",
            "nuitka",
            "--mode=onefile",
            "--jobs=2",
            "--onefile-cache-mode=cached",
            f"--onefile-tempdir-spec={{CACHE_DIR}}/RinChan/{PRODUCT}/{{VERSION}}",
            "--assume-yes-for-downloads",
            "--enable-plugin=pyside6",
            "--windows-console-mode=disable",
            f"--windows-icon-from-ico={icon_path}",
            f"--output-dir={dist}",
            f"--output-filename={PRODUCT}.exe",
            "--company-name=RinChan",
            "--product-name=纸条 TypeSlip",
            "--file-description=纸条 TypeSlip",
            f"--file-version={windows_version}",
            f"--product-version={windows_version}",
            "--copyright=Copyright 2026 RinChan",
            "--include-package=oopz_sdk",
            # Login comes from the installed Oopz client. The SDK's optional
            # browser login/voice runtime and test fixtures are not used here.
            "--nofollow-import-to=oopz_sdk.testing,playwright,pytest",
            "--include-package-data=certifi",
            "--include-package-data=oopz_overlay",
            f"--report={build / 'compilation-report.xml'}",
            str(ROOT / "tools" / "build" / "windows_entry.py"),
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
        "url": f"{PUBLIC_BASE}/{version}/{PRODUCT}.exe",
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
