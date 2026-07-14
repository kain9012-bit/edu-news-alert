from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "public"
SOURCES_PATH = ROOT / "crawler" / "sources.json"
NEWS_PATH = PUBLIC_DIR / "news.json"
LATEST_PATH = PUBLIC_DIR / "latest.json"
STATUS_PATH = PUBLIC_DIR / "status.json"
PUBLIC_SOURCES_PATH = PUBLIC_DIR / "sources.json"

KST = timezone(timedelta(hours=9))
RETENTION_DAYS = int(__import__("os").environ.get("RETENTION_DAYS", "14"))
COLLECTION_WINDOW_HOURS = int(__import__("os").environ.get("COLLECTION_WINDOW_HOURS", "24"))
BRIEFING_HOUR_KST = int(__import__("os").environ.get("BRIEFING_HOUR_KST", "8"))
MAX_ITEMS_TOTAL = int(__import__("os").environ.get("MAX_ITEMS_TOTAL", "3000"))
MAX_ITEMS_PER_SOURCE = int(__import__("os").environ.get("MAX_ITEMS_PER_SOURCE", "20"))
TIMEOUT_SECONDS = int(__import__("os").environ.get("REQUEST_TIMEOUT_SECONDS", "20"))

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "edu-news-alert/0.1 (+https://github.com/kain9012-bit/edu-news-alert)",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
    }
)

DATE_PATTERNS = [
    r"(20\d{2})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})",
    r"(\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})",
]

GENERIC_TITLE_PHRASES = [
    "상단영역",
    "시스템안내",
    "전북교육소식",
    "제주교육소식",
    "요청하신 페이지를 찾을수 없습니다",
    "요청하신 페이지를 찾을 수 없습니다",
    "자율 균형 미래 경기도교육청",
    "GYEONGGIDO OFFICE OF EDUCATION",
    "보도자료 | 경기도교육청",
    "보도자료",
    "뉴스/소식",
]

PREFER_LIST_TITLE = {
    "gyeonggi",
    "busan",
    "daegu",
    "incheon",
    "sejong",
    "gyeongbuk",
    "chungnam",
    "jeju",
}

DATA_ID_ONLY_SOURCES = {
    "gyeonggi",
    "busan",
    "incheon",
    "chungbuk",
    "gyeongbuk",
}

RETIRED_SOURCE_IDS = {
    "gwangju",
    "jeonnam",
    "jeonbuk_institute",
    "jeonbuk_support",
    "jngj_s1n2",
    "jngj_s1n3",
}

NOTICE_TITLE_PHRASES = [
    "보도자료 서식",
    "보도(홍보)자료 제출방법",
    "보도자료 작성 서식",
]

TITLE_SELECTORS = {
    "seoul": [".news_view_tit", ".view_title", "h1", "h2"],
    "gyeonggi": [".board_view .tit", ".view_title", ".title", "h1", "h2"],
    "busan": [".bbs_ViewA h3", "h3", ".tit"],
    "daegu": [".bbs_ViewA h3", "h3"],
    "incheon": [".bbs_ViewA h3", ".bbs_ViewA", ".subContent"],
    "gwangju": [".subject", ".view_top .subject"],
    "daejeon": ["article.board-text h2.tit", "#container h2.tit"],
    "ulsan": ["h3.vtitle .tit", ".bd-view__vhead h3.vtitle .tit", ".bd-view__vhead h3.vtitle"],
    "sejong": [".bbs_ViewA h3", ".bbs_ViewA", "#cntntsView"],
    "gangwon": [".board_detail .title", ".bo_head .title"],
    "chungbuk": [".bbs_ViewA h3", "h3"],
    "chungnam": ["article.board-text h1.tit", ".board-text h1.tit", ".tit"],
    "jeonnam": [".article-view-header h3.heading", ".aht-title-view", "header.article-view-header h3.heading"],
    "jngj_s1n1": [".article-view-header h3.heading", ".aht-title-view", "header.article-view-header h3.heading"],
    "gyeongbuk": ["th.title", ".title"],
    "gyeongnam": [".bd-view__vhead h3.vtitle .tit", ".bd-view__vhead h3.vtitle", ".bd-view__vhead .tit"],
    "jeju": [".bdvTit", ".bdvTitWrap .bdvTit"],
    "moe": ["h3", ".tit", ".title"],
}

CONTENT_SELECTORS = {
    "jeonbuk": [".bbs_con", ".board_view"],
    "seoul": ["#view_txt", ".news_view", ".view_cont"],
    "gyeonggi": [".bbsV_cont", "#contents", ".board_view", ".view_cont"],
    "busan": [".bbsV_cont"],
    "daegu": [".bbsV_cont"],
    "incheon": [".bbsV_cont"],
    "gwangju": [".press_content", "#EditorViewer"],
    "daejeon": [".viewBox"],
    "ulsan": [".bd-view__vcontent .txt", ".bd-view__vcontent"],
    "sejong": [".bbsV_cont"],
    "gangwon": [".bo_con"],
    "chungbuk": [".bbsV_cont"],
    "chungnam": [".viewBox"],
    "jeonnam": ["#article-view-content-div"],
    "jngj_s1n1": ["#article-view-content-div"],
    "gyeongbuk": ["table"],
    "gyeongnam": [".bd-view__vcontent .txt", ".bd-view__vcontent"],
    "jeju": [".bdvCntWrap"],
    "moe": [".boardView", ".board_view", "body"],
}

REMOVE_SELECTORS = [
    "script",
    "style",
    "noscript",
    ".file",
    ".attach",
    ".view_file",
    ".bbsV_atchmnfl",
    ".fieldBox",
    ".bdvFileWrap",
    ".bd-view__vattach",
    ".bo_file",
    ".btn_area",
    ".btnGrp",
    ".sns",
    ".listNavi",
    ".hwp_editor_board_content",
]


def now_kst() -> datetime:
    return datetime.now(KST)


def briefing_window(reference: datetime | None = None) -> tuple[datetime, datetime]:
    current = reference or now_kst()
    window_end = current.replace(hour=BRIEFING_HOUR_KST, minute=0, second=0, microsecond=0)
    if current < window_end:
        window_end -= timedelta(days=1)
    return window_end - timedelta(hours=COLLECTION_WINDOW_HOURS), window_end


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def stable_id(source_id: str, url: str) -> str:
    return f"{source_id}-{hashlib.sha1(url.encode('utf-8')).hexdigest()[:16]}"


def fetch_text(url: str, source: dict[str, Any] | None = None) -> str:
    verify = not (source or {}).get("verifySsl") is False
    res = SESSION.get(url, timeout=TIMEOUT_SECONDS, verify=verify)
    res.raise_for_status()
    if not res.encoding or res.encoding.lower() == "iso-8859-1":
        res.encoding = res.apparent_encoding or "utf-8"
    return res.text


def url_matches(url: str, source: dict[str, Any]) -> bool:
    include = source.get("include") or []
    exclude = source.get("exclude") or []
    if include and not all(part in url for part in include):
        return False
    return not any(part in url for part in exclude)


def add_query(url: str, params: dict[str, str]) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key, value in params.items():
        if value:
            query[key] = [value]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def detail_url_from_seq(source: dict[str, Any], seq: str) -> str | None:
    detail_path = source.get("detailPath")
    seq_param = source.get("seqParam")
    if not detail_path or not seq_param or not seq:
        return None
    list_query = parse_qs(urlparse(source["listUrl"]).query)
    params = {seq_param: seq}
    for key in ["bbsId", "mi", "boardID", "m", "s", "searchCate"]:
        if key in list_query:
            params[key] = list_query[key][0]
    return add_query(urljoin(source["listUrl"], detail_path), params)


def clean_candidate_title(text: str) -> str:
    text = normalize_space(text or "")
    text = re.sub(r"^(닫기\s+)+", "", text)
    for delimiter in [" < ", " | ", " - "]:
        if delimiter in text:
            left = text.split(delimiter, 1)[0].strip()
            if len(left) >= 5:
                text = left
                break
    for marker in ["작성자", "등록일", "조회수", "담당부서", "▢", "□", "○"]:
        idx = text.find(marker)
        if idx > 8:
            text = text[:idx]
    text = re.sub(r"\s+\d{4}[.-]\d{2}[.-]\d{2}.*$", "", text)
    text = re.sub(r"\s+\d{2}[.-]\d{2}[.-]\d{2}.*$", "", text)
    text = re.sub(r"^\d+\s+", "", text)
    text = re.sub(r"\s*새글\s*$", "", text)
    return normalize_space(text).strip(" -|·")


def is_generic_title(text: str) -> bool:
    title = normalize_space(text or "")
    if len(title) < 5:
        return True
    return any(phrase in title for phrase in GENERIC_TITLE_PHRASES)


def needs_refetch(item: dict[str, Any]) -> bool:
    return is_generic_title(item.get("title", "")) or len(normalize_space(item.get("summary", ""))) < 40


def is_usable_item(item: dict[str, Any]) -> bool:
    if item.get("sourceId") in RETIRED_SOURCE_IDS:
        return False
    title = normalize_space(item.get("title", ""))
    summary = normalize_space(item.get("summary", ""))
    if item.get("sourceId") == "incheon" and not item.get("bundleIndex") and re.search(r"외\s*\d+건", title):
        return False
    return bool(title) and title != "제목 없음" and not is_generic_title(title) and not is_notice_title(title) and len(summary) >= 40


def row_text(tag: Any) -> str:
    parent = tag.find_parent(["tr", "li", "div", "article"])
    return normalize_space(parent.get_text(" ", strip=True)) if parent else normalize_space(tag.get_text(" ", strip=True))


def is_notice_title(text: str) -> bool:
    title = normalize_space(text or "")
    return any(phrase in title for phrase in NOTICE_TITLE_PHRASES)


def collect_moe_links(source: dict[str, Any], soup: BeautifulSoup) -> list[dict[str, str]]:
    seen: set[str] = set()
    links: list[dict[str, str]] = []
    for a in soup.find_all("a"):
        onclick = str(a.get("onclick") or "")
        match = re.search(r"goView\(['\"](\d+)['\"]\s*,\s*['\"](\d+)['\"]", onclick)
        if not match:
            continue
        board_id, board_seq = match.groups()
        url = add_query(
            urljoin(source["listUrl"], source.get("detailPath") or "/boardCnts/viewRenew.do"),
            {
                "boardID": board_id,
                "boardSeq": board_seq,
                "lev": "0",
                "m": "020402",
                "s": "moe",
            },
        )
        title = clean_candidate_title(a.get_text(" ") or row_text(a))
        if is_notice_title(title) or not url_matches(url, source) or url in seen:
            continue
        seen.add(url)
        links.append({"url": url, "title": title, "listText": row_text(a)})
    return links[:MAX_ITEMS_PER_SOURCE]


def collect_links(source: dict[str, Any], html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    links: list[dict[str, str]] = []
    source_id = source["id"]

    if source_id == "moe":
        return collect_moe_links(source, soup)

    if source_id == "sejong":
        return []

    if source_id not in DATA_ID_ONLY_SOURCES:
        for a in soup.find_all("a"):
            href = a.get("href") or ""
            title = clean_candidate_title(a.get_text(" ") or row_text(a))
            if not href or is_notice_title(title):
                continue
            url = urljoin(source["listUrl"], href)
            if url_matches(url, source) and url not in seen:
                seen.add(url)
                links.append({"url": url, "title": title, "listText": row_text(a)})

    seq_param = source.get("seqParam")
    if seq_param:
        tags = soup.select("a.nttInfoBtn[data-id]") if source_id in DATA_ID_ONLY_SOURCES else soup.find_all(True)
        for tag in tags:
            attrs = tag.attrs
            seq = None
            for name in ["data-id", "data-ntt-sn", "data-nttsn", "data-seq", "data-board-seq"]:
                if attrs.get(name):
                    seq = str(attrs.get(name))
                    break
            if not seq:
                onclick = str(attrs.get("onclick") or "")
                match = re.search(r"(?:nttSn|boardSeq|dataId|seq)['\"\s,:=]+(\d+)", onclick)
                if not match:
                    match = re.search(r"\b(\d{5,})\b", onclick)
                if match:
                    seq = match.group(1)
            url = detail_url_from_seq(source, seq or "")
            title = clean_candidate_title(tag.get_text(" ") or row_text(tag))
            if is_notice_title(title):
                continue
            if url and url_matches(url, source) and url not in seen:
                seen.add(url)
                links.append({"url": url, "title": title, "listText": row_text(tag)})

    return links[:MAX_ITEMS_PER_SOURCE]


def parse_date(text: str) -> str:
    text = text or ""
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text)
        if not match:
            continue
        y, m, d = [int(x) for x in match.groups()]
        if y < 100:
            y += 2000
        try:
            return datetime(y, m, d, tzinfo=KST).date().isoformat()
        except ValueError:
            pass
    try:
        return date_parser.parse(text, fuzzy=True).date().isoformat()
    except Exception:
        return now_kst().date().isoformat()


def item_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = date_parser.parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt
    except Exception:
        return None


def within_collection_window(item: dict[str, Any], window_start: datetime, window_end: datetime) -> bool:
    value = item.get("date") or item.get("publishedAt") or item.get("collectedAt")
    dt = item_datetime(value)
    if not dt:
        return True
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
        return window_start.date() <= dt.date() <= window_end.date()
    return window_start <= dt <= window_end


def meta_content(soup: BeautifulSoup, *selectors: str) -> list[str]:
    values = []
    for selector in selectors:
        node = soup.select_one(selector)
        if node and node.get("content"):
            values.append(str(node.get("content")))
    return values


def extract_title(soup: BeautifulSoup, fallback: str, source: dict[str, Any]) -> str:
    source_id = source["id"]
    candidates: list[str] = []
    fallback_title = clean_candidate_title(fallback or "")

    if source_id == "jeju" and fallback_title and not is_generic_title(fallback_title):
        return fallback_title[:200]

    if source_id in PREFER_LIST_TITLE and fallback_title:
        candidates.append(fallback_title)

    for selector in TITLE_SELECTORS.get(source_id, []):
        found = soup.select_one(selector)
        if found:
            candidates.append(found.get_text(" ", strip=True))

    candidates.extend(meta_content(soup, 'meta[property="og:title"]', 'meta[name="twitter:title"]'))

    page_text = normalize_space(soup.get_text("\n", strip=True))
    if source_id.startswith("jeonbuk"):
        for pattern in [r"네이버밴드 공유\s+(?:닫기\s+)?(.{5,180}?)\s+작성자\s*:?"]:
            match = re.search(pattern, page_text)
            if match:
                candidates.append(match.group(1))

    for selector in ["h1", "h2", "h3", "h4", ".title", ".view_title", ".view-title", ".tit"]:
        found = soup.select_one(selector)
        if found:
            candidates.append(found.get_text(" ", strip=True))

    if source_id not in PREFER_LIST_TITLE and fallback_title:
        candidates.append(fallback_title)
    if soup.title:
        candidates.append(soup.title.get_text(" ", strip=True))

    for candidate in candidates:
        title = clean_candidate_title(candidate)
        if not is_generic_title(title):
            return title[:200]
    return fallback_title if fallback_title and not is_generic_title(fallback_title) else "제목 없음"


def clean_content_text(text: str) -> str:
    lines = [normalize_space(line) for line in (text or "").replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line)


def selector_text(soup: BeautifulSoup, selector: str) -> str:
    node = soup.select_one(selector)
    if not node:
        return ""
    node_soup = BeautifulSoup(str(node), "lxml")
    for bad_selector in REMOVE_SELECTORS:
        for bad in node_soup.select(bad_selector):
            bad.decompose()
    return clean_content_text(node_soup.get_text("\n", strip=True))


def extract_summary(soup: BeautifulSoup, source: dict[str, Any]) -> str:
    candidates = []
    for selector in CONTENT_SELECTORS.get(source["id"], []):
        text = selector_text(soup, selector)
        if text:
            candidates.append(text)
    candidates.append(clean_content_text(soup.get_text("\n", strip=True)))
    for text in candidates:
        if len(text) > 40:
            if source["id"] == "incheon":
                return text[:5000]
            return text[:700]
    return ""


def collect_detail(source: dict[str, Any], link: dict[str, str]) -> dict[str, Any]:
    html = fetch_text(link["url"], source)
    soup = BeautifulSoup(html, "lxml")
    all_text = soup.get_text(" ")
    title = extract_title(soup, link.get("title", ""), source)
    date = parse_date(all_text + " " + link.get("listText", ""))
    summary = extract_summary(soup, source)
    return {
        "id": stable_id(source["id"], link["url"]),
        "sourceId": source["id"],
        "source": source["name"],
        "title": title,
        "date": date,
        "url": link["url"],
        "summary": summary,
        "collectedAt": now_kst().isoformat(timespec="seconds"),
    }


def cleanup_incheon_split_title(title: str) -> str:
    title = normalize_space(title or "")
    title = re.sub(r"\s+([,.:;!?])", r"\1", title)
    title = re.sub(r"([‘“\"\(\[])\s+", r"\1", title)
    title = re.sub(r"\s+([’”\"\)\]])", r"\1", title)
    title = re.sub(r"(\d)\s+(년|월|일|명|개|곳|회|차|기|학년)", r"\1\2", title)
    title = re.sub(r"\s*·\s*", "·", title)
    title = re.sub(r"\s*,\s*", ", ", title)
    return normalize_space(title).strip(" ,")


def infer_incheon_split_title(section: str, fallback_title: str = "") -> str:
    lines = [line.strip() for line in (section or "").splitlines() if line.strip()]
    if not lines:
        return cleanup_incheon_split_title(fallback_title)
    first = re.sub(r"^\d{1,2}\.\s*", "", lines[0]).strip()
    joined = normalize_space(" ".join(lines[:30]))
    org = first.strip(" ,")
    if org and len(org) >= 3:
        second_pos = joined.find(org, len(org))
        if second_pos > len(org):
            return cleanup_incheon_split_title(joined[:second_pos])
    chunks = []
    for line in lines[:8]:
        clean_line = re.sub(r"^\d{1,2}\.\s*", "", line).strip()
        if not clean_line:
            continue
        chunks.append(clean_line)
        candidate = cleanup_incheon_split_title(" ".join(chunks))
        if re.search(r"(실시|개최|운영|모집|가동|상영|전달|시행|확대|선정|발간|지원|추진)$", candidate):
            return candidate
        if len(candidate) >= 45 and len(chunks) >= 2:
            return candidate
    return cleanup_incheon_split_title(first or fallback_title)


def split_incheon_bundle_items(item: dict[str, Any]) -> list[dict[str, Any]]:
    if item.get("sourceId") != "incheon":
        return [item]
    text = item.get("summary") or ""
    if not text:
        return [item]

    raw_markers = list(re.finditer(r"(?m)^\s*(\d{1,2})\.\s*(?=\S|\n|$)", text))
    if len(raw_markers) < 2:
        return [item]

    markers = []
    for marker in raw_markers:
        after = text[marker.end() : marker.end() + 250]
        first_line = ""
        for line in after.splitlines():
            line = line.strip()
            if line:
                first_line = line
                break
        if len(first_line) >= 5 and any(
            word in first_line for word in ["인천", "교육청", "교육지원청", "도서관", "학교"]
        ):
            markers.append(marker)
    if len(markers) < 2:
        return [item]

    ntt_match = re.search(r"nttSn=(\d+)", item.get("url", ""))
    ntt_sn = ntt_match.group(1) if ntt_match else hashlib.sha1(item.get("url", "").encode("utf-8")).hexdigest()[:12]
    split_items: list[dict[str, Any]] = []
    for idx, marker in enumerate(markers, start=1):
        section_start = marker.end()
        section_end = markers[idx].start() if idx < len(markers) else len(text)
        section = text[section_start:section_end].strip()
        if len(section) < 150:
            continue
        title = infer_incheon_split_title(section, item.get("title", ""))
        if not title:
            continue
        split_items.append(
            {
                **item,
                "id": stable_id("incheon", f"{item.get('url', '')}#bundle-{ntt_sn}-{idx:02d}"),
                "title": title[:200],
                "summary": section[:700],
                "bundleIndex": idx,
                "bundleTotal": len(markers),
            }
        )
    return split_items or [item]


def collect_source(
    source: dict[str, Any],
    existing_by_id: dict[str, dict[str, Any]],
    window_start: datetime,
    window_end: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = now_kst().isoformat(timespec="seconds")
    skipped_existing = 0
    skipped_old = 0
    detail_failures = 0
    refreshed_existing = 0
    try:
        html = fetch_text(source["listUrl"], source)
        links = collect_links(source, html)
        items = []
        for link in links:
            item_id = stable_id(source["id"], link["url"])
            existing = existing_by_id.get(item_id)
            if existing and source["id"] != "incheon" and not needs_refetch(existing):
                skipped_existing += 1
                continue
            try:
                item = collect_detail(source, link)
                expanded_items = split_incheon_bundle_items(item)
                kept_any = False
                for expanded in expanded_items:
                    expanded_existing = existing_by_id.get(expanded["id"]) or existing
                    if within_collection_window(expanded, window_start, window_end) or expanded_existing:
                        items.append(expanded)
                        kept_any = True
                        if expanded_existing:
                            refreshed_existing += 1
                    else:
                        skipped_old += 1
                if not kept_any and not expanded_items:
                    skipped_old += 1
            except Exception as exc:
                detail_failures += 1
                print(f"detail failed {source['id']} {link['url']}: {exc}")
        return items, {
            "sourceId": source["id"],
            "source": source["name"],
            "status": "success",
            "foundLinks": len(links),
            "fetched": len(items),
            "refreshedExisting": refreshed_existing,
            "skippedExisting": skipped_existing,
            "skippedOutsideWindow": skipped_old,
            "detailFailures": detail_failures,
            "startedAt": started,
            "finishedAt": now_kst().isoformat(timespec="seconds"),
        }
    except Exception as exc:
        return [], {
            "sourceId": source["id"],
            "source": source["name"],
            "status": "failed",
            "foundLinks": 0,
            "fetched": 0,
            "refreshedExisting": refreshed_existing,
            "skippedExisting": skipped_existing,
            "skippedOutsideWindow": skipped_old,
            "detailFailures": detail_failures,
            "error": str(exc)[:500],
            "startedAt": started,
            "finishedAt": now_kst().isoformat(timespec="seconds"),
        }


def within_retention(item: dict[str, Any], cutoff: datetime) -> bool:
    value = item.get("publishedAt") or item.get("date") or item.get("collectedAt")
    dt = item_datetime(value)
    if not dt:
        return False
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
        return dt.date() >= cutoff.date()
    return dt >= cutoff


def dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        key = "::".join(
            [
                normalize_space(item.get("url", "")),
                normalize_space(item.get("title", "")),
            ]
        )
        current = deduped.get(key)
        if not current or (item.get("collectedAt", "") > current.get("collectedAt", "")):
            deduped[key] = item
    return list(deduped.values())


def normalize_source_names(items: list[dict[str, Any]], source_names: dict[str, str]) -> list[dict[str, Any]]:
    for item in items:
        source_id = item.get("sourceId")
        if source_id in source_names:
            item["source"] = source_names[source_id]
    return items


def public_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_names: set[str] = set()
    output = []
    for source in sources:
        name = source["name"]
        if name in seen_names:
            continue
        seen_names.add(name)
        output.append({"id": source["id"], "name": name, "enabled": source.get("enabled", True)})
    return output


def main() -> None:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    sources = [s for s in read_json(SOURCES_PATH, []) if s.get("enabled", True)]
    old_items = read_json(NEWS_PATH, [])
    existing_by_id = {item.get("id", ""): item for item in old_items if item.get("id")}
    window_start, window_end = briefing_window()

    all_new: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    for source in sources:
        print(f"collect {source['id']} {source['name']}")
        items, run = collect_source(source, existing_by_id, window_start, window_end)
        all_new.extend(items)
        for item in items:
            existing_by_id[item["id"]] = item
        runs.append(run)

    merged: dict[str, dict[str, Any]] = {item.get("id", ""): item for item in old_items if item.get("id")}
    for item in all_new:
        merged[item["id"]] = {**merged.get(item["id"], {}), **item}

    cutoff = window_end - timedelta(days=RETENTION_DAYS)
    source_names = {source["id"]: source["name"] for source in sources}
    kept = normalize_source_names(
        dedupe_items([item for item in merged.values() if within_retention(item, cutoff) and is_usable_item(item)]),
        source_names,
    )
    kept.sort(key=lambda x: (x.get("date") or "", x.get("collectedAt") or ""), reverse=True)
    kept = kept[:MAX_ITEMS_TOTAL]
    briefing_items = [item for item in kept if within_collection_window(item, window_start, window_end)]
    collected_at = now_kst().isoformat(timespec="seconds")

    status = {
        "ok": all(run["status"] == "success" for run in runs),
        "retentionDays": RETENTION_DAYS,
        "collectionWindowHours": COLLECTION_WINDOW_HOURS,
        "briefingWindowStart": window_start.isoformat(timespec="seconds"),
        "briefingWindowEnd": window_end.isoformat(timespec="seconds"),
        "total": len(kept),
        "briefingTotal": len(briefing_items),
        "newlyCollected": len([item for item in all_new if item["id"] not in {old.get("id") for old in old_items}]),
        "updatedOrCollected": len(all_new),
        "collectedAt": collected_at,
        "runs": runs,
    }
    latest = {
        "collectedAt": status["collectedAt"],
        "windowStart": status["briefingWindowStart"],
        "windowEnd": status["briefingWindowEnd"],
        "total": len(briefing_items),
        "items": briefing_items,
        "runs": runs,
    }

    write_json(NEWS_PATH, kept)
    write_json(LATEST_PATH, latest)
    write_json(STATUS_PATH, status)
    write_json(PUBLIC_SOURCES_PATH, public_sources(sources))

    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
