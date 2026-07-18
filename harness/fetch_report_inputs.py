from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from crawler.collect import KST, briefing_window


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="공개 대시보드에서 최신 내부 보고서 입력을 기다려 내려받기")
    parser.add_argument("--base-url", default="https://kain9012-bit.github.io/edu-news-alert")
    parser.add_argument("--output", default=".report-input")
    parser.add_argument("--attempts", type=int, default=15)
    parser.add_argument("--interval", type=int, default=120)
    return parser.parse_args()


def fetch_json(url: str) -> dict[str, Any]:
    response = requests.get(url, timeout=30, headers={"Cache-Control": "no-cache"})
    response.raise_for_status()
    return response.json()


def main() -> int:
    args = parse_args()
    expected_end = briefing_window(datetime.now(KST))[1].isoformat()
    base_url = args.base_url.rstrip("/")
    last_error = ""
    for attempt in range(1, max(1, args.attempts) + 1):
        try:
            source = fetch_json(f"{base_url}/latest.json?attempt={attempt}&ts={int(time.time())}")
            selection = fetch_json(f"{base_url}/briefings/latest.json?attempt={attempt}&ts={int(time.time())}")
            source_end = source.get("windowEnd")
            selection_end = selection.get("metadata", {}).get("windowEnd")
            if source_end == expected_end and selection_end == expected_end:
                output = Path(args.output)
                output.mkdir(parents=True, exist_ok=True)
                (output / "latest.json").write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                (output / "selection.json").write_text(json.dumps(selection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(json.dumps({"status": "ready", "windowEnd": expected_end, "attempt": attempt}, ensure_ascii=False))
                return 0
            last_error = f"예상 {expected_end}, 수집 {source_end}, 선별 {selection_end}"
        except Exception as error:
            last_error = str(error)[:500]
        if attempt < args.attempts:
            print(f"최신 수집 결과 대기 중 ({attempt}/{args.attempts}): {last_error}", flush=True)
            time.sleep(max(1, args.interval))
    raise RuntimeError(f"최신 수집 결과를 받지 못했습니다: {last_error}")


if __name__ == "__main__":
    raise SystemExit(main())