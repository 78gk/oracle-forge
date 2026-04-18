#!/usr/bin/env python3
"""
Download DataAgentBench PATENTS SQLite: patent_publication.db (~5GB) from Google Drive.

Mirrors DataAgentBench/download.sh (same FILE_ID and path). Safe to re-run: skips if the
file already exists and is larger than 5 GiB.

Usage (repo root):

  python scripts/download_patent_publication_db.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUTPUT_PATH = REPO / "DataAgentBench/query_PATENTS/query_dataset/patent_publication.db"
# From DataAgentBench/download.sh — https://drive.google.com/file/d/1pALQ1UH-OwaEUeGYAx47uCyzClfK94XC/view
FILE_ID = "1pALQ1UH-OwaEUeGYAx47uCyzClfK94XC"
MIN_BYTES = 5 * 1024 * 1024 * 1024  # 5 GiB — same threshold as download.sh


def _gdown_missing_instructions() -> None:
    exe = sys.executable
    print(
        "gdown is not available for this Python interpreter.\n"
        f"  {exe}\n\n"
        "Install into the same environment (avoid --user so the venv gets the package):\n"
        f"  {exe} -m pip install gdown\n",
        file=sys.stderr,
    )


def _download_via_module() -> bool:
    try:
        import gdown  # type: ignore[import-not-found]
    except ImportError:
        return False
    url = f"https://drive.google.com/uc?id={FILE_ID}"
    gdown.download(url, str(OUTPUT_PATH), quiet=False)
    return True


def _download_via_cli() -> bool:
    """Use the `gdown` executable on PATH (e.g. user Scripts dir) if the module is not in this venv."""
    cmd = shutil.which("gdown")
    if not cmd:
        return False
    print(f"Using gdown CLI: {cmd}")
    proc = subprocess.run(
        [cmd, "--id", FILE_ID, "-O", str(OUTPUT_PATH)],
        check=False,
    )
    return proc.returncode == 0


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if OUTPUT_PATH.is_file():
        size = OUTPUT_PATH.stat().st_size
        if size > MIN_BYTES:
            print(f"Already present ({size} bytes, > 5 GiB). Skipping: {OUTPUT_PATH}")
            return 0
        print(f"Existing file is smaller than 5 GiB ({size} bytes). Re-downloading...")
        OUTPUT_PATH.unlink()

    print(f"Downloading (~5GB) to {OUTPUT_PATH} ...")

    ok = _download_via_module()
    if not ok:
        ok = _download_via_cli()

    if not ok:
        _gdown_missing_instructions()
        return 1

    if not OUTPUT_PATH.is_file():
        print("ERROR: download finished but file is missing.", file=sys.stderr)
        return 1
    size = OUTPUT_PATH.stat().st_size
    print(f"Done. Size: {size} bytes ({size / (1024**3):.2f} GiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
