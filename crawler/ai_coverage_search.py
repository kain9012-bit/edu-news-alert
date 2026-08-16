"""구글 검색 연동 AI로 언론 게재 기사를 보완 수집한다.

구글 뉴스 RSS는 색인 범위가 좁아 실제 게재된 기사를 상당수 놓친다. 이 스크립트는
Gemini의 구글 검색 연동(grounding)으로 웹 전체를 훑어 기사를 더 찾아낸다.

중요한 원칙: **모든 보도자료에 똑같이 적용한다.** 못 찾은 자료에만 쓰면 그 자료에만
다른 매체가 붙어 부서별·자료별 비교가 어긋나기 때문이다. 자료마다 정확히 한 번씩
검색하고 그 사실을 기록해, 다음 실행에서는 건너뛴다.

비용: 구글 검색 연동은 월 5,000건까지 무료다. 새 보도자료가 하루 3건 안팎이라
월 70건 수준이며, 과거분을 채울 때도 한 번 실행당 호출 수를 강제로 제한한다.

지어낸 주소를 막기 위해 모델의 답변 문장이 아니라 검색 근거로 제시된 출처만 쓰고,
실제로 열리는 주소인지 확인한 뒤 저장한다. 기사 본문은 저장하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_coverage import (  # noqa: E402
    days_apart,
    has_other_region,
    has_region_hint,
    is_other_organization,
    similarity,
    summarize_departments,
    tokenize,
)

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
USER_AGENT = "Mozilla/5.0 (compatible; jbe-edu-trends/1.0) coverage-search"
FETCH_INTERVAL = 0.8
CALL_INTERVAL = 1.5
# 날짜를 알 수 없는 기사는 제목이 이만큼 닮아야 인정한다.
UNDATED_MIN_SCORE = 0.4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI 검색으로 언론 게재 기사 보완 수집")
    parser.add_argument("--coverage", default="public/coverage.json", help="게재현황 JSON")
    parser.add_argument("--model", default="gemini-3.1-flash-lite", help="사용할 모델")
    parser.add_argument(
        "--max-calls", type=int, default=25, help="한 번 실행에서 허용할 최대 검색 호출 수"
    )
    parser.add_argument("--window-before", type=int, default=4, help="배포일 이 일수 전까지 인정")
    parser.add_argument("--window-after", type=int, default=10, help="배포일 이 일수 후까지 인정")
    parser.add_argument("--min-score", type=float, default=0.22, help="제목 유사도 최소값")
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 결과만 출력")
    return parser.parse_args()


def search_sources(api_key: str, model: str, title: str, subtitle: str, release_date: str):
    """구글 검색을 붙여 질의하고, 근거로 제시된 출처(제목·링크)를 돌려준다."""
    hint = f"\n부제: {subtitle}" if subtitle else ""
    prompt = (
        "전북특별자치도교육청이 아래 보도자료를 배포했습니다. "
        "이 보도자료를 기사로 다룬 국내 언론 보도를 구글에서 찾아 주세요.\n\n"
        f"제목: {title}{hint}\n배포일: {release_date}\n\n"
        "같은 사안을 다룬 기사만 찾고, 언론사명과 기사 제목을 나열해 주세요."
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 1024},
    }
    try:
        response = requests.post(
            API_URL.format(model=model),
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=90,
        )
    except requests.RequestException as exc:
        print(f"   호출 실패: {exc}", file=sys.stderr)
        return [], False
    if not response.ok:
        print(f"   호출 실패({response.status_code}): {response.text[:180]}", file=sys.stderr)
        return [], False

    data = response.json()
    sources: list[dict[str, str]] = []
    for candidate in data.get("candidates", []) or []:
        meta = candidate.get("groundingMetadata") or {}
        for chunk in meta.get("groundingChunks", []) or []:
            web = chunk.get("web") or {}
            if web.get("uri") and web.get("title"):
                sources.append(
                    {
                        "url": web["uri"],
                        "title": web["title"],
                        "publisher": web.get("domain", ""),
                    }
                )
    return sources, True


def resolve_article(session: requests.Session, url: str) -> tuple[str, str, str] | None:
    """실제로 열리는 기사인지 확인하고 최종 주소·제목·보도일을 얻는다."""
    try:
        response = session.get(url, timeout=(5, 20), allow_redirects=True)
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    html = response.text
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    title = re.sub(r"\s+", " ", match.group(1)).strip() if match else ""
    # 기사 제목 뒤에 붙는 매체명 꼬리표를 떼어낸다.
    title = re.split(r"\s*[-|｜<]\s*", title)[0].strip() if title else ""
    published = ""
    date_match = re.search(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", html)
    if date_match:
        published = "{}-{:02d}-{:02d}".format(
            date_match.group(1), int(date_match.group(2)), int(date_match.group(3))
        )
    return response.url, title, published


def publisher_name(url: str, fallback: str) -> str:
    if fallback:
        return fallback
    return urllib.parse.urlsplit(url).netloc.replace("www.", "")


def acceptable(
    article_title: str, score: float, published: str, release_date: str, args: argparse.Namespace
) -> bool:
    if is_other_organization(article_title):
        return False
    if has_other_region(article_title) and not has_region_hint(article_title):
        return False
    gap = days_apart(published, release_date)
    if gap is None:
        return score >= UNDATED_MIN_SCORE
    if gap > max(args.window_before, args.window_after):
        return False
    return score >= args.min_score


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("GEMINI_API_KEY가 없어 AI 보완 검색을 건너뜁니다.", file=sys.stderr)
        return 0

    path = Path(args.coverage)
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items", [])

    # 아직 AI 검색을 하지 않은 자료를 최신순으로 처리한다(모든 자료가 대상).
    targets = [e for e in items if not e.get("aiSearched")]
    targets.sort(key=lambda e: e.get("date", ""), reverse=True)
    targets = targets[: args.max_calls]
    remaining = sum(1 for e in items if not e.get("aiSearched")) - len(targets)
    if not targets:
        print("AI 검색이 필요한 자료가 없습니다.")
        return 0
    print(f"대상 {len(targets)}건 처리 (남은 자료 {remaining}건은 다음 실행에서)")

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    added_total = 0

    for index, entry in enumerate(targets, 1):
        title = entry.get("title", "")
        release_date = entry.get("date", "")
        subtitle = entry.get("subtitle") or ""
        print(f"[{index}/{len(targets)}] {release_date} {title[:40]}")

        tokens = tokenize(title)
        subtitle_tokens = tokenize(subtitle)
        existing = {a["url"] for a in entry.get("articles", []) or []}

        sources, ok = search_sources(api_key, args.model, title, subtitle, release_date)
        if not ok:
            break  # 호출이 실패하면 한도 문제일 수 있으므로 즉시 중단한다.
        entry["aiSearched"] = True

        added: list[dict[str, str]] = []
        for source in sources:
            time.sleep(FETCH_INTERVAL)
            resolved = resolve_article(session, source["url"])
            if not resolved:
                continue
            final_url, page_title, published = resolved
            article_title = page_title or source["title"]
            if final_url in existing:
                continue
            score = max(
                similarity(tokens, article_title), similarity(subtitle_tokens, article_title)
            )
            if not acceptable(article_title, score, published, release_date, args):
                continue
            existing.add(final_url)
            added.append(
                {
                    "title": article_title[:120],
                    "publisher": publisher_name(final_url, source.get("publisher", "")),
                    "publishedAt": published,
                    "url": final_url,
                    "via": "ai",
                }
            )

        if added:
            entry.setdefault("articles", [])
            entry["articles"].extend(added)
            entry["articles"].sort(key=lambda a: (a.get("publishedAt") or "", a.get("publisher") or ""))
            entry["articleCount"] = len(entry["articles"])
            added_total += len(added)
            for article in added:
                print(f"      + {article['publisher']} | {article['title'][:46]}")
        else:
            print("      추가 없음")
        time.sleep(CALL_INTERVAL)

    payload["coveredCount"] = sum(1 for e in items if e.get("articleCount"))
    payload["articleCount"] = sum(int(e.get("articleCount") or 0) for e in items)
    publishers: dict[str, int] = {}
    for entry in items:
        for article in entry.get("articles", []) or []:
            name = article.get("publisher", "미상")
            publishers[name] = publishers.get(name, 0) + 1
    payload["publishers"] = [
        {"name": name, "count": count}
        for name, count in sorted(publishers.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    payload["departments"] = summarize_departments(items)

    if args.dry_run:
        print(f"\n(시험 실행) 추가 예정 {added_total}건")
        return 0

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n저장 완료: 기사 {added_total}건 추가 · 총 {payload['articleCount']}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
