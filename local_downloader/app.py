from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import threading
import webbrowser
from datetime import date
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from local_downloader.receiver import (
    ReportDownloadError,
    download_from_github,
    is_weekday,
    report_directory_complete,
    check_github_connection,
    validate_repository,
)
from local_downloader.scheduler import install_tasks, remove_tasks
from local_downloader.settings import (
    DEFAULT_REPOSITORY,
    DownloaderSettings,
    default_save_root,
    load_settings,
    log_path,
    save_settings,
    state_path,
)


APP_TITLE = "오늘의 교육동향 자동 수신기"
TOKEN_URL = "https://github.com/settings/personal-access-tokens/new"


def setup_logging() -> None:
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    handler = logging.handlers.RotatingFileHandler(
        path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root.addHandler(handler)


def run_receiver(mode: str) -> list:
    settings, token = load_settings()
    if settings is None or not token:
        raise ReportDownloadError("먼저 자동 수신기 설정을 저장해 주세요.")
    if mode in ("scheduled", "startup"):
        if not settings.auto_receive:
            logging.info("자동 수신이 꺼져 있어 종료합니다.")
            return []
        if not is_weekday(date.today()):
            logging.info("주말에는 자동 수신을 실행하지 않습니다.")
            return []
    save_root = Path(settings.save_root)
    if mode == "scheduled" and report_directory_complete(save_root, date.today()):
        logging.info("오늘 보고서가 이미 저장되어 GitHub에 접속하지 않습니다.")
        return []
    results = download_from_github(
        repository=settings.repository,
        token=token,
        save_root=save_root,
        state_path=state_path(),
        lookback_days=settings.lookback_days,
    )
    for result in results:
        logging.info(
            "보고서 저장 완료 artifact_id=%s report_id=%s date=%s directory=%s changed=%s",
            result.artifact_id,
            result.report_id,
            result.report_date,
            result.directory,
            result.changed,
        )
    if not results:
        logging.info("새로 받을 교육동향 보고서가 없습니다.")
    return results


class DownloaderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("700x500")
        self.root.minsize(640, 470)
        self.root.option_add("*Font", ("Malgun Gothic", 10))
        self.running = False
        self.saved_token = ""
        self._configure_style()
        self._build_ui()
        self._load()

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Malgun Gothic", 18, "bold"), foreground="#111827")
        style.configure("Primary.TButton", font=("Malgun Gothic", 10, "bold"), padding=(14, 8))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=22)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="GitHub에서 생성된 평일 교육동향 보고서를 지정 폴더에 저장합니다.",
            foreground="#4b5563",
        ).pack(anchor="w", pady=(4, 18))

        form = ttk.LabelFrame(outer, text="GitHub 연결", padding=16)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        self.repository_var = tk.StringVar(value=DEFAULT_REPOSITORY)
        self.token_var = tk.StringVar()
        self.folder_var = tk.StringVar(value=str(default_save_root()))
        self.auto_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="설정을 확인해 주세요.")

        ttk.Label(form, text="비공개 저장소").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.repository_var).grid(
            row=0, column=1, columnspan=2, sticky="ew", padx=(14, 0), pady=6
        )
        ttk.Label(form, text="Actions 읽기 토큰").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.token_var, show="●").grid(
            row=1, column=1, sticky="ew", padx=(14, 8), pady=6
        )
        ttk.Label(form, text="비워두면 저장된 값 유지", foreground="#6b7280").grid(
            row=1, column=2, sticky="w", pady=6
        )
        ttk.Button(form, text="토큰 발급 페이지", command=lambda: webbrowser.open(TOKEN_URL)).grid(
            row=2, column=1, sticky="w", padx=(14, 0), pady=(4, 0)
        )

        folder = ttk.LabelFrame(outer, text="저장 위치", padding=16)
        folder.pack(fill="x", pady=(14, 0))
        folder.columnconfigure(0, weight=1)
        ttk.Entry(folder, textvariable=self.folder_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(folder, text="찾아보기", command=self.choose_folder).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(folder, text="폴더 열기", command=self.open_folder).grid(row=0, column=2, padx=(8, 0))

        options = ttk.Frame(outer)
        options.pack(fill="x", pady=(14, 0))
        ttk.Checkbutton(
            options,
            text="평일 오전 9시 15분과 Windows 로그인 시 누락 보고서 자동 확인",
            variable=self.auto_var,
        ).pack(anchor="w")
        ttk.Label(
            options,
            text="주말에는 실행하지 않으며 최근 14일의 미수신 보고서만 확인합니다.",
            foreground="#6b7280",
        ).pack(anchor="w", pady=(3, 0))

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(18, 0))
        self.save_button = ttk.Button(actions, text="설정 저장", style="Primary.TButton", command=self.save)
        self.save_button.pack(side="left")
        self.test_button = ttk.Button(actions, text="연결 확인", command=self.test_connection)
        self.test_button.pack(side="left", padx=(8, 0))
        self.check_button = ttk.Button(actions, text="지금 확인", command=self.check_now)
        self.check_button.pack(side="left", padx=(8, 0))
        self.disable_button = ttk.Button(actions, text="자동 수신 해제", command=self.disable_auto)
        self.disable_button.pack(side="right")

        status = ttk.LabelFrame(outer, text="상태", padding=14)
        status.pack(fill="both", expand=True, pady=(16, 0))
        ttk.Label(status, textvariable=self.status_var, wraplength=620, justify="left").pack(anchor="w")

    def _load(self) -> None:
        try:
            settings, token = load_settings()
        except Exception as exc:
            self.status_var.set(f"저장된 설정을 읽지 못했습니다: {exc}")
            return
        if settings is None:
            return
        self.repository_var.set(settings.repository)
        self.folder_var.set(settings.save_root)
        self.auto_var.set(settings.auto_receive)
        self.saved_token = token
        if token:
            self.status_var.set("저장된 설정을 불러왔습니다.")
        else:
            self.status_var.set("GitHub Actions 읽기 토큰을 등록해 주세요.")

    def choose_folder(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.folder_var.get() or str(default_save_root()))
        if selected:
            self.folder_var.set(selected)

    def open_folder(self) -> None:
        path = Path(self.folder_var.get().strip() or default_save_root())
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def _current_values(self) -> tuple[DownloaderSettings, str]:
        repository = validate_repository(self.repository_var.get())
        token = self.token_var.get().strip() or self.saved_token
        if not token:
            raise ValueError("비공개 저장소의 Actions 읽기 토큰을 입력해 주세요.")
        folder = Path(self.folder_var.get().strip()).expanduser()
        if not folder.is_absolute():
            raise ValueError("저장 위치는 전체 경로로 지정해 주세요.")
        settings = DownloaderSettings(
            repository=repository,
            save_root=str(folder),
            auto_receive=bool(self.auto_var.get()),
            lookback_days=14,
        )
        return settings, token

    def _save_values(self, register_tasks: bool) -> tuple[DownloaderSettings, str]:
        settings, token = self._current_values()
        Path(settings.save_root).mkdir(parents=True, exist_ok=True)
        save_settings(settings, token)
        self.saved_token = token.strip()
        self.token_var.set("")
        if register_tasks:
            if settings.auto_receive:
                install_tasks()
            else:
                remove_tasks()
        return settings, self.saved_token

    def save(self) -> None:
        try:
            self._save_values(register_tasks=True)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"설정을 저장하지 못했습니다.\n\n{exc}")
            return
        self.status_var.set("설정을 저장하고 Windows 자동 수신 일정을 등록했습니다.")
        messagebox.showinfo(APP_TITLE, "설정을 저장했습니다.")

    def _set_running(self, value: bool, text: str | None = None) -> None:
        self.running = value
        state = "disabled" if value else "normal"
        for button in (self.save_button, self.test_button, self.check_button, self.disable_button):
            button.configure(state=state)
        if text:
            self.status_var.set(text)

    def _background(self, work, success_text) -> None:
        if self.running:
            return
        try:
            settings, token = self._save_values(register_tasks=False)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        self._set_running(True, "GitHub에 연결하고 있습니다...")

        def runner():
            try:
                result = work(settings, token)
            except Exception as exc:
                self.root.after(0, lambda: self._finish_error(exc))
                return
            self.root.after(0, lambda: self._finish_success(success_text(result)))

        threading.Thread(target=runner, daemon=True).start()

    def _finish_error(self, exc: Exception) -> None:
        self._set_running(False, f"실패: {exc}")
        messagebox.showerror(APP_TITLE, str(exc))

    def _finish_success(self, text: str) -> None:
        self._set_running(False, text)
        messagebox.showinfo(APP_TITLE, text)

    def test_connection(self) -> None:
        self._background(
            lambda settings, token: check_github_connection(settings.repository, token),
            lambda _result: "GitHub 연결에 성공했습니다.",
        )

    def check_now(self) -> None:
        def work(_settings, _token):
            return run_receiver("manual")

        def success(results):
            if not results:
                return "새로 받을 교육동향 보고서가 없습니다."
            dates = ", ".join(result.report_date.isoformat() for result in results)
            return f"보고서 {len(results)}건을 저장했습니다.\n{dates}"

        self._background(work, success)

    def disable_auto(self) -> None:
        if not messagebox.askyesno(APP_TITLE, "Windows 자동 수신 일정을 해제할까요?"):
            return
        try:
            settings, token = self._current_values()
            disabled = DownloaderSettings(
                repository=settings.repository,
                save_root=settings.save_root,
                auto_receive=False,
                lookback_days=settings.lookback_days,
            )
            save_settings(disabled, token)
            remove_tasks()
            self.auto_var.set(False)
            self.saved_token = token
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"자동 수신을 해제하지 못했습니다.\n\n{exc}")
            return
        self.status_var.set("자동 수신 일정을 해제했습니다. 필요할 때 지금 확인을 사용할 수 있습니다.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--scheduled", action="store_true")
    group.add_argument("--startup-check", action="store_true")
    group.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> int:
    setup_logging()
    args = parse_args()
    mode = "scheduled" if args.scheduled else "startup" if args.startup_check else "manual" if args.once else "gui"
    if mode != "gui":
        try:
            run_receiver(mode)
            return 0
        except Exception:
            logging.exception("자동 수신 실행 실패 mode=%s", mode)
            return 1
    root = tk.Tk()
    DownloaderApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())