from __future__ import annotations

import argparse
import json
import os
import smtplib
import ssl
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Callable


SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


@dataclass(frozen=True)
class ReportFiles:
    json: Path
    html: Path
    hwpx: Path


def discover_report_files(report_dir: Path) -> ReportFiles:
    resolved = report_dir.resolve()
    if not resolved.is_dir():
        raise ValueError(f"보고서 디렉터리를 찾을 수 없습니다: {resolved}")

    found: dict[str, Path] = {}
    for suffix in ("json", "html", "hwpx"):
        matches = sorted(resolved.glob(f"*.{suffix}"))
        if len(matches) != 1:
            raise ValueError(f".{suffix} 보고서 파일은 정확히 1개여야 합니다: {len(matches)}개")
        found[suffix] = matches[0]
    return ReportFiles(**found)


def report_date(files: ReportFiles) -> date:
    payload = json.loads(files.json.read_text(encoding="utf-8"))
    metadata = payload.get("metadata", {})
    raw = str(metadata.get("windowEnd") or metadata.get("generatedAt") or "")[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("보고서 JSON에서 기준 날짜를 확인할 수 없습니다.") from exc


def validate_address(value: str, label: str) -> str:
    address = parseaddr(value.strip())[1]
    if not address or "@" not in address:
        raise ValueError(f"{label} 이메일 주소가 올바르지 않습니다.")
    return address


def build_message(files: ReportFiles, sender: str, recipient: str) -> EmailMessage:
    sender = validate_address(sender, "발신")
    recipient = validate_address(recipient, "수신")
    target_date = report_date(files)
    display_date = f"{target_date.year}년 {target_date.month}월 {target_date.day}일"
    html_body = files.html.read_text(encoding="utf-8")

    message = EmailMessage()
    message["Subject"] = f"[오늘의 교육동향] {display_date}"
    message["From"] = sender
    message["To"] = recipient
    message["X-Education-Trend-Report"] = "daily"
    message["X-Education-Trend-Date"] = target_date.isoformat()
    message.set_content(
        f"{display_date} 오늘의 교육동향 보고서입니다. "
        "HTML을 지원하는 메일에서 본문을 확인하거나 첨부파일을 이용해 주세요."
    )
    message.add_alternative(html_body, subtype="html")
    message.add_attachment(
        files.json.read_bytes(),
        maintype="application",
        subtype="json",
        filename=files.json.name,
    )
    message.add_attachment(
        html_body,
        subtype="html",
        filename=files.html.name,
    )
    message.add_attachment(
        files.hwpx.read_bytes(),
        maintype="application",
        subtype="vnd.hancom.hwpx",
        filename=files.hwpx.name,
    )
    return message


def send_report_email(
    files: ReportFiles,
    sender: str,
    app_password: str,
    recipient: str,
    smtp_factory: Callable[..., smtplib.SMTP_SSL] = smtplib.SMTP_SSL,
) -> None:
    password = app_password.replace(" ", "").strip()
    if not password:
        raise ValueError("Gmail 앱 비밀번호가 비어 있습니다.")
    message = build_message(files, sender, recipient)
    context = ssl.create_default_context()
    with smtp_factory(SMTP_HOST, SMTP_PORT, context=context, timeout=60) as smtp:
        smtp.login(validate_address(sender, "발신"), password)
        smtp.send_message(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="오늘의 교육동향 보고서를 Gmail로 발송")
    parser.add_argument("--report-dir", required=True, help="JSON·HTML·HWPX가 있는 디렉터리")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sender = os.environ.get("GMAIL_SMTP_USER", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    recipient = os.environ.get("REPORT_RECIPIENT", "").strip() or sender
    if not sender:
        raise RuntimeError("GMAIL_SMTP_USER Secret이 필요합니다.")
    if not password:
        raise RuntimeError("GMAIL_APP_PASSWORD Secret이 필요합니다.")

    files = discover_report_files(Path(args.report_dir))
    send_report_email(files, sender, password, recipient)
    print(json.dumps({
        "status": "sent",
        "reportDate": report_date(files).isoformat(),
        "attachments": [files.json.name, files.html.name, files.hwpx.name],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
