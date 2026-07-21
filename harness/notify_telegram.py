"""생성된 내부 보고서를 텔레그램으로 발송한다.

PC를 켜지 않아도 휴대폰에서 바로 확인하고 메신저로 전달할 수 있도록,
GitHub Actions가 HTML(기본 배포본)과 HWPX를 텔레그램 문서로 보낸다.
토큰과 대화 ID는 저장소 Secret으로만 전달하며 로그에 남기지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests


API_BASE = "https://api.telegram.org"
CAPTION_LIMIT = 1024
SEND_TIMEOUT = 120


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="내부 보고서를 텔레그램으로 발송")
    parser.add_argument("--report-dir", required=True, help="보고서 파일이 있는 디렉터리")
    parser.add_argument(
        "--documents",
        default="html,hwpx",
        help="발송할 확장자 목록(쉼표 구분). 예: html 또는 html,hwpx",
    )
    return parser.parse_args()


def find_report_files(report_dir: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for path in sorted(report_dir.iterdir()):
        if not path.is_file():
            continue
        suffix = path.suffix.lower().lstrip(".")
        if suffix in {"json", "html", "hwpx"} and suffix not in files:
            files[suffix] = path
    return files


def read_metadata(json_path: Path | None) -> dict[str, Any]:
    if json_path is None or not json_path.exists():
        return {}
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def date_label(window_end: Any) -> str:
    text = str(window_end or "")[:10]
    parts = text.split("-")
    if len(parts) != 3:
        return "날짜 미상"
    return f"{parts[0]}년 {int(parts[1])}월 {int(parts[2])}일"


def build_caption(report: dict[str, Any]) -> str:
    metadata = report.get("metadata", {})
    items = report.get("items", [])
    validation = report.get("validation", {}).get("status", "")

    lines = [
        f"오늘의 교육동향 · {date_label(metadata.get('windowEnd'))}",
        f"교육동향 {len(items)}건 · 제외 {metadata.get('omittedCount', 0)}건 · 검증 {validation}",
    ]
    if items:
        lines.append("")
        for index, item in enumerate(items, 1):
            title = str(item.get("title", "")).strip()
            source = str(item.get("source", "")).strip()
            entry = f"{index}. {title}" + (f" ({source})" if source else "")
            candidate = "\n".join(lines + [entry])
            if len(candidate) > CAPTION_LIMIT - 40:
                lines.append(f"… 외 {len(items) - index + 1}건")
                break
            lines.append(entry)
    else:
        lines.append("")
        lines.append("검증을 통과한 교육동향이 없습니다.")

    caption = "\n".join(lines)
    return caption[: CAPTION_LIMIT - 1] if len(caption) >= CAPTION_LIMIT else caption


def send_document(token: str, chat_id: str, path: Path, caption: str = "") -> None:
    url = f"{API_BASE}/bot{token}/sendDocument"
    data: dict[str, str] = {"chat_id": chat_id, "disable_notification": "false"}
    if caption:
        data["caption"] = caption
    with path.open("rb") as handle:
        response = requests.post(
            url,
            data=data,
            files={"document": (path.name, handle)},
            timeout=SEND_TIMEOUT,
        )
    if response.status_code != 200:
        # 응답 본문에는 토큰이 포함되지 않으므로 그대로 출력해도 안전하다.
        raise RuntimeError(f"텔레그램 발송 실패({response.status_code}): {response.text[:300]}")


def main() -> int:
    args = parse_args()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("텔레그램 Secret이 없어 발송을 건너뜁니다.", file=sys.stderr)
        return 0

    report_dir = Path(args.report_dir)
    if not report_dir.is_dir():
        raise FileNotFoundError(f"보고서 디렉터리를 찾을 수 없습니다: {report_dir}")

    files = find_report_files(report_dir)
    caption = build_caption(read_metadata(files.get("json")))
    wanted = [item.strip().lower() for item in args.documents.split(",") if item.strip()]

    sent = 0
    for index, suffix in enumerate(wanted):
        path = files.get(suffix)
        if path is None:
            print(f"{suffix} 파일이 없어 건너뜁니다.", file=sys.stderr)
            continue
        send_document(token, chat_id, path, caption if index == 0 else "")
        print(f"텔레그램 발송 완료: {path.name}")
        sent += 1

    if sent == 0:
        raise RuntimeError("발송할 보고서 파일이 없습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
