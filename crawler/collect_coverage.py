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
# 구글 뉴스가 색인하지 않는 기사를 Bing 뉴스가 잡는 경우가 있어 두 검색을 함께 쓴다.
BING_RSS_ENDPOINT = "https://www.bing.com/news/search"
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
    # '전국 1위', '전국 대회'처럼 흔한 수식어만 겹쳐 무관한 기사가 붙는 것을 막는다.
    "전국",
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
# 보도자료 배포일 전후 이 범위의 기사는 같은 사안일 가능성이 매우 높다.
# 언론사가 제목을 새로 뽑는 경우가 많아, 이때는 유사도 기준을 크게 낮춘다.
NEAR_DAYS = 4
NEAR_MIN_SCORE = 0.22
# 같은 날 기사라도 이 점수에 못 미치면, 주체가 전북교육청인지 따로 확인한다.
# ('청렴문화 확산'처럼 흔한 표현만 겹친 타 기관 기사를 걸러내기 위함)
NEAR_TRUST_SCORE = 0.6


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="보도자료의 언론 보도 현황 수집")
    parser.add_argument("--news", default="public/news.json", help="수집된 보도자료 JSON")
    parser.add_argument("--out", default="public/coverage.json", help="결과 저장 경로")
    parser.add_argument("--source-id", default="jeonbuk", help="대상 기관 sourceId")
    parser.add_argument("--days", type=int, default=30, help="최근 며칠치 보도자료를 대상으로 할지")
    parser.add_argument("--max-items", type=int, default=40, help="한 번에 조회할 보도자료 최대 건수")
    # 금요일에 배포한 자료를 월요일에 게시판에 올리는 일이 있어 앞쪽 여유를 넉넉히 둔다.
    parser.add_argument("--window-before", type=int, default=4, help="보도자료보다 이 일수 전 기사까지 인정")
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


# 소속 부서로 묶어서 봐야 하는 산하 기관·명칭 변형.
DEPARTMENT_ALIASES = {
    "전북학부모지원센터": "교육협력과",
    "학부모지원센터": "교육협력과",
}


def clean_department(value: str) -> str:
    """'(문의)재무과' 처럼 붙어 나오는 표 머리말을 떼어낸다."""
    text = re.sub(r"\s+", "", value or "")
    text = re.sub(r"^\(?문\s*의\)?", "", text)
    text = text.strip("()·-")
    # '감사관실'과 '감사관', '대변인실'과 '대변인'은 같은 부서로 본다.
    text = re.sub(r"(관|인)실$", r"\1", text)
    # '중등교육과장'처럼 직책이 붙어 나오면 부서명만 남긴다.
    text = re.sub(r"(과|관|원|실|부|단|센터)장$", r"\1", text)
    return DEPARTMENT_ALIASES.get(text, text)


def extract_department(document_text: str) -> str | None:
    """'담당 부서 / (문 의) / <부서명> / <직책> ...' 표에서 부서명을 읽는다.

    직책이 과장·대변인·감사관 등으로 제각각이라 직책 목록에 기대지 않고,
    '(문 의)' 바로 다음 줄을 부서명으로 본다.
    """
    marker = re.search(r"담당\s*부\s*서", document_text)
    if marker:
        tail = document_text[marker.end() :]
        lines = [line.strip() for line in tail.splitlines()]
        for line in lines[:6]:
            if not line:
                continue
            # '(문 의)' 같은 표 머리말은 건너뛴다.
            if re.fullmatch(r"\(?\s*문\s*의\s*\)?", line):
                continue
            name = clean_department(line)
            if 2 <= len(name) <= 20 and not re.search(r"\d", name):
                return name
            break

    match = DEPARTMENT_PATTERN.search(document_text)
    if match:
        name = clean_department(match.group(1))
        if len(name) >= 2:
            return name
    if marker:
        alt = DEPARTMENT_FALLBACK.search(document_text[marker.start() :])
        if alt:
            name = clean_department(alt.group(1))
            if len(name) >= 2:
                return name
    return None


# 한글 첨부에서 제목·부제 줄 앞에 붙어 나오는 깨진 머리글자.
SUBTITLE_MARKER = "汤捯"


def extract_subtitle(document_text: str, title: str) -> str | None:
    """보도자료의 부제를 뽑는다.

    언론사가 부제를 그대로 기사 제목으로 쓰는 경우가 많아, 제목만으로는
    같은 사안임을 알아채지 못한다. 부제를 함께 확보해 매칭에 쓴다.
    """
    title_tokens = tokenize(title)
    best: tuple[float, str] | None = None
    for line in document_text.splitlines():
        if SUBTITLE_MARKER not in line:
            continue
        text = line.replace(SUBTITLE_MARKER, "").strip()
        if len(text) < 8:
            continue
        # 제목과 같은 줄은 건너뛰고, 제목과 가장 덜 겹치는 줄을 부제로 본다.
        score = similarity(title_tokens, text)
        if score >= 0.8:
            continue
        if best is None or score < best[0]:
            best = (score, text)
    return best[1] if best else None


def fetch_release_meta(session: requests.Session, detail_url: str) -> tuple[str | None, str | None]:
    """보도자료 상세 페이지의 한글 첨부를 열어 주관 부서와 부제를 확인한다."""
    if not detail_url:
        return None, None
    try:
        page = session.get(detail_url, timeout=REQUEST_TIMEOUT)
        if page.status_code != 200:
            return None, None
        page.encoding = page.apparent_encoding or "utf-8"
        soup = BeautifulSoup(page.text, "html.parser")
        link = None
        for anchor in soup.find_all("a", href=True):
            label = f"{anchor.get('title') or ''} {anchor.get_text() or ''} {anchor['href']}"
            if "download" in anchor["href"] and re.search(r"\.hwpx?(?:[\"'\s]|$)", label, re.I):
                link = anchor["href"]
                break
        if not link:
            return None, None
        if link.startswith("/"):
            parsed = urllib.parse.urlsplit(detail_url)
            link = f"{parsed.scheme}://{parsed.netloc}{link}"
        attachment = session.get(link, timeout=(5, 30))
        if attachment.status_code != 200:
            return None, None
        text = extract_attachment_document_text(attachment.content, "release.hwp")
        if not text:
            return None, None
        return extract_department(text), text
    except (requests.RequestException, ValueError) as exc:
        print(f"  첨부 확인 실패: {exc}", file=sys.stderr)
        return None, None


BOARD_LIST_URL = (
    "https://news.jbe.go.kr/board/list.jbe"
    "?boardId=BBS_0000222&menuCd=DOM_000001201001000000"
    "&paging=ok&searchOperation=AND&startPage={page}"
)


def fetch_department_map(
    session: requests.Session, since_date: str, max_pages: int = 60
) -> dict[str, str]:
    """보도자료 목록 화면에서 글번호별 담당부서를 읽어온다.

    목록에 '담당부서 : 대변인'이 그대로 적혀 있으므로 첨부파일을 열 필요가 없다.
    대상 기간의 가장 오래된 자료가 나올 때까지 목록을 넘겨, 모든 자료의 부서를 채운다.
    """
    mapping: dict[str, str] = {}
    for page in range(1, max_pages + 1):
        try:
            response = session.get(BOARD_LIST_URL.format(page=page), timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            print(f"  목록 {page}쪽 조회 실패: {exc}", file=sys.stderr)
            break
        if response.status_code != 200:
            break
        response.encoding = response.apparent_encoding or "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")
        found = 0
        oldest = ""
        for item in soup.select("ul.news_list > li"):
            anchor = item.find("a", href=True)
            if not anchor or "dataSid=" not in anchor["href"]:
                continue
            sid = re.search(r"dataSid=(\d+)", anchor["href"])
            info = anchor.find("em", class_="info")
            if not sid or not info:
                continue
            text = info.get_text(" ", strip=True)
            dept = re.search(r"담당부서\s*:\s*([^\s]+?)\s*(?:연락처|$)", text)
            if dept:
                mapping[sid.group(1)] = clean_department(dept.group(1))
                found += 1
            posted = re.search(r"작성일\s*:\s*(\d\d)\.(\d\d)\.(\d\d)", text)
            if posted:
                value = f"20{posted.group(1)}-{posted.group(2)}-{posted.group(3)}"
                oldest = value if not oldest else min(oldest, value)
        if not found:
            break
        # 대상 기간을 지나면 더 넘길 필요가 없다.
        if oldest and since_date and oldest < since_date:
            break
        time.sleep(REQUEST_INTERVAL / 2)
    return mapping


def has_region_hint(text: str) -> bool:
    return any(hint in (text or "") for hint in REGION_HINTS)


def has_other_region(text: str) -> bool:
    return any(hint in (text or "") for hint in OTHER_REGION_HINTS)


# '익산시, 공감과 참여로 청렴문화 확산'처럼 지자체가 주어인 기사를 가려낸다.
MUNICIPALITY_SUBJECT = re.compile(r"^\s*[가-힣]{2,6}(?:시|군|구)\s*[,，]")
EDU_SUBJECT_HINTS = ("교육청", "교육감", "교육지원청", "전북교육", "교육원", "학교")


def is_other_organization(title: str) -> bool:
    """지자체 등 다른 기관이 주어이고 교육청 단서가 없으면 다른 사안으로 본다."""
    if not MUNICIPALITY_SUBJECT.match(title or ""):
        return False
    return not any(hint in title for hint in EDU_SUBJECT_HINTS)


def days_apart(article_date: str, release_date: str) -> int | None:
    if not article_date:
        return None
    try:
        return abs((date.fromisoformat(article_date) - date.fromisoformat(release_date)).days)
    except ValueError:
        return None


def is_same_case(
    score: float, article: dict[str, str], min_score: float, release_date: str = ""
) -> bool:
    """같은 사안을 다룬 기사인지 판정한다.

    보도자료는 배포 당일에 기사화되므로 날짜가 가장 강한 단서다. 배포일 전후
    이틀 안의 기사는 언론사가 제목을 새로 뽑아도 같은 사안일 가능성이 높아
    유사도 기준을 낮추고, 날짜가 멀면 제목이 거의 같아야 인정한다.
    """
    title = article.get("title", "")
    # 다른 지자체가 주어인 기사는 표현이 겹쳐도 다른 사안이다.
    if has_other_region(title) and not has_region_hint(title):
        return False
    if is_other_organization(title):
        return False

    gap = days_apart(article.get("publishedAt", ""), release_date) if release_date else None
    if gap is not None and gap <= NEAR_DAYS:
        # 배포 직후 기사는 제목을 새로 뽑았어도 같은 사안으로 본다.
        if score < NEAR_MIN_SCORE:
            return False
        if score >= NEAR_TRUST_SCORE:
            return True
        # 겹치는 말이 적다면 다른 기관 소식일 수 있으니 전북 단서를 확인한다.
        return has_region_hint(f"{title} {article.get('publisher', '')}")
    # 날짜가 멀면 과거의 비슷한 행사일 수 있으므로 제목이 거의 같아야 인정한다.
    return score >= STRONG_MATCH_SCORE


# 낱말을 많이 넣을수록 구글 뉴스가 결과를 거의 돌려주지 않는다(5개면 0건인 경우가 잦다).
QUERY_TERM_LIMIT = 3
# '만들어간다'처럼 서술어로 끝나는 낱말은 기사 제목에 그대로 쓰이지 않는 일이 많다.
VERB_ENDINGS = ("다", "요", "까", "죠", "임", "함")


def build_query(title: str, tokens: set[str]) -> str:
    """검색어는 핵심 낱말 몇 개로만 만든다.

    낱말을 많이 넣으면 모두 포함한 기사만 찾아 결과가 0건이 되기 쉽고,
    조사를 떼면 '신뢰받'처럼 실제로 쓰이지 않는 형태가 되어 검색이 어긋난다.
    그래서 원문 표기를 그대로 쓰고, 길이가 긴(정보량이 많은) 낱말을 고른다.
    """
    words = [w for w in re.split(r"\s+", re.sub(r"[^0-9A-Za-z가-힣\s]", " ", title)) if w]
    candidates = [w for w in words if strip_josa(w) in tokens]
    # '1,259명에'가 '259명에'로 쪼개지는 등 숫자가 섞인 낱말은 검색을 어긋나게 한다.
    without_numbers = [w for w in candidates if not re.search(r"\d", w)]
    if without_numbers:
        candidates = without_numbers
    nouns = [w for w in candidates if not w.endswith(VERB_ENDINGS)]
    if nouns:
        candidates = nouns
    if not candidates:
        candidates = words
    ranked = sorted(dict.fromkeys(candidates), key=lambda w: -len(w))[:QUERY_TERM_LIMIT]
    # 제목에 나온 순서를 지켜야 검색 결과가 자연스럽다.
    keep = [w for w in dict.fromkeys(candidates) if w in ranked]
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


def fetch_bing_rss(session: requests.Session, query: str) -> str | None:
    params = {"q": query, "format": "rss", "setmkt": "ko-KR"}
    url = f"{BING_RSS_ENDPOINT}?{urllib.parse.urlencode(params)}"
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        print(f"  Bing 요청 실패: {exc}", file=sys.stderr)
        return None
    return response.text if response.status_code == 200 else None


def _unwrap_bing_link(link: str) -> str:
    """Bing 뉴스 링크는 apiclick 리디렉션일 수 있어 원문 주소를 꺼낸다."""
    parsed = urllib.parse.urlsplit(link)
    if "bing.com" in parsed.netloc:
        for key, value in urllib.parse.parse_qsl(parsed.query):
            if key == "url":
                return value
    return link


def parse_bing_rss(xml_text: str) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    articles: list[dict[str, str]] = []
    for node in root.iterfind(".//item"):
        title = (node.findtext("title") or "").strip()
        link = _unwrap_bing_link((node.findtext("link") or "").strip())
        if not title or not link:
            continue
        source = ""
        for child in node:
            if child.tag.lower().endswith("source") and (child.text or "").strip():
                source = child.text.strip()
                break
        if not source:
            source = urllib.parse.urlsplit(link).netloc.replace("www.", "")
        articles.append(
            {
                "title": title,
                "publisher": source,
                "publishedAt": parse_pubdate(node.findtext("pubDate")),
                "url": link,
            }
        )
    return articles


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
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M %Z",  # Bing은 초를 생략하기도 한다.
        "%a, %d %b %Y %H:%M %z",
    ):
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


def dedupe_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """같은 언론사의 같은 기사를 하나로 합친다.

    구글·Bing이 같은 기사를 서로 다른 주소(리디렉션·MSN 재게재판)로 돌려주므로
    URL만으로는 걸러지지 않는다. 언론사명(MSN 꼬리표 제거)과 제목을 정규화해
    비교하고, 원문 주소(구글/MSN 리디렉션이 아닌 것)를 우선 남긴다.
    """
    def norm_publisher(name: str) -> str:
        text = re.sub(r"\s*on\s+MSN\s*$", "", name or "", flags=re.I)
        return re.sub(r"\s+", "", text).lower()

    def norm_title(title: str) -> str:
        return re.sub(r"[^0-9A-Za-z가-힣]", "", title or "")

    def directness(article: dict[str, Any]) -> int:
        host = urllib.parse.urlsplit(article.get("url", "")).netloc
        if "news.google.com" in host or "msn.com" in host or "bing.com" in host:
            return 1
        return 0

    best: dict[tuple[str, str], dict[str, Any]] = {}
    for article in articles:
        key = (norm_publisher(article.get("publisher", "")), norm_title(article.get("title", "")))
        current = best.get(key)
        if current is None or directness(article) < directness(current):
            best[key] = article
    kept = list(best.values())
    kept.sort(key=lambda a: (a.get("publishedAt") or "", a.get("publisher") or ""))
    return kept


def assign_articles(entries: list[dict[str, Any]], args: argparse.Namespace) -> None:
    """한 기사는 가장 잘 맞는 보도자료 한 곳에만 배정한다.

    비슷한 사업의 보도자료가 잇달아 나가면 같은 기사가 여러 자료에 붙는다.
    어느 자료의 검색에서 나왔는지와 무관하게 모든 기사를 모든 자료와 대조해,
    점수가 가장 높은 자료 하나에만 넣는다.
    """
    pool: dict[str, dict[str, str]] = {}
    for entry in entries:
        for article in entry["_found"]:
            pool.setdefault(article["url"], article)

    best: dict[str, tuple[float, int, int]] = {}
    for index, entry in enumerate(entries):
        release_date = entry["date"]
        for url, article in pool.items():
            score = max(
                (similarity(tokens, article["title"]) for tokens in entry["_tokens"]), default=0.0
            )
            if not is_same_case(score, article, args.min_score, release_date):
                continue
            if not within_window(
                article["publishedAt"], release_date, args.window_before, args.window_after
            ):
                continue
            gap = days_apart(article.get("publishedAt", ""), release_date)
            # 점수가 높은 자료, 같으면 배포일이 기사와 가까운 자료를 택한다.
            rank = (score, -(gap if gap is not None else 99), index)
            current = best.get(url)
            if current is None or rank[:2] > current[:2]:
                best[url] = rank

    for index, entry in enumerate(entries):
        entry.pop("_tokens", None)
        entry.pop("_found", None)
        kept = [pool[url] for url, rank in best.items() if rank[2] == index]
        kept = dedupe_articles(kept)
        entry["articleCount"] = len(kept)
        entry["articles"] = kept[: args.limit_per_item]


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
    # 순위는 부서가 배포한 보도자료 건수 기준으로 매긴다.
    return [
        {"name": name, **row}
        for name, row in sorted(
            stats.items(), key=lambda kv: (-kv[1]["releaseCount"], -kv[1]["articleCount"], kv[0])
        )
    ]


def load_known_meta(out_path: Path) -> dict[str, dict[str, Any]]:
    """이미 확인한 부서·부제는 다시 내려받지 않도록 기존 결과에서 읽어둔다."""
    if not out_path.exists():
        return {}
    try:
        old = json.loads(out_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    known: dict[str, dict[str, Any]] = {}
    for entry in old.get("items", []) or []:
        news_id = entry.get("newsId")
        if not news_id:
            continue
        # 첨부를 실제로 열어본 자료만 캐시로 인정한다(예전 형식은 다시 확인).
        if not entry.get("metaChecked"):
            continue
        known[str(news_id)] = {
            "department": entry.get("department"),
            "subtitle": entry.get("subtitle"),
        }
    return known


def collect(args: argparse.Namespace) -> dict[str, Any]:
    releases = load_releases(Path(args.news), args.source_id, args.days, args.max_items)
    known_meta = load_known_meta(Path(args.out))
    print(f"대상 보도자료 {len(releases)}건 (첨부 기확인 {len(known_meta)}건)")

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml"})

    # 부서는 목록 화면에서 한 번에 받아온다(첨부를 열 필요가 없다).
    department_map: dict[str, str] = {}
    if not args.skip_departments:
        oldest_needed = min((str(r.get("date", ""))[:10] for r in releases), default="")
        department_map = fetch_department_map(session, oldest_needed)
        print(f"목록에서 부서 {len(department_map)}건 확인 (기준 {oldest_needed})")

    entries: list[dict[str, Any]] = []
    last_request = 0.0

    def throttled_rss(query: str) -> list[dict[str, str]]:
        """구글·Bing 뉴스 검색을 모두 돌려 결과를 합친다."""
        nonlocal last_request
        results: list[dict[str, str]] = []
        for engine in ("google", "bing"):
            wait = REQUEST_INTERVAL - (time.monotonic() - last_request)
            if wait > 0:
                time.sleep(wait)
            last_request = time.monotonic()
            if engine == "google":
                xml_text = fetch_rss(session, query)
                if xml_text:
                    results.extend(parse_rss(xml_text))
            else:
                xml_text = fetch_bing_rss(session, query)
                if xml_text:
                    results.extend(parse_bing_rss(xml_text))
        return results

    for index, release in enumerate(releases, 1):
        title = str(release.get("title", "")).strip()
        release_date = str(release.get("date", ""))[:10]
        news_id = str(release.get("id") or "")
        print(f"[{index}/{len(releases)}] {release_date} {title[:40]}")

        cached = known_meta.get(news_id)
        subtitle = cached.get("subtitle") if cached else None
        meta_checked = bool(cached)

        # 부서는 게시판 목록에 그대로 적혀 있으므로 그 값을 그대로 쓴다.
        sid = re.search(r"dataSid=(\d+)", str(release.get("url") or ""))
        department = department_map.get(sid.group(1)) if sid else None
        if not department:
            department = release.get("department") or (cached.get("department") if cached else None)

        # 첨부는 목록에 없는 부제를 확인할 때만 연다.
        if not cached and not args.skip_departments:
            _unused, document = fetch_release_meta(session, str(release.get("url") or ""))
            meta_checked = document is not None
            if document:
                subtitle = extract_subtitle(document, title)

        # 언론사가 제목을 새로 뽑는 일이 잦아, 보도자료 제목과 부제를 모두 기준으로 삼는다.
        headlines = [h for h in (title, subtitle) if h]
        token_sets = [tokenize(h) for h in headlines]

        # 낱말 질의는 결과가 넓고, 제목 전체를 따옴표로 묶은 질의는 정확히 같은 제목을 집어낸다.
        queries: list[str] = []
        for headline, tokens in zip(headlines, token_sets):
            queries.append(build_query(headline, tokens))
        if title:
            queries.append(f'"{title}"')

        articles: list[dict[str, str]] = []
        for query in dict.fromkeys(queries):
            articles.extend(throttled_rss(query))

        entries.append(
            {
                "newsId": release.get("id"),
                "title": title,
                "subtitle": subtitle,
                "metaChecked": meta_checked,
                "date": release_date,
                "url": release.get("url"),
                "department": department,
                "_tokens": token_sets,
                "_found": articles,
            }
        )
        print(f"    → 검색 결과 {len(articles)}건 / 부서 {department or '미확인'}")

    assign_articles(entries, args)

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
        key = str(entry["newsId"])
        previous = by_id.get(key)
        if previous:
            # 웹검색·AI 등 다른 경로로 확보한 기사가 지워지지 않도록 합집합으로 병합한다.
            seen = {a.get("url") for a in entry.get("articles", []) or []}
            for article in previous.get("articles", []) or []:
                if article.get("url") not in seen:
                    entry["articles"].append(article)
                    seen.add(article.get("url"))
            entry["articles"] = dedupe_articles(entry["articles"])
            entry["articleCount"] = len(entry["articles"])
            if not entry.get("department"):
                entry["department"] = previous.get("department")
            if not entry.get("subtitle"):
                entry["subtitle"] = previous.get("subtitle")
        by_id[key] = entry
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
