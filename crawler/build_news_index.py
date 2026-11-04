"""'전국 보도자료' 탭이 읽을 가벼운 목록(public/news-index.json)을 만든다.

웹 화면은 제목·날짜·기관·링크만 쓰는데, 예전엔 본문까지 든 news.json(압축 4MB대)과
선정 표시용 briefing 파일 수십 개를 하나하나 받아 탭이 느렸다. 여기서 필요한 칸만
뽑고 선정 여부를 미리 계산해 파일 하나(압축 0.3MB 안팎)로 만든다.

news.json은 본문 때문에 90일만 보관하지만, 이 목록은 본문이 없어 가벼우므로
기간 제한 없이 계속 쌓는다. 그래서 매번 새로 만들지 않고 기존 목록과 합친다.

  - news.json 보관 범위 '안'의 글: news.json을 그대로 따른다
    (제목을 고쳤거나 일부러 지운 글이 목록에도 반영되도록)
  - news.json 보관 범위 '밖'(90일이 지나 빠진) 글: 기존 목록에서 그대로 살린다

선정 여부는 발행된 보고서 날짜(reports/index.json)의 briefing에서 모은다.
웹 화면이 하던 계산과 같다.

사용:
    python crawler/build_news_index.py                      # 저장소의 public/
    python crawler/build_news_index.py --public-dir ../x/public
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="전국 보도자료 탭용 가벼운 목록 생성")
    parser.add_argument("--public-dir", default=str(ROOT / "public"))
    return parser.parse_args()


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def report_dates(public: Path) -> list[str]:
    data = read_json(public / "reports" / "index.json", {})
    reports = data if isinstance(data, list) else data.get("reports", [])
    return sorted({str(r.get("date")) for r in reports if r.get("date")})


def selected_ids(public: Path, dates: list[str]) -> dict[str, str]:
    """기사 id → 처음 선정된 보고서 날짜."""
    selected: dict[str, str] = {}
    for day in dates:
        briefing = read_json(public / "briefings" / f"{day}.json", {})
        for item in briefing.get("selectedItems") or []:
            news_id = str((item or {}).get("newsId") or "")
            if news_id and news_id not in selected:
                selected[news_id] = day
    return selected


def to_row(item: dict[str, Any]) -> dict[str, Any] | None:
    title = str(item.get("title") or "").strip()
    date = str(item.get("date") or "")[:10]
    news_id = str(item.get("id") or "")
    if not (title and date and news_id):
        return None
    row = {
        "id": news_id,
        "sid": str(item.get("sourceId") or item.get("sid") or ""),
        "date": date,
        "title": title,
    }
    if item.get("url"):
        row["url"] = str(item["url"])
    return row


def build(public: Path) -> dict[str, Any]:
    news = read_json(public / "news.json", [])
    news = news if isinstance(news, list) else news.get("items", [])
    previous = read_json(public / "news-index.json", {})

    sources: dict[str, str] = dict(previous.get("sources") or {})
    rows: dict[str, dict[str, Any]] = {}

    current: list[dict[str, Any]] = []
    for item in news:
        row = to_row(item)
        if not row:
            continue
        current.append(row)
        rows[row["id"]] = row
        if row["sid"] and item.get("source"):
            sources[row["sid"]] = str(item["source"])

    # news.json에서 90일이 지나 빠진 글만 기존 목록에서 살린다.
    oldest_current = min((r["date"] for r in current), default="9999-12-31")
    kept_old = 0
    for row in previous.get("items") or []:
        if row.get("id") in rows or str(row.get("date", "")) >= oldest_current:
            continue
        clean = {k: v for k, v in row.items() if k != "sel"}
        rows[clean["id"]] = clean
        kept_old += 1

    selected = selected_ids(public, report_dates(public))
    for news_id, day in selected.items():
        if news_id in rows:
            rows[news_id]["sel"] = day

    items = sorted(rows.values(), key=lambda r: (r["date"], r["id"]), reverse=True)
    return {
        "generatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "count": len(items),
        "selectedCount": sum(1 for r in items if r.get("sel")),
        "keptBeyondNewsJson": kept_old,
        "sources": dict(sorted(sources.items())),
        "items": items,
    }


def main() -> int:
    public = Path(parse_args().public_dir)
    index = build(public)
    out = public / "news-index.json"
    out.write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    print(
        f"news-index.json: {index['count']}건 (선정 {index['selectedCount']}, "
        f"news.json 밖에서 보존 {index['keptBeyondNewsJson']}) {out.stat().st_size / 1e6:.2f}MB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
