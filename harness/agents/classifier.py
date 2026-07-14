from __future__ import annotations

import json
from typing import Any

from harness.utils import chunks, compact_news, normalize_space, render_prompt
from harness.validators import validate_classifications


CATEGORY_RULES = {
    "디지털·AI": ["인공지능", " ai ", "디지털", "에듀테크", "소프트웨어", "정보교육"],
    "안전·시설": ["안전", "재난", "폭염", "급식", "시설", "공사", "통학"],
    "교원·인사": ["교원", "교사", "교감", "교장", "연수", "인사", "교직원"],
    "학생지원·복지": ["학생지원", "복지", "돌봄", "상담", "장학금", "취약계층", "학교폭력"],
    "진로·직업교육": ["진로", "직업", "취업", "특성화고", "마이스터고"],
    "교육과정·수업": ["교육과정", "수업", "학습", "독서", "기초학력", "방학"],
    "정책·행정": ["정책", "조례", "예산", "감사", "행정", "업무", "협약"],
    "지역협력·행사": ["협력", "협약", "행사", "대회", "공연", "전시", "캠페인"],
}


class ClassifierAgent:
    name = "classifier"

    def __init__(self, llm: Any, categories: list[str], batch_size: int = 6, max_attempts: int = 2) -> None:
        self.llm = llm
        self.categories = categories
        self.batch_size = max(1, batch_size)
        self.max_attempts = max(1, max_attempts)

    def run(self, news_items: list[dict[str, Any]]) -> dict[str, Any]:
        output: list[dict[str, Any]] = []
        attempts = 0
        fallback_count = 0

        for batch in chunks(news_items, self.batch_size):
            compact = [compact_news(item) for item in batch]
            expected_ids = {item["newsId"] for item in compact}
            source_map = {item["newsId"]: item for item in compact}
            accepted: list[dict[str, Any]] | None = None

            for _ in range(self.max_attempts):
                attempts += 1
                prompt = render_prompt(
                    "classifier.md",
                    CATEGORIES=", ".join(self.categories),
                    ITEMS_JSON=json.dumps(compact, ensure_ascii=False),
                )
                try:
                    raw = self.llm.generate_json(prompt)
                    values = raw.get("items") if isinstance(raw, dict) else raw
                    errors = validate_classifications(values, expected_ids, set(self.categories))
                    if not errors:
                        accepted = [self._enrich(item, source_map[item["newsId"]]) for item in values]
                        break
                except Exception:
                    continue

            if accepted is None:
                accepted = [self._fallback(item) for item in compact]
                fallback_count += len(accepted)
            output.extend(accepted)

        return {
            "items": output,
            "attempts": attempts,
            "fallbackCount": fallback_count,
        }

    @staticmethod
    def _enrich(value: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
        return {
            **value,
            "source": source["source"],
            "title": source["title"],
            "date": source["date"],
        }

    def _fallback(self, item: dict[str, Any]) -> dict[str, Any]:
        text = f" {item['title']} {item['summary']} ".lower()
        category = "기타"
        matched: list[str] = []
        for candidate, keywords in CATEGORY_RULES.items():
            hits = [keyword.strip() for keyword in keywords if keyword in text]
            if hits:
                category = candidate if candidate in self.categories else "기타"
                matched = hits
                break
        summary = normalize_space(item.get("summary", ""))[:180] or item["title"]
        importance = "high" if any(word in text for word in ["전국", "정책", "안전", "예산", "개편"]) else "medium"
        return {
            "newsId": item["newsId"],
            "category": category,
            "importance": importance,
            "keywords": (matched or [category])[:5],
            "summary": summary,
            "confidence": 0.25,
            "evidenceIds": [item["newsId"]],
            "source": item["source"],
            "title": item["title"],
            "date": item["date"],
            "fallback": True,
        }
