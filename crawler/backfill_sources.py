"""특정 기관의 지난 보도자료를 게시판에서 거슬러 올라가 news.json에 채워 넣는다.

수집기가 고장나 있던 기간(대구·세종·강원)처럼, 뒤늦게 고친 기관의 과거분을
보관기간 안에서 다시 모을 때 쓴다. 평소 수집(collect.py)은 하루 단위 창만 보므로
과거는 소급되지 않기 때문이다.

사용 예:
    python crawler/backfill_sources.py --sources daegu,sejong,gangwon --since 2026-07-27
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crawler.collect import (  # noqa: E402
    add_query,
    collect_detail,
    collect_links,
    fetch_text,
    stable_id,
    title_excluded,
)

NEWS_PATH = ROOT / "public" / "news.json"
SOURCES_PATH = ROOT / "crawler" / "sources.json"

# 기관별 목록 페이지 파라미터(실측으로 확인한 값)
PAGE_PARAM = {
    "daegu": "currPage",
    "sejong": "currPage",
    "gangwon": "pageIndex",
}
REQUEST_INTERVAL = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="지난 보도자료 백필")
    parser.add_argument("--sources", required=True, help="쉼표로 구분한 기관 id")
    parser.add_argument("--since", required=True, help="이 날짜부터 (YYYY-MM-DD)")
    parser.add_argument("--until", default="9999-12-31", help="이 날짜까지 (YYYY-MM-DD)")
    parser.add_argument("--max-pages", type=int, default=30, help="넘겨볼 최대 목록 페이지")
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 결과만 출력")
    return parser.parse_args()


def load_sources() -> dict[str, dict[str, Any]]:
    raw = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    items = raw["sources"] if isinstance(raw, dict) else raw
    return {s["id"]: s for s in items}


def backfill_source(
    source: dict[str, Any],
    since: str,
    until: str,
    max_pages: int,
    known_dates: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    page_param = PAGE_PARAM.get(source["id"])
    if not page_param:
        raise SystemExit(f"{source['id']}: 페이지 파라미터를 모릅니다. PAGE_PARAM에 추가하세요.")

    collected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    known = known_dates or {}
    stats = {"pages": 0, "links": 0, "already": 0, "too_old": 0, "excluded": 0, "failed": 0}

    for page in range(1, max_pages + 1):
        url = source["listUrl"] if page == 1 else add_query(source["listUrl"], {page_param: str(page)})
        try:
            links = collect_links({**source, "listUrl": url}, fetch_text(url, source))
        except Exception as exc:  # noqa: BLE001
            print(f"    {page}쪽 목록 실패: {type(exc).__name__} {exc}")
            break
        stats["pages"] += 1
        fresh = [l for l in links if l["url"] not in seen_urls]
        if not fresh:
            print(f"    {page}쪽에 새 항목이 없어 중단")
            break

        page_oldest = ""
        for link in fresh:
            seen_urls.add(link["url"])
            stats["links"] += 1
            if title_excluded(source, link.get("title", "")):
                stats["excluded"] += 1
                continue
            # 이미 news.json에 있는 글은 상세를 다시 열지 않는다(나눠 돌릴 때 빨라진다).
            item_id = stable_id(source["id"], link["url"])
            if item_id in known:
                stats["already"] += 1
                old_date = known[item_id][:10]
                if old_date:
                    page_oldest = min(page_oldest or old_date, old_date)
                continue
            try:
                item = collect_detail(source, link)
            except Exception as exc:  # noqa: BLE001
                stats["failed"] += 1
                print(f"      상세 실패 {link['url'][:70]}: {type(exc).__name__}")
                continue
            time.sleep(REQUEST_INTERVAL)
            date = str(item.get("date") or "")[:10]
            page_oldest = min(page_oldest or date, date) if date else page_oldest
            if date and date < since:
                stats["too_old"] += 1
                continue
            if date and date > until:
                continue
            if title_excluded(source, item.get("title", "")):
                stats["excluded"] += 1
                continue
            item["id"] = stable_id(source["id"], link["url"])
            item["sourceId"] = source["id"]
            item["source"] = source["name"]
            collected.append(item)

        print(f"    {page}쪽: 새 {len(fresh)}건 / 누적 {len(collected)}건 (이 쪽 최고 오래된 날짜 {page_oldest or '?'})")
        if page_oldest and page_oldest < since:
            print(f"    {since} 이전에 도달 — 중단")
            break

    return collected, stats


def main() -> int:
    args = parse_args()
    sources = load_sources()
    existing = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    by_id = {str(item.get("id")): item for item in existing}
    added = 0

    for sid in [s.strip() for s in args.sources.split(",") if s.strip()]:
        source = sources.get(sid)
        if not source:
            raise SystemExit(f"알 수 없는 기관 id: {sid}")
        print(f"\n=== {source['name']} ({sid}) ===")
        known_dates = {
            str(k): str(v.get("date") or "")
            for k, v in by_id.items()
            if v.get("sourceId") == sid
        }
        items, stats = backfill_source(
            source, args.since, args.until, args.max_pages, known_dates
        )
        new = [i for i in items if str(i.get("id")) not in by_id]
        print(f"  결과: 수집 {len(items)}건, 새로 추가 {len(new)}건, 통계 {stats}")
        for item in new:
            by_id[str(item["id"])] = item
        added += len(new)

    if args.dry_run:
        print(f"\n[dry-run] 저장하지 않음. 추가 예정 {added}건")
        return 0

    merged = sorted(
        by_id.values(),
        key=lambda i: (str(i.get("date") or ""), str(i.get("collectedAt") or "")),
        reverse=True,
    )
    NEWS_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\n저장 완료: {len(existing)}건 → {len(merged)}건 (+{added})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
