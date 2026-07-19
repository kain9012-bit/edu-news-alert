from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import winreg
except ImportError:  # pragma: no cover - Windows-only module
    winreg = None


MORNING_TASK = "오늘의 교육동향 자동 수신 - 오전"
LOGON_RUN_VALUE = "EduNewsAlertDownloader"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
INSTALLED_EXE_NAME = "오늘의 교육동향 자동 수신기.exe"


def install_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Programs" / "EduNewsAlertDownloader"


def ensure_installed_executable() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    target_dir = install_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / INSTALLED_EXE_NAME
    source = Path(sys.executable).resolve()
    if not target.exists() or source != target.resolve():
        shutil.copy2(source, target)
    return target


def launch_command(mode: str, install_copy: bool = False) -> str:
    if getattr(sys, "frozen", False):
        executable = ensure_installed_executable() if install_copy else Path(sys.executable)
        return f'"{executable}" {mode}'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    launcher = Path(__file__).resolve().parent / "run_downloader.pyw"
    return f'"{pythonw}" "{launcher}" {mode}'


def _run_schtasks(arguments: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["schtasks.exe", *arguments],
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _install_logon_entry(command: str) -> None:
    if winreg is None:
        raise RuntimeError("Windows에서만 로그인 자동 실행을 등록할 수 있습니다.")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, LOGON_RUN_VALUE, 0, winreg.REG_SZ, command)


def _remove_logon_entry() -> None:
    if winreg is None:
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, LOGON_RUN_VALUE)
    except FileNotFoundError:
        pass


def install_tasks() -> None:
    morning_command = launch_command("--scheduled", install_copy=True)
    logon_command = launch_command("--startup-check", install_copy=True)
    _run_schtasks([
        "/Create", "/F",
        "/TN", MORNING_TASK,
        "/TR", morning_command,
        "/SC", "WEEKLY",
        "/D", "MON,TUE,WED,THU,FRI",
        "/ST", "09:15",
        "/RL", "LIMITED",
    ])
    try:
        _install_logon_entry(logon_command)
    except Exception:
        _run_schtasks(["/Delete", "/F", "/TN", MORNING_TASK], check=False)
        _remove_logon_entry()
        raise


def remove_tasks() -> None:
    _run_schtasks(["/Delete", "/F", "/TN", MORNING_TASK], check=False)
    _remove_logon_entry()