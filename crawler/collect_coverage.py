"""전북교육청 보도자료가 언론에 어떻게 보도됐는지 수집한다.

news.json에 저장된 전북교육청 보도자료 제목을 질의어로 구글 뉴스 RSS를 검색하고,
제목 유사도와 보도 시점으로 같은 사안을 다룬 기사만 골라낸다.

저작권 보호를 위해 기사 본문·발췌는 저장하지 않고 제목·언론사·보도일·원문 링크만
남긴다. 결과는 public/coverage.json에 저장하며 GitHub Pages로 배포된다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect import extract_attachment_document_text  # noqa: E402

RSS_ENDPOINT = "https://news.google.com/rss/search"
USER_AGENT = (
    "Mozilla/5.0 (compatible; jbe-edu-trends/1.0; "
    "+https://jbe-edu-trends.vercel.app) press-coverage-collector"
)
REQUEST_TIMEOUT = (5, 15)
REQUEST_INTERVAL = 2.0  # 요청 사이 최소 간격(초)

KST = timezone(timedelta(hours=9))

# 제목 비교 시 버리는 조사·기관명·상투어. 이것들만 겹쳐 오탐이 나는 것을 막는다.
STOPWORDS = {
    "전북",
    "전라북도",
    "전북특별자치도",
    "전북특별자치도교육청",
    "전북교육청",
    "도교육청",
    "교육청",
    "교육감",
    "천호성",
    "운영",
    "실시",
    "개최",
    "추진",
    "지원",
    "위한",
    "통해",
    "함께",
    "우리",
    "올해",
    "내년",
    "관련",
    "대한",
    "모든",
    "이번",
}
JOSA = ("으로", "에서", "에게", "이나", "라도", "까지", "부터", "보다", "은", "는", "이", "가", "을", "를", "의", "에", "도", "와", "과", "로")

# '역량 강화 교육 실시'처럼 흔한 표현만 겹쳐 타 지자체 기사가 딸려오는 것을 막는 지역 단서.
REGION_HINTS = (
    "전북",
    "전라북도",
    "전주",
    "익산",
    "군산",
    "정읍",
    "남원",
    "김제",
    "완주",
    "진안",
    "무주",
    "장수",
    "임실",
    "순창",
    "고창",
    "부안",
    "천호성",
)
# 전북이 아닌 지역이 제목에 드러나면 같은 표현을 써도 다른 사안이다.
OTHER_REGION_HINTS = (
    "서울",
    "부산",
    "대구",
    "인천",
    "광주",
    "대전",
    "울산",
    "세종",
    "경기",
    "강원",
    "충북",
    "충남",
    "충청",
    "경북",
    "경남",
    "경상",
    "전남",
    "전라남도",
    "제주",
    "수원",
    "성남",
    "용인",
    "창원",
    "진주",
    "사천",
    "포항",
    "안동",
    "청주",
    "천안",
    "춘천",
    "원주",
    "목포",
    "여수",
    "순천",
)
# 지역 단서가 없어도 제목이 이만큼 일치하면 같은 사안으로 본다.
STRONG_MATCH_SCORE = 0.8


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="보도자료의 언론 보도 현황 수집")
    parser.add_argument("--news", default="public/news.json", help="수집된 보도자료 JSON")
    parser.add_argument("--out", default="public/coverage.json", help="결과 저장 경로")
    parser.add_argument("--source-id", default="jeonbuk", help="대상 기관 sourceId")
    parser.add_argument("--days", type=int, default=30, help="최근 며칠치 보도자료를 대상으로 할지")
    parser.add_argument("--max-items", type=int, default=40, help="한 번에 조회할 보도자료 최대 건수")
    parser.add_argument("--window-before", type=int, default=1, help="보도자료보다 이 일수 전 기사까지 인정")
    parser.add_argument("--window-after", type=int, default=10, help="보도자료보다 이 일수 후 기사까지 인정")
    parser.add_argument("--min-score", type=float, default=0.45, help="제목 유사도 임계값(0~1)")
    parser.add_argument("--limit-per-item", type=int, default=30, help="보도자료당 저장할 기사 최대 건수")
    parser.add_argument(
        "--skip-departments", action="store_true", help="한글 첨부에서 주관 부서를 확인하지 않는다"
    )
    return parser.parse_args()


def strip_josa(token: str) -> str:
    for suffix in JOSA:
        if len(token) > len(suffix) + 1 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def tokenize(text: str) -> set[str]:
    """제목을 비교 가능한 핵심 토큰 집합으로 바꾼다."""
    cleaned = re.sub(r"[^0-9A-Za-z가-힣\s]", " ", text or "")
    tokens: set[str] = set()
    for raw in cleaned.split():
        token = strip_josa(raw.strip())
        if len(token) < 2:
            continue
        if token in STOPWORDS:
            continue
        tokens.add(token)
    return tokens


def similarity(release_tokens: set[str], article_title: str) -> float:
    """보도자료 제목 토큰이 기사 제목에 얼마나 담겼는지(포함률)를 잰다."""
    if not release_tokens:
        return 0.0
    article_tokens = tokenize(article_title)
    if not article_tokens:
        return 0.0
    hit = 0
    for token in release_tokens:
        # 기사 제목이 표현을 조금 바꿔 쓰는 경우가 많아 부분 일치까지 인정한다.
        if any(token in other or other in token for other in article_tokens):
            hit += 1
    return hit / len(release_tokens)


# 보도자료 한글 첨부의 '담당 부서' 표에서 주관 부서명을 뽑는다.
DEPARTMENT_PATTERN = re.compile(
    r"담당\s*부\s*서.{0,40}?\n\s*([가-힣A-Za-z0-9()·\s]{2,20}?)\s*\n\s*"
    r"(?:과장|담당관|원장|센터장|실장|팀장|사무관|장학관)",
    re.S,
)
DEPARTMENT_FALLBACK = re.compile(r"([가-힣]{2,12}(?:과|담당관|정책관|센터|교육원|실))\s*\n")


def clean_department(value: str) -> str:
    """'(문의)재무과' 처럼 붙어 나오는 표 머리말을 떼어낸다."""
    text = re.sub(r"\s+", "", value or "")
    text = re.sub(r"^\(?문\s*의\)?", "", text)
    text = text.strip("()·-")
    return text


def extract_department(document_text: str) -> str | None:
    match = DEPARTMENT_PATTERN.search(document_text)
    if match:
        name = clean_department(match.group(1))
        if len(name) >= 2:
            return name
    marker = document_text.find("담당")
    if marker >= 0:
        alt = DEPARTMENT_FALLBACK.search(document_text[marker:])
        if alt:
            name = clean_department(alt.group(1))
            if len(name) >= 2:
                return name
    return None


def fetch_department(session: requests.Session, detail_url: str) -> str | None:
    """보도자료 상세 페이지의 한글 첨부를 열어 주관 부서를 확인한다."""
    if not detail_url:
        return None
    try:
        page = session.get(detail_url, timeout=REQUEST_TIMEOUT)
        if page.status_code != 200:
            return None
        page.encoding = page.apparent_encoding or "utf-8"
        soup = BeautifulSoup(page.text, "html.parser")
        link = None
        for anchor in soup.find_all("a", href=True):
            label = f"{anchor.get('title') or ''} {anchor.get_text() or ''} {anchor['href']}"
            if "download" in anchor["href"] and re.search(r"\.hwpx?(?:[\"'\s]|$)", label, re.I):
                link = anchor["href"]
                break
        if not link:
            return None
        if link.startswith("/"):
            parsed = urllib.parse.urlsplit(detail_url)
            link = f"{parsed.scheme}://{parsed.netloc}{link}"
        attachment = session.get(link, timeout=(5, 30))
        if attachment.status_code != 200:
            return None
        text = extract_attachment_document_text(attachment.content, "release.hwp")
        return extract_department(text) if text else None
    except (requests.RequestException, ValueError) as exc:
        print(f"  부서 확인 실패: {exc}", file=sys.stderr)
        return None


def has_region_hint(text: str) -> bool:
    return any(hint in (text or "") for hint in REGION_HINTS)


def has_other_region(text: str) -> bool:
    return any(hint in (text or "") for hint in OTHER_REGION_HINTS)


def is_same_case(score: float, article: dict[str, str], min_score: float) -> bool:
    """제목 유사도만으로는 걸러지지 않는 타 지역 기사를 배제한다."""
    if score < min_score:
        return False
    title = article.get("title", "")
    # 다른 지자체가 주어인 기사는 표현이 겹쳐도 다른 사안이다.
    if has_other_region(title) and not has_region_hint(title):
        return False
    # 지역 언론이 쓴 기사라면 제목에 지역명이 없어도 우리 사안일 가능성이 높다.
    if has_region_hint(f"{title} {article.get('publisher', '')}"):
        return True
    return score >= STRONG_MATCH_SCORE


def build_query(title: str, tokens: set[str]) -> str:
    """검색어는 핵심 토큰 위주로 만들어 지나치게 긴 질의를 피한다."""
    ordered = [t for t in re.split(r"\s+", re.sub(r"[^0-9A-Za-z가-힣\s]", " ", title)) if t]
    keep: list[str] = []
    for raw in ordered:
        token = strip_josa(raw)
        if token in tokens and token not in keep:
            keep.append(token)
        if len(keep) >= 8:
            break
    if not keep:
        keep = ordered[:8]
    return " ".join(["전북교육청", *keep])


def fetch_rss(session: requests.Session, query: str) -> str | None:
    params = {"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    url = f"{RSS_ENDPOINT}?{urllib.parse.urlencode(params)}"
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        print(f"  요청 실패: {exc}", file=sys.stderr)
        return None
    if response.status_code != 200:
        print(f"  응답 코드 {response.status_code}", file=sys.stderr)
        return None
    return response.text


def parse_rss(xml_text: str) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        print(f"  RSS 파싱 실패: {exc}", file=sys.stderr)
        return []
    articles: list[dict[str, str]] = []
    for node in root.iterfind(".//item"):
        raw_title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        if not raw_title or not link:
            continue
        source = (node.findtext("source") or "").strip()
        title = raw_title
        # 구글 뉴스 제목은 "기사 제목 - 언론사" 형태다.
        if source and raw_title.endswith(f" - {source}"):
            title = raw_title[: -len(f" - {source}")].strip()
        elif " - " in raw_title:
            title, _, tail = raw_title.rpartition(" - ")
            source = source or tail.strip()
        articles.append(
            {
                "title": title,
                "publisher": source or "미상",
                "publishedAt": parse_pubdate(node.findtext("pubDate")),
                "url": link,
            }
        )
    return articles


def parse_pubdate(value: str | None) -> str:
    if not value:
        return ""
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            parsed = datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(KST).date().isoformat()
    return ""


def within_window(article_date: str, release_date: str, before: int, after: int) -> bool:
    if not article_date:
        return True  # 날짜를 못 읽은 기사는 제목 유사도로만 판정한다.
    try:
        a = date.fromisoformat(article_date)
        r = date.fromisoformat(release_date)
    except ValueError:
        return True
    return (r - timedelta(days=before)) <= a <= (r + timedelta(days=after))


def load_releases(path: Path, source_id: str, days: int, max_items: int) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload if isinstance(payload, list) else payload.get("items", [])
    cutoff = (datetime.now(KST).date() - timedelta(days=days)).isoformat()
    picked = [
        item
        for item in items
        if item.get("sourceId") == source_id and str(item.get("date", ""))[:10] >= cutoff
    ]
    picked.sort(key=lambda x: str(x.get("date", "")), reverse=True)
    return picked[:max_items]


def summarize_departments(entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """부서별로 보도자료 수·보도된 건수·기사 수를 집계한다."""
    stats: dict[str, dict[str, int]] = {}
    for entry in entries:
        name = entry.get("department") or "미확인"
        row = stats.setdefault(name, {"releaseCount": 0, "coveredCount": 0, "articleCount": 0})
        row["releaseCount"] += 1
        count = int(entry.get("articleCount") or 0)
        row["articleCount"] += count
        if count > 0:
            row["coveredCount"] += 1
    return [
        {"name": name, **row}
        for name, row in sorted(stats.items(), key=lambda kv: (-kv[1]["articleCount"], kv[0]))
    ]


def load_known_departments(out_path: Path) -> dict[str, str]:
    """이미 확인한 부서는 다시 내려받지 않도록 기존 결과에서 읽어둔다."""
    if not out_path.exists():
        return {}
    try:
        old = json.loads(out_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    known: dict[str, str] = {}
    for entry in old.get("items", []) or []:
        if entry.get("newsId") and entry.get("department"):
            known[str(entry["newsId"])] = str(entry["department"])
    return known


def collect(args: argparse.Namespace) -> dict[str, Any]:
    releases = load_releases(Path(args.news), args.source_id, args.days, args.max_items)
    known_departments = load_known_departments(Path(args.out))
    print(f"대상 보도자료 {len(releases)}건 (부서 기확인 {len(known_departments)}건)")

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml"})

    entries: list[dict[str, Any]] = []
    last_request = 0.0
    for index, release in enumerate(releases, 1):
        title = str(release.get("title", "")).strip()
        release_date = str(release.get("date", ""))[:10]
        tokens = tokenize(title)
        query = build_query(title, tokens)
        print(f"[{index}/{len(releases)}] {release_date} {title[:40]}")

        wait = REQUEST_INTERVAL - (time.monotonic() - last_request)
        if wait > 0:
            time.sleep(wait)
        last_request = time.monotonic()

        xml_text = fetch_rss(session, query)
        matched: list[dict[str, str]] = []
        seen: set[str] = set()
        if xml_text:
            for article in parse_rss(xml_text):
                score = similarity(tokens, article["title"])
                if not is_same_case(score, article, args.min_score):
                    continue
                if not within_window(
                    article["publishedAt"], release_date, args.window_before, args.window_after
                ):
                    continue
                key = article["url"]
                if key in seen:
                    continue
                seen.add(key)
                matched.append(article)

        matched.sort(key=lambda a: (a.get("publishedAt") or "", a.get("publisher") or ""))

        news_id = str(release.get("id") or "")
        department = known_departments.get(news_id)
        if department is None and not args.skip_departments:
            department = fetch_department(session, str(release.get("url") or ""))

        entries.append(
            {
                "newsId": release.get("id"),
                "title": title,
                "date": release_date,
                "url": release.get("url"),
                "department": department,
                "articleCount": len(matched),
                "articles": matched[: args.limit_per_item],
            }
        )
        print(f"    → 기사 {len(matched)}건 / 부서 {department or '미확인'}")

    publishers: dict[str, int] = {}
    for entry in entries:
        for article in entry["articles"]:
            name = article["publisher"]
            publishers[name] = publishers.get(name, 0) + 1

    covered = sum(1 for e in entries if e["articleCount"] > 0)
    return {
        "departments": summarize_departments(entries),
        "generatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "source": "Google News RSS",
        "sourceId": args.source_id,
        "windowDays": args.days,
        "releaseCount": len(entries),
        "coveredCount": covered,
        "articleCount": sum(e["articleCount"] for e in entries),
        "publishers": [
            {"name": name, "count": count}
            for name, count in sorted(publishers.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "items": entries,
    }


def merge_with_existing(fresh: dict[str, Any], out_path: Path) -> dict[str, Any]:
    """이전 수집 결과를 보존해 오래된 보도자료의 기사 목록이 사라지지 않게 한다."""
    if not out_path.exists():
        return fresh
    try:
        old = json.loads(out_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fresh
    by_id: dict[str, dict[str, Any]] = {}
    for entry in old.get("items", []) or []:
        if entry.get("newsId"):
            by_id[str(entry["newsId"])] = entry
    for entry in fresh["items"]:
        by_id[str(entry["newsId"])] = entry
    merged = sorted(by_id.values(), key=lambda e: (str(e.get("date", "")), str(e.get("title", ""))), reverse=True)

    publishers: dict[str, int] = {}
    for entry in merged:
        for article in entry.get("articles", []) or []:
            name = article.get("publisher", "미상")
            publishers[name] = publishers.get(name, 0) + 1

    fresh["items"] = merged
    fresh["releaseCount"] = len(merged)
    fresh["coveredCount"] = sum(1 for e in merged if e.get("articleCount"))
    fresh["articleCount"] = sum(int(e.get("articleCount") or 0) for e in merged)
    fresh["publishers"] = [
        {"name": name, "count": count}
        for name, count in sorted(publishers.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    fresh["departments"] = summarize_departments(merged)
    return fresh


def main() -> int:
    args = parse_args()
    payload = collect(args)
    out_path = Path(args.out)
    payload = merge_with_existing(payload, out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"저장 완료: {out_path} "
        f"(보도자료 {payload['releaseCount']}건 중 {payload['coveredCount']}건 보도, "
        f"기사 {payload['articleCount']}건)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
