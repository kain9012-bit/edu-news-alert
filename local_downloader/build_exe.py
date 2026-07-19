from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "local_downloader" / "dist"
WORK = ROOT / ".tmp" / "downloader-build"
SPEC = ROOT / ".tmp" / "downloader-spec"


def main() -> int:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "오늘의 교육동향 자동 수신기",
        "--distpath",
        str(DIST),
        "--workpath",
        str(WORK),
        "--specpath",
        str(SPEC),
        str(ROOT / "local_downloader" / "run_downloader.pyw"),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    print(DIST / "오늘의 교육동향 자동 수신기.exe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
