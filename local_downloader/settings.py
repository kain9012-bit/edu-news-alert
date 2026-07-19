from __future__ import annotations

import base64
import ctypes
import json
import os
from ctypes import wintypes
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable


APP_DIR_NAME = "EduNewsAlertDownloader"
CONFIG_FILENAME = "config.json"
STATE_FILENAME = "state.json"
LOG_FILENAME = "downloader.log"
DEFAULT_REPOSITORY = "kain9012-bit/edu-news-alert-private-reports"


class DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


@dataclass(frozen=True)
class DownloaderSettings:
    repository: str
    save_root: str
    auto_receive: bool = True
    lookback_days: int = 14


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_DIR_NAME


def config_path() -> Path:
    return app_data_dir() / CONFIG_FILENAME


def state_path() -> Path:
    return app_data_dir() / STATE_FILENAME


def log_path() -> Path:
    return app_data_dir() / LOG_FILENAME


def default_save_root() -> Path:
    return Path.home() / "Documents" / "오늘의 교육동향"


def _input_blob(payload: bytes) -> tuple[DataBlob, object]:
    buffer = (ctypes.c_ubyte * len(payload)).from_buffer_copy(payload)
    return DataBlob(len(payload), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def protect_secret(secret: str) -> str:
    if os.name != "nt":
        raise RuntimeError("Windows에서만 GitHub 토큰을 저장할 수 있습니다.")
    input_blob, input_buffer = _input_blob(secret.encode("utf-8"))
    output_blob = DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        "EduNewsAlertDownloader",
        None,
        None,
        None,
        0x01,
        ctypes.byref(output_blob),
    )
    _ = input_buffer
    if not ok:
        raise ctypes.WinError()
    try:
        return base64.b64encode(ctypes.string_at(output_blob.pbData, output_blob.cbData)).decode("ascii")
    finally:
        kernel32.LocalFree(output_blob.pbData)


def unprotect_secret(encoded: str) -> str:
    if os.name != "nt":
        raise RuntimeError("Windows에서만 GitHub 토큰을 읽을 수 있습니다.")
    input_blob, input_buffer = _input_blob(base64.b64decode(encoded.encode("ascii")))
    output_blob = DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0x01,
        ctypes.byref(output_blob),
    )
    _ = input_buffer
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData).decode("utf-8")
    finally:
        kernel32.LocalFree(output_blob.pbData)


def load_settings(
    path: Path | None = None,
    unprotect: Callable[[str], str] = unprotect_secret,
) -> tuple[DownloaderSettings | None, str]:
    target = path or config_path()
    if not target.is_file():
        return None, ""
    payload = json.loads(target.read_text(encoding="utf-8"))
    settings = DownloaderSettings(
        repository=str(payload.get("repository", DEFAULT_REPOSITORY)),
        save_root=str(payload.get("save_root", default_save_root())),
        auto_receive=bool(payload.get("auto_receive", True)),
        lookback_days=max(1, min(30, int(payload.get("lookback_days", 14)))),
    )
    encoded = str(payload.get("encrypted_github_token", ""))
    return settings, unprotect(encoded) if encoded else ""


def save_settings(
    settings: DownloaderSettings,
    github_token: str,
    path: Path | None = None,
    protect: Callable[[str], str] = protect_secret,
) -> None:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(settings)
    payload["encrypted_github_token"] = protect(github_token.strip())
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, target)