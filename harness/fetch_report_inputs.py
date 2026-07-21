from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests

from crawler.collect import BRIEFING_HOUR_KST, KST, briefing_window


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="공개 대시보드에서 내부 보고서 입력을 내려받기")
    parser.add_argument("--base-url", default="https://kain9012-bit.github.io/edu-news-alert")
    parser.add_argument("--output", default=".report-input")
    parser.add_argument("--attempts", type=int, default=15)
    parser.add_argument("--interval", type=int, default=120)
    parser.add_argument("--report-date", help="다시 생성할 보고서 기준일(YYYY-MM-DD)")
    return parser.parse_args()


def fetch_json(url: str) -> Any:
    response = requests.get(url, timeout=30, headers={"Cache-Control": "no-cache"})
    response.raise_for_status()
    return response.json()


def historical_source(selection: dict[str, Any], news: Any, report_date: date) -> dict[str, Any]:
    metadata = selection.get("metadata", {})
    if report_date.weekday() >= 5:
        raise ValueError("주말 날짜의 교육동향 보고서는 생성하지 않습니다.")
    # 기준 시각이 바뀌어도 과거 보고서를 다시 만들 수 있도록 날짜만 대조한다.
    if str(metadata.get("windowEnd", ""))[:10] != report_date.isoformat():
        raise ValueError(f"선별 결과의 기준일이 {report_date.isoformat()}과 다릅니다.")
    if metadata.get("validationStatus") != "PASS":
        raise ValueError("검증을 통과하지 않은 선별 결과입니다.")
    if not isinstance(news, list):
        raise ValueError("보도자료 원문 목록 형식이 올바르지 않습니다.")

    selected_ids = {
        str(item.get("newsId"))
        for item in selection.get("selectedItems", [])
        if isinstance(item, dict) and item.get("newsId")
    }
    source_items = [
        item
        for item in news
        if isinstance(item, dict) and str(item.get("id")) in selected_ids
    ]
    found_ids = {str(item.get("id")) for item in source_items}
    missing = sorted(selected_ids - found_ids)
    if missing:
        raise ValueError("보관 기간이 지나 원문을 찾을 수 없습니다: " + ", ".join(missing[:5]))
    return {
        "windowStart": metadata.get("windowStart"),
        "windowEnd": metadata.get("windowEnd"),
        "items": source_items,
    }


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    requested_date = date.fromisoformat(args.report_date) if args.report_date else None
    if requested_date and requested_date > datetime.now(KST).date():
        raise ValueError("미래 날짜의 교육동향 보고서는 생성할 수 없습니다.")

    expected_end = (
        datetime(
            requested_date.year,
            requested_date.month,
            requested_date.day,
            BRIEFING_HOUR_KST,
            tzinfo=KST,
        ).isoformat()
        if requested_date
        else briefing_window(datetime.now(KST))[1].isoformat()
    )
    attempts = 1 if requested_date else max(1, args.attempts)
    last_error = ""

    for attempt in range(1, attempts + 1):
        try:
            cache_key = f"attempt={attempt}&ts={int(time.time())}"
            selection_name = f"{requested_date.isoformat()}.json" if requested_date else "latest.json"
            selection = fetch_json(f"{base_url}/briefings/{selection_name}?{cache_key}")
            if requested_date:
                source = historical_source(
                    selection,
                    fetch_json(f"{base_url}/news.json?{cache_key}"),
                    requested_date,
                )
            else:
                source = fetch_json(f"{base_url}/latest.json?{cache_key}")

            source_end = source.get("windowEnd")
            selection_end = selection.get("metadata", {}).get("windowEnd")
            if requested_date:
                # 과거 재생성은 기준 시각 변경 이전 자료도 허용하도록 날짜만 대조한다.
                target = requested_date.isoformat()
                ready = str(source_end)[:10] == target and str(selection_end)[:10] == target
            else:
                ready = source_end == expected_end and selection_end == expected_end
            if ready:
                output = Path(args.output)
                output.mkdir(parents=True, exist_ok=True)
                (output / "latest.json").write_text(
                    json.dumps(source, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                (output / "selection.json").write_text(
                    json.dumps(selection, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                print(json.dumps({
                    "status": "ready",
                    "windowEnd": expected_end,
                    "reportDate": requested_date.isoformat() if requested_date else None,
                    "sourceCount": len(source.get("items", [])),
                    "attempt": attempt,
                }, ensure_ascii=False))
                return 0
            last_error = f"예상 {expected_end}, 수집 {source_end}, 선별 {selection_end}"
        except Exception as error:
            last_error = str(error)[:500]
        if attempt < attempts:
            print(f"최신 수집 결과 대기 중 ({attempt}/{attempts}): {last_error}", flush=True)
            time.sleep(max(1, args.interval))
    raise RuntimeError(f"보고서 입력을 받지 못했습니다: {last_error}")


if __name__ == "__main__":
    raise SystemExit(main())