"""구글 뉴스 검색에서 못 찾은 보도자료를, 구글 검색 연동 AI로 한 번 더 확인한다.

구글 뉴스 RSS는 색인 범위가 좁아 실제로 실린 기사를 놓치는 일이 잦다. 그 결과
'확인 안 됨'으로 남은 자료가 마치 보도되지 않은 것처럼 보이는 문제가 있다.

이 스크립트는 기사를 찾지 못한 자료만 골라, Gemini의 구글 검색 연동(grounding)으로
실제 기사 링크를 받아온다. 모델이 지어낸 주소를 걸러내기 위해 근거로 제시된
검색 출처(groundingMetadata)만 사용하고, 실제로 열리는 주소인지 확인한 뒤 저장한다.

비용 보호: 한 번 실행에 호출 수를 강제로 제한하며, 이미 확인한 자료는 다시 묻지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import date
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
USER_AGENT = "Mozilla/5.0 (compatible; jbe-edu-trends/1.0) coverage-verifier"
REQUEST_INTERVAL = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="확인 안 된 보도자료의 기사 보완 검색")
    parser.add_argument("--coverage", default="public/coverage.json", help="게재현황 JSON")
    parser.add_argument("--model", default="gemini-3.1-flash-lite", help="사용할 모델")
    parser.add_argument(
        "--max-calls", type=int, default=5, help="한 번 실행에서 허용할 최대 AI 호출 수"
    )
    parser.add_argument("--window", type=int, default=10, help="배포일 기준 며칠 이내 기사만 인정")
    parser.add_argument("--min-score", type=float, default=0.2, help="제목 유사도 최소값")
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 결과만 출력")
    return parser.parse_args()


def ask_gemini(api_key: str, model: str, title: str, release_date: str) -> list[dict[str, str]]:
    """구글 검색을 붙여 질의하고, 근거로 제시된 출처 목록을 돌려준다."""
    prompt = (
        "전북특별자치도교육청이 아래 보도자료를 배포했습니다. "
        "이 보도자료를 다룬 국내 언론 기사를 구글에서 찾아 주세요.\n\n"
        f"제목: {title}\n배포일: {release_date}\n\n"
        "찾은 기사들의 언론사명과 기사 제목을 간단히 나열해 주세요. "
        "같은 사안을 다룬 기사만 포함하고, 없으면 '없음'이라고 답하세요."
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 1024},
    }
    response = requests.post(
        API_URL.format(model=model),
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=90,
    )
    if not response.ok:
        print(f"  AI 호출 실패({response.status_code}): {response.text[:200]}", file=sys.stderr)
        return []

    data = response.json()
    sources: list[dict[str, str]] = []
    for candidate in data.get("candidates", []) or []:
        meta = candidate.get("groundingMetadata") or {}
        for chunk in meta.get("groundingChunks", []) or []:
            web = chunk.get("web") or {}
            uri, chunk_title = web.get("uri"), web.get("title")
            if uri and chunk_title:
                sources.append({"url": uri, "title": chunk_title, "publisher": web.get("domain", "")})
    return sources


def resolve_url(session: requests.Session, url: str) -> tuple[str, str] | None:
    """리디렉션을 따라가 실제로 열리는 기사인지 확인하고 최종 주소·제목을 얻는다."""
    try:
        response = session.get(url, timeout=(5, 20), allow_redirects=True)
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    final = response.url
    match = re.search(r"<title[^>]*>(.*?)</title>", response.text, re.S | re.I)
    page_title = re.sub(r"\s+", " ", match.group(1)).strip() if match else ""
    return final, page_title


def publisher_from_url(url: str, fallback: str) -> str:
    host = urllib.parse.urlsplit(url).netloc.replace("www.", "")
    return fallback or host


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("GEMINI_API_KEY가 없어 보완 검색을 건너뜁니다.", file=sys.stderr)
        return 0

    path = Path(args.coverage)
    payload = json.loads(path.read_text(encoding="utf-8"))
    targets = [
        entry
        for entry in payload.get("items", [])
        if not entry.get("articleCount") and not entry.get("aiChecked")
    ]
    if not targets:
        print("보완 검색이 필요한 자료가 없습니다.")
        return 0

    targets.sort(key=lambda e: e.get("date", ""), reverse=True)
    targets = targets[: args.max_calls]
    print(f"보완 검색 대상 {len(targets)}건 (최대 호출 {args.max_calls}회)")

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    added_total = 0

    for entry in targets:
        title = entry.get("title", "")
        release_date = entry.get("date", "")
        print(f"\n■ {release_date} {title[:44]}")
        tokens = tokenize(title)
        subtitle_tokens = tokenize(entry.get("subtitle") or "")

        sources = ask_gemini(api_key, args.model, title, release_date)
        print(f"   검색 출처 {len(sources)}건")
        found: list[dict[str, str]] = []
        seen: set[str] = set()

        for source in sources:
            time.sleep(REQUEST_INTERVAL)
            resolved = resolve_url(session, source["url"])
            if not resolved:
                continue
            final_url, page_title = resolved
            article_title = page_title or source["title"]
            # 지어낸 링크·다른 기관 기사를 규칙으로 다시 걸러낸다.
            if is_other_organization(article_title):
                continue
            if has_other_region(article_title) and not has_region_hint(article_title):
                continue
            score = max(
                similarity(tokens, article_title), similarity(subtitle_tokens, article_title)
            )
            if score < args.min_score:
                continue
            if final_url in seen:
                continue
            seen.add(final_url)
            found.append(
                {
                    "title": article_title[:120],
                    "publisher": publisher_from_url(final_url, source.get("publisher", "")),
                    "publishedAt": "",
                    "url": final_url,
                    "via": "ai-search",
                }
            )

        entry["aiChecked"] = True
        if found:
            entry["articles"] = found
            entry["articleCount"] = len(found)
            added_total += len(found)
            for article in found:
                print(f"      + {article['publisher']} | {article['title'][:50]}")
        else:
            print("      추가 없음")

    payload["coveredCount"] = sum(1 for e in payload["items"] if e.get("articleCount"))
    payload["articleCount"] = sum(int(e.get("articleCount") or 0) for e in payload["items"])
    publishers: dict[str, int] = {}
    for entry in payload["items"]:
        for article in entry.get("articles", []) or []:
            name = article.get("publisher", "미상")
            publishers[name] = publishers.get(name, 0) + 1
    payload["publishers"] = [
        {"name": name, "count": count}
        for name, count in sorted(publishers.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    payload["departments"] = summarize_departments(payload["items"])

    if args.dry_run:
        print(f"\n(시험 실행) 추가 예정 {added_total}건")
        return 0

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n저장 완료: 기사 {added_total}건 추가 · 총 {payload['articleCount']}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
