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
RETENTION_DAYS = int(__import__("os").environ.get("RETENTION_DAYS", "7"))
MAX_ITEMS_TOTAL = int(__import__("os").environ.get("MAX_ITEMS_TOTAL", "1000"))
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


def now_kst() -> datetime:
    return datetime.now(KST)


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


def fetch_text(url: str) -> str:
    res = SESSION.get(url, timeout=TIMEOUT_SECONDS)
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
    for key in ["bbsId", "mi", "boardID", "m", "s"]:
        if key in list_query:
            params[key] = list_query[key][0]
    return add_query(urljoin(source["baseUrl"], detail_path), params)


def collect_links(source: dict[str, Any], html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    links: list[dict[str, str]] = []

    for a in soup.find_all("a"):
        href = a.get("href") or ""
        title = normalize_space(a.get_text(" "))
        if not href:
            continue
        url = urljoin(source["baseUrl"], href)
        if url_matches(url, source) and url not in seen:
            seen.add(url)
            links.append({"url": url, "title": title})

    seq_param = source.get("seqParam")
    if seq_param:
        for tag in soup.find_all(True):
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
                    match = re.search(r"\b(\d{4,})\b", onclick)
                if match:
                    seq = match.group(1)
            url = detail_url_from_seq(source, seq or "")
            title = normalize_space(tag.get_text(" "))
            if url and url_matches(url, source) and url not in seen:
                seen.add(url)
                links.append({"url": url, "title": title})

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


def extract_title(soup: BeautifulSoup, fallback: str) -> str:
    for selector in ["h1", "h2", "h3", "h4", ".title", ".view_title", ".view-title", ".tit"]:
        found = soup.select_one(selector)
        if found:
            text = normalize_space(found.get_text(" "))
            if len(text) >= 4:
                return text
    if soup.title:
        title = normalize_space(soup.title.get_text(" "))
        if title:
            return title
    return fallback or "제목 없음"


def extract_summary(soup: BeautifulSoup) -> str:
    candidates = []
    for selector in ["main", "article", "#contents", ".board_view", ".news_view", ".view_cont", ".bbsV_cont", ".view-content"]:
        found = soup.select_one(selector)
        if found:
            candidates.append(found.get_text(" "))
    candidates.append(soup.get_text(" "))
    for text in candidates:
        cleaned = normalize_space(text)
        if len(cleaned) > 40:
            return cleaned[:350]
    return ""


def collect_detail(source: dict[str, Any], link: dict[str, str]) -> dict[str, Any]:
    html = fetch_text(link["url"])
    soup = BeautifulSoup(html, "lxml")
    all_text = soup.get_text(" ")
    title = extract_title(soup, link.get("title", ""))
    date = parse_date(all_text)
    summary = extract_summary(soup)
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


def collect_source(source: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = now_kst().isoformat(timespec="seconds")
    try:
        html = fetch_text(source["listUrl"])
        links = collect_links(source, html)
        items = []
        for link in links:
            try:
                items.append(collect_detail(source, link))
            except Exception as exc:
                print(f"detail failed {source['id']} {link['url']}: {exc}")
        return items, {
            "sourceId": source["id"],
            "source": source["name"],
            "status": "success",
            "fetched": len(items),
            "startedAt": started,
            "finishedAt": now_kst().isoformat(timespec="seconds"),
        }
    except Exception as exc:
        return [], {
            "sourceId": source["id"],
            "source": source["name"],
            "status": "failed",
            "fetched": 0,
            "error": str(exc)[:500],
            "startedAt": started,
            "finishedAt": now_kst().isoformat(timespec="seconds"),
        }


def within_retention(item: dict[str, Any], cutoff: datetime) -> bool:
    for key in ["date", "collectedAt"]:
        value = item.get(key)
        if not value:
            continue
        try:
            dt = date_parser.parse(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=KST)
            if dt >= cutoff:
                return True
        except Exception:
            pass
    return False


def main() -> None:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    sources = [s for s in read_json(SOURCES_PATH, []) if s.get("enabled", True)]
    old_items = read_json(NEWS_PATH, [])

    all_new: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    for source in sources:
        print(f"collect {source['id']} {source['name']}")
        items, run = collect_source(source)
        all_new.extend(items)
        runs.append(run)

    merged: dict[str, dict[str, Any]] = {item.get("id", ""): item for item in old_items if item.get("id")}
    for item in all_new:
        merged[item["id"]] = {**merged.get(item["id"], {}), **item}

    cutoff = now_kst() - timedelta(days=RETENTION_DAYS)
    kept = [item for item in merged.values() if within_retention(item, cutoff)]
    kept.sort(key=lambda x: (x.get("date") or "", x.get("collectedAt") or ""), reverse=True)
    kept = kept[:MAX_ITEMS_TOTAL]

    status = {
        "ok": all(run["status"] == "success" for run in runs),
        "retentionDays": RETENTION_DAYS,
        "total": len(kept),
        "newlyCollected": len(all_new),
        "collectedAt": now_kst().isoformat(timespec="seconds"),
        "runs": runs,
    }
    latest = {
        "collectedAt": status["collectedAt"],
        "items": kept[:50],
        "runs": runs,
    }

    write_json(NEWS_PATH, kept)
    write_json(LATEST_PATH, latest)
    write_json(STATUS_PATH, status)
    write_json(PUBLIC_SOURCES_PATH, [{"id": s["id"], "name": s["name"], "enabled": s.get("enabled", True)} for s in sources])

    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
