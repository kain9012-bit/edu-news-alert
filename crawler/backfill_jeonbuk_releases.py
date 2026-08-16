"""전북교육청 보도자료 게시판을 거슬러 올라가 지난 보도자료 목록을 만든다.

news.json은 보관기간이 지난 자료를 지우기 때문에, 언론 게재현황을 과거까지
넓히려면 게시판에서 다시 목록을 받아와야 한다. 목록 화면에 제목·작성일·담당부서가
모두 있어 첨부파일을 열지 않고도 기본 정보를 얻을 수 있다.

결과는 news.json과 같은 형식으로 저장되므로 collect_coverage.py에 그대로 넘길 수 있다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

LIST_URL = (
    "https://news.jbe.go.kr/board/list.jbe"
    "?boardId=BBS_0000222&menuCd=DOM_000001201001000000"
    "&paging=ok&searchOperation=AND&startPage={page}"
)
VIEW_URL = (
    "https://news.jbe.go.kr/board/view.jbe"
    "?boardId=BBS_0000222&menuCd=DOM_000001201001000000"
    "&paging=ok&startPage=1&searchOperation=AND&dataSid={sid}"
)
USER_AGENT = "Mozilla/5.0 (compatible; jbe-edu-trends/1.0) release-backfill"
REQUEST_INTERVAL = 1.5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="전북교육청 지난 보도자료 목록 수집")
    parser.add_argument("--since", required=True, help="이 날짜부터 수집 (YYYY-MM-DD)")
    parser.add_argument("--until", default="9999-12-31", help="이 날짜까지 수집 (YYYY-MM-DD)")
    parser.add_argument("--out", required=True, help="저장 경로(news.json 형식)")
    parser.add_argument("--max-pages", type=int, default=40, help="넘겨볼 최대 목록 페이지 수")
    return parser.parse_args()


def parse_list_page(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, Any]] = []
    for item in soup.select("ul.news_list > li"):
        anchor = item.find("a", href=True)
        if not anchor or "dataSid=" not in anchor["href"]:
            continue
        sid_match = re.search(r"dataSid=(\d+)", anchor["href"])
        if not sid_match:
            continue
        strong = anchor.find("strong")
        title = strong.get_text(strip=True) if strong else ""
        info = anchor.find("em", class_="info")
        info_text = info.get_text(" ", strip=True) if info else ""
        date_match = re.search(r"작성일\s*:\s*(\d\d)\.(\d\d)\.(\d\d)", info_text)
        if not title or not date_match:
            continue
        dept_match = re.search(r"담당부서\s*:\s*([^\s]+?)\s*(?:연락처|$)", info_text)
        rows.append(
            {
                "sid": sid_match.group(1),
                "title": title,
                "date": f"20{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}",
                "department": dept_match.group(1) if dept_match else None,
            }
        )
    return rows


def collect(args: argparse.Namespace) -> list[dict[str, Any]]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    picked: dict[str, dict[str, Any]] = {}

    for page in range(1, args.max_pages + 1):
        response = session.get(LIST_URL.format(page=page), timeout=(5, 20))
        if response.status_code != 200:
            print(f"목록 {page}쪽 응답 {response.status_code}", file=sys.stderr)
            break
        response.encoding = response.apparent_encoding or "utf-8"
        rows = parse_list_page(response.text)
        if not rows:
            break

        reached = False
        for row in rows:
            if row["date"] < args.since:
                reached = True
                continue
            if row["date"] > args.until:
                continue
            picked[row["sid"]] = row
        oldest = min(row["date"] for row in rows)
        print(f"목록 {page}쪽 · 최종 {oldest} · 누적 {len(picked)}건")
        if reached:
            break
        time.sleep(REQUEST_INTERVAL)

    items = [
        {
            "id": f"jeonbuk-b{row['sid']}",
            "sourceId": "jeonbuk",
            "source": "전북특별자치도교육청",
            "title": row["title"],
            "date": row["date"],
            "url": VIEW_URL.format(sid=row["sid"]),
            "department": row["department"],
        }
        for row in picked.values()
    ]
    items.sort(key=lambda x: (x["date"], x["title"]), reverse=True)
    return items


def main() -> int:
    args = parse_args()
    items = collect(args)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    span = f"{items[-1]['date']} ~ {items[0]['date']}" if items else "없음"
    print(f"저장 완료: {out_path} ({len(items)}건, {span})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
