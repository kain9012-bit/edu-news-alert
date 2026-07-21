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
FALLBACK_TASK = "오늘의 교육동향 자동 수신 - 보완"
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


def _create_weekday_task(
    name: str,
    command: str,
    start_time: str,
    repeat_minutes: int = 0,
    duration: str = "",
) -> None:
    arguments = [
        "/Create", "/F",
        "/TN", name,
        "/TR", command,
        "/SC", "WEEKLY",
        "/D", "MON,TUE,WED,THU,FRI",
        "/ST", start_time,
        "/RL", "LIMITED",
    ]
    if repeat_minutes:
        arguments += ["/RI", str(repeat_minutes), "/DU", duration or "01:00"]
    _run_schtasks(arguments)
    _enable_wake_and_catchup(name)


def _enable_wake_and_catchup(name: str) -> None:
    """출근 후 부팅·절전 해제로 실행 시각을 놓쳐도 복귀 즉시 따라잡게 한다."""
    script = (
        f"$t = Get-ScheduledTask -TaskName '{name}';"
        "$t.Settings.WakeToRun = $false;"
        "$t.Settings.StartWhenAvailable = $true;"
        "$t.Settings.DisallowStartIfOnBatteries = $false;"
        "$t.Settings.StopIfGoingOnBatteries = $false;"
        "Set-ScheduledTask -InputObject $t | Out-Null"
    )
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        # 부가 설정이므로 실패해도 예약 작업 등록 자체는 유지한다.
        pass


def install_tasks() -> None:
    scheduled_command = launch_command("--scheduled", install_copy=True)
    logon_command = launch_command("--startup-check", install_copy=True)
    # 배포는 텔레그램으로 이미 끝난 뒤이므로, 수신기는 출근 시각(09:00)에 맞춰
    # 09:10부터 09:50까지 5분 간격으로 확인해 원본 파일을 폴더에 보관한다.
    _create_weekday_task(MORNING_TASK, scheduled_command, "09:10", repeat_minutes=5, duration="00:40")
    try:
        _create_weekday_task(FALLBACK_TASK, scheduled_command, "10:00", repeat_minutes=10, duration="01:00")
        _install_logon_entry(logon_command)
    except Exception:
        _run_schtasks(["/Delete", "/F", "/TN", MORNING_TASK], check=False)
        _run_schtasks(["/Delete", "/F", "/TN", FALLBACK_TASK], check=False)
        _remove_logon_entry()
        raise


def remove_tasks() -> None:
    _run_schtasks(["/Delete", "/F", "/TN", MORNING_TASK], check=False)
    _run_schtasks(["/Delete", "/F", "/TN", FALLBACK_TASK], check=False)
    _remove_logon_entry()