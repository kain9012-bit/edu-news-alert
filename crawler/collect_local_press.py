"""전북 지역 언론사 사이트를 직접 훑어 보도자료 게재 기사를 찾는다.

전북금강일보·무진장인터넷뉴스처럼 보도자료를 제목 그대로 싣는 지역지는 구글 뉴스
색인에 잘 잡히지 않아, 검색만으로는 게재 사실을 놓치게 된다. 이 스크립트는 각
매체의 기사 목록을 직접 넘겨 제목을 모은 뒤, 보도자료 제목·부제와 대조해 잇는다.

모든 보도자료에 동일하게 적용되므로 부서별·자료별 비교가 어긋나지 않는다.
비용은 들지 않으며, 저장하는 값은 제목·언론사·링크뿐이다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.robotparser
from pathlib import Path
from typing import Any, Iterable

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_coverage import similarity, summarize_departments, tokenize  # noqa: E402

USER_AGENT = "Mozilla/5.0 (compatible; jbe-edu-trends/1.0) local-press-collector"
REQUEST_INTERVAL = 1.2

# 목록 화면에서 제목과 링크를 얻을 수 있는 지역지들.
OUTLETS = [
    # 아래 목록은 (1) 공개 조사에서 자동수집 가능으로 확인됐고 (2) 실행 시점에
    # robots.txt 검사를 통과하는 매체만 담는다. 실행할 때마다 다시 확인하므로,
    # 매체가 정책을 바꾸면 자동으로 제외된다.
    #
    # 제외한 곳:
    #  - 전북금강일보·전북일보·무주신문·열린순창: robots.txt가 AI 자동수집 차단
    #  - 전북도민일보·전북연합신문·전북타임스: 약관이 사전 동의 없는 수집·발췌 금지
    {
        "name": "무진장인터넷뉴스",
        "base": "https://www.mjjnews.net",
        "list": "https://www.mjjnews.net/news/article_list_all.html?page={page}",
        "link_pattern": r"/news/article\.html\?no=\d+",
        "pages": 40,
    },
    {
        "name": "전라일보",
        "base": "https://www.jeollailbo.com",
        "list": "https://www.jeollailbo.com/news/articleList.html?page={page}&view_type=sm",
        "link_pattern": r"/news/articleView\.html\?idxno=\d+",
        "pages": 20,
    },
    {
        "name": "전민일보",
        "base": "https://www.jeonmin.co.kr",
        "list": "https://www.jeonmin.co.kr/news/articleList.html?page={page}&view_type=sm",
        "link_pattern": r"/news/articleView\.html\?idxno=\d+",
        "pages": 20,
    },
    {
        "name": "전주일보",
        "base": "https://www.jjilbo.co.kr",
        "list": "https://www.jjilbo.co.kr/news/articleList.html?page={page}&view_type=sm",
        "link_pattern": r"/news/articleView\.html\?idxno=\d+",
        "pages": 20,
    },
    {
        "name": "투데이안",
        "base": "https://www.todayan.com",
        "list": "https://www.todayan.com/news/articleList.html?page={page}&view_type=sm",
        "link_pattern": r"/news/articleView\.html\?idxno=\d+",
        "pages": 20,
    },
    {
        "name": "전북의소리",
        "base": "https://www.jbsori.com",
        "list": "https://www.jbsori.com/news/articleList.html?page={page}&view_type=sm",
        "link_pattern": r"/news/articleView\.html\?idxno=\d+",
        "pages": 20,
    },
    {
        "name": "전주시민신문",
        "base": "https://jj1news.com",
        "list": "https://jj1news.com/news/article_list_all.html?page={page}",
        "link_pattern": r"/news/article\.html\?no=\d+",
        "pages": 20,
    },
    {
        "name": "완주신문",
        "base": "https://wj1news.com",
        "list": "https://wj1news.com/mobile/article_list_all.html?page={page}",
        "link_pattern": r"/mobile/article\.html\?no=\d+",
        "pages": 20,
    },
    {
        "name": "완주독립신문",
        "base": "https://wanjutimes.com",
        "list": "https://wanjutimes.com/news/article_list_all.html?page={page}",
        "link_pattern": r"/news/article\.html\?no=\d+",
        "pages": 20,
    },
    {
        "name": "김제시민의신문",
        "base": "https://www.gjtimes.co.kr",
        "list": "https://www.gjtimes.co.kr/news/articleList.html?page={page}&view_type=sm",
        "link_pattern": r"/news/articleView\.html\?idxno=\d+",
        "pages": 12,
    },
    {
        "name": "진안신문",
        "base": "https://www.janews.co.kr",
        "list": "https://www.janews.co.kr/news/articleList.html?page={page}&view_type=sm",
        "link_pattern": r"/news/articleView\.html\?idxno=\d+",
        "pages": 12,
    },
    {
        "name": "장수신문",
        "base": "https://www.jangsunews.co.kr",
        "list": "https://www.jangsunews.co.kr/news/articleList.html?page={page}&view_type=sm",
        "link_pattern": r"/news/articleView\.html\?idxno=\d+",
        "pages": 12,
    },
    {
        "name": "부안독립신문",
        "base": "https://www.ibuan.com",
        "list": "https://www.ibuan.com/news/articleList.html?page={page}&view_type=sm",
        "link_pattern": r"/news/articleView\.html\?idxno=\d+",
        "pages": 12,
    },
    {
        "name": "투데이군산",
        "base": "https://www.todaygunsan.co.kr",
        "list": "https://www.todaygunsan.co.kr/news/articleList.html?page={page}&view_type=sm",
        "link_pattern": r"/news/articleView\.html\?idxno=\d+",
        "pages": 12,
    },
    {
        "name": "부안뉴스",
        "base": "https://www.ibnews.kr",
        "list": "https://www.ibnews.kr/news/articleList.html?page={page}&view_type=sm",
        "link_pattern": r"/news/articleView\.html\?idxno=\d+",
        "pages": 12,
    },
    {
        "name": "부안인터넷신문",
        "base": "https://www.buan114.com",
        "list": "https://www.buan114.com/news/articleList.html?page={page}&view_type=sm",
        "link_pattern": r"/news/articleView\.html\?idxno=\d+",
        "pages": 12,
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="전북 지역지 직접 수집으로 게재 기사 보완")
    parser.add_argument("--coverage", default="public/coverage.json", help="게재현황 JSON")
    parser.add_argument("--min-score", type=float, default=0.6, help="제목 일치 최소값")
    parser.add_argument("--pages", type=int, default=0, help="매체별 최대 페이지(0이면 기본값)")
    parser.add_argument("--start-page", type=int, default=1, help="목록 시작 페이지")
    parser.add_argument("--outlet", type=int, default=-1, help="특정 매체만 처리(0부터), -1이면 전체")
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 결과만 출력")
    return parser.parse_args()


# robots.txt에서 이 이름들이 차단돼 있으면 자동수집을 원하지 않는 매체로 본다.
BLOCKED_AGENT_NAMES = ("claudebot", "gptbot", "ccbot", "anthropic-ai", "google-extended")


def robots_allows(session: requests.Session, base: str, path: str) -> tuple[bool, str]:
    """수집 전에 robots.txt를 확인한다.

    우리 수집기 이름(*)뿐 아니라 AI 크롤러를 차단해 둔 곳도 제외한다. 명시적으로
    막아 둔 매체를 이름만 바꿔 긁는 것은 취지에 어긋나기 때문이다.
    """
    robots_url = urllib.parse.urljoin(base, "/robots.txt")
    try:
        response = session.get(robots_url, timeout=(5, 15))
    except requests.RequestException as exc:
        return False, f"robots.txt 확인 실패({exc.__class__.__name__})"
    if response.status_code != 200:
        # robots.txt가 없으면 관례상 허용이지만, 판단 근거를 남긴다.
        return True, "robots.txt 없음(허용으로 봄)"

    text = response.text
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(text.splitlines())
    if not parser.can_fetch("*", urllib.parse.urljoin(base, path)):
        return False, "robots.txt가 일반 수집을 차단함"

    lowered = text.lower()
    for agent in BLOCKED_AGENT_NAMES:
        block = re.search(
            rf"user-agent:\s*{re.escape(agent)}\s*\n(?:\s*(?:allow|disallow):[^\n]*\n)*?\s*disallow:\s*/\s*(?:\n|$)",
            lowered,
        )
        if block:
            return False, f"robots.txt가 {agent} 자동수집을 차단함"
    return True, "허용"


def clean_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    # 목록에서 제목 뒤에 본문 미리보기가 붙어 나오는 경우를 잘라낸다.
    return text[:120]


def crawl_outlet(
    session: requests.Session, outlet: dict[str, Any], pages: int, start_page: int = 1
) -> dict[str, str]:
    """매체 목록을 넘기며 {기사주소: 제목}을 모은다."""
    found: dict[str, str] = {}
    pattern = re.compile(outlet["link_pattern"])
    for page in range(start_page, start_page + pages):
        url = outlet["list"].format(page=page)
        try:
            response = session.get(url, timeout=(5, 20))
        except requests.RequestException as exc:
            print(f"   {outlet['name']} {page}쪽 실패: {exc}", file=sys.stderr)
            break
        if response.status_code != 200:
            break
        response.encoding = response.apparent_encoding or "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        before = len(found)
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            if not pattern.search(href):
                continue
            title = clean_title(anchor.get_text(" ", strip=True))
            if len(title) < 8:
                continue
            full = urllib.parse.urljoin(outlet["base"], href)
            # 같은 기사에 제목·본문 링크가 여러 개면 가장 짧은(=제목) 것을 쓴다.
            if full not in found or len(title) < len(found[full]):
                found[full] = title
        if len(found) == before:
            break
        if page % 10 == 0:
            print(f"   {outlet['name']} {page}쪽까지 {len(found)}건")
        time.sleep(REQUEST_INTERVAL)
    return found


def match_articles(
    entries: list[dict[str, Any]], articles: dict[str, str], outlet_name: str, min_score: float
) -> int:
    """모은 기사 제목을 보도자료 제목·부제와 대조해 가장 잘 맞는 자료에 붙인다."""
    added = 0
    token_sets = [
        (entry, [tokenize(entry.get("title", "")), tokenize(entry.get("subtitle") or "")])
        for entry in entries
    ]
    for url, title in articles.items():
        best_entry, best_score = None, 0.0
        for entry, tokens in token_sets:
            score = max((similarity(t, title) for t in tokens if t), default=0.0)
            if score > best_score:
                best_entry, best_score = entry, score
        if not best_entry or best_score < min_score:
            continue
        existing = {a["url"] for a in best_entry.get("articles", []) or []}
        if url in existing:
            continue
        best_entry.setdefault("articles", []).append(
            {
                "title": title,
                "publisher": outlet_name,
                "publishedAt": best_entry.get("date", ""),
                "url": url,
                "via": "local",
            }
        )
        added += 1
    return added


def main() -> int:
    args = parse_args()
    path = Path(args.coverage)
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("items", [])
    if not entries:
        print("게재현황 자료가 비어 있습니다.")
        return 0

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    total_added = 0

    targets = OUTLETS if args.outlet < 0 else [OUTLETS[args.outlet]]
    for outlet in targets:
        allowed, reason = robots_allows(session, outlet["base"], "/")
        if not allowed:
            print(f"■ {outlet['name']} 건너뜀 — {reason}")
            continue
        pages = args.pages or outlet["pages"]
        print(f"■ {outlet['name']} 목록 수집 ({args.start_page}쪽부터 {pages}쪽)")
        articles = crawl_outlet(session, outlet, pages, args.start_page)
        print(f"   기사 {len(articles)}건 확보")
        added = match_articles(entries, articles, outlet["name"], args.min_score)
        total_added += added
        print(f"   보도자료와 연결 {added}건")

    for entry in entries:
        entry.setdefault("articles", [])
        entry["articles"].sort(key=lambda a: (a.get("publishedAt") or "", a.get("publisher") or ""))
        entry["articleCount"] = len(entry["articles"])

    payload["coveredCount"] = sum(1 for e in entries if e["articleCount"])
    payload["articleCount"] = sum(e["articleCount"] for e in entries)
    publishers: dict[str, int] = {}
    for entry in entries:
        for article in entry["articles"]:
            name = article.get("publisher", "미상")
            publishers[name] = publishers.get(name, 0) + 1
    payload["publishers"] = [
        {"name": name, "count": count}
        for name, count in sorted(publishers.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    payload["departments"] = summarize_departments(entries)

    if args.dry_run:
        print(f"\n(시험 실행) 추가 예정 {total_added}건")
        return 0

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n저장 완료: {total_added}건 추가 · 총 {payload['articleCount']}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
