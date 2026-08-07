"""생성된 '오늘의 교육동향' 보고서를 공개 아카이브(public/reports)로 발행한다.

내부 보고서 생성이 끝나면 이 스크립트가 그날 HTML·JSON을 public/reports/<날짜>.*로
복사하고 public/reports/index.json 목록을 갱신한다. GitHub Pages가 이 폴더를 배포하면
과거 보고서를 날짜별로 다시 볼 수 있다. 텔레그램 발송과 같은 산출물을 재사용하므로
AI 재생성 비용이 추가로 들지 않는다.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="보고서를 공개 아카이브로 발행")
    parser.add_argument("--report-dir", required=True, help="생성된 보고서(HTML·JSON) 디렉터리")
    parser.add_argument("--public-dir", default="public", help="GitHub Pages 공개 디렉터리")
    parser.add_argument("--retention-days", type=int, default=0, help="0이면 전체 보관")
    return parser.parse_args()


def _find(report_dir: Path, suffix: str) -> Path | None:
    files = sorted(p for p in report_dir.iterdir() if p.is_file() and p.suffix.lower() == suffix)
    return files[0] if files else None


def _report_date(meta: dict[str, Any], fallback_name: str) -> str:
    window_end = str(meta.get("windowEnd") or "")[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", window_end):
        return window_end
    match = re.search(r"(\d{4})(\d{2})(\d{2})", fallback_name)
    if match:
        return "-".join(match.groups())
    raise ValueError("보고서 날짜를 확인할 수 없습니다.")


def publish(report_dir: Path, public_dir: Path, retention_days: int = 0) -> str:
    html_path = _find(report_dir, ".html")
    json_path = _find(report_dir, ".json")
    if html_path is None or json_path is None:
        raise FileNotFoundError("보고서 HTML 또는 JSON을 찾을 수 없습니다.")

    meta = json.loads(json_path.read_text(encoding="utf-8")).get("metadata", {})
    date = _report_date(meta, html_path.name)

    reports_dir = public_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(html_path, reports_dir / f"{date}.html")
    shutil.copyfile(json_path, reports_dir / f"{date}.json")

    index_path = reports_dir / "index.json"
    entries: list[dict[str, Any]] = []
    if index_path.exists():
        try:
            loaded = json.loads(index_path.read_text(encoding="utf-8"))
            entries = [e for e in loaded.get("reports", []) if isinstance(e, dict) and e.get("date") != date]
        except json.JSONDecodeError:
            entries = []

    entries.append(
        {
            "date": date,
            "title": str(meta.get("title", "오늘의 교육동향")),
            "windowStart": meta.get("windowStart"),
            "windowEnd": meta.get("windowEnd"),
            "trendCount": int(meta.get("publishedCount", 0) or 0),
            "ownOfficeCount": int(meta.get("ownOfficePublishedCount", 0) or 0),
            "generatedAt": meta.get("generatedAt"),
        }
    )
    entries.sort(key=lambda e: str(e.get("date", "")), reverse=True)

    if retention_days and retention_days > 0:
        keep = entries[:retention_days]
        for stale in entries[retention_days:]:
            for suffix in (".html", ".json"):
                stale_file = reports_dir / f"{stale.get('date')}{suffix}"
                if stale_file.exists():
                    stale_file.unlink()
        entries = keep

    index_path.write_text(
        json.dumps({"updatedAt": date, "reports": entries}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return date


def main() -> int:
    args = parse_args()
    date = publish(Path(args.report_dir), Path(args.public_dir), args.retention_days)
    print(f"공개 아카이브 발행 완료: reports/{date}.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
