from __future__ import annotations

import json
from typing import Any

from harness.utils import chunks, compact_news, render_prompt
from harness.validators import validate_relevance


SYSTEM_TREND_WORDS = [
    "정책",
    "제도",
    "예산",
    "교육과정",
    "전면 시행",
    "확대 운영",
    "종합 대책",
    "기본계획",
    "개편",
    "전체 학교",
    "전 학교",
    "지원 계획",
]
LOCAL_OR_INSTITUTION_WORDS = [
    "교육지원청",
    "교육연수원",
    "학생교육문화회관",
    "교육문화회관",
    "도서관",
    "초등학교",
    "중학교",
    "고등학교",
]
ONE_OFF_WORDS = ["방문", "내방", "공연", "전시", "대회", "수상", "체험", "캠페인", "봉사", "업무협약", "간담회"]


class RelevanceFilterAgent:
    name = "relevance_filter"

    def __init__(self, llm: Any, batch_size: int = 6, max_attempts: int = 2) -> None:
        self.llm = llm
        self.batch_size = max(1, batch_size)
        self.max_attempts = max(1, max_attempts)

    def run(self, news_items: list[dict[str, Any]]) -> dict[str, Any]:
        output: list[dict[str, Any]] = []
        attempts = 0
        fallback_count = 0
        errors: list[dict[str, Any]] = []

        for batch in chunks(news_items, self.batch_size):
            compact = [compact_news(item) for item in batch]
            expected_ids = {item["newsId"] for item in compact}
            source_map = {item["newsId"]: item for item in compact}
            accepted: list[dict[str, Any]] | None = None
            last_error = ""

            for _ in range(self.max_attempts):
                attempts += 1
                prompt = render_prompt(
                    "relevance_filter.md",
                    ITEMS_JSON=json.dumps(compact, ensure_ascii=False),
                )
                try:
                    raw = self.llm.generate_json(prompt)
                    values = raw.get("items") if isinstance(raw, dict) else raw
                    if not validate_relevance(values, expected_ids):
                        accepted = [self._enrich(item, source_map[item["newsId"]]) for item in values]
                        break
                except Exception as error:
                    last_error = str(error)[:500]
                    continue

            if accepted is None:
                accepted = [self._fallback(item) for item in compact]
                fallback_count += len(accepted)
                errors.append({"newsIds": sorted(expected_ids), "error": last_error or "응답 계약 검증 실패"})
            output.extend(accepted)

        return {
            "items": output,
            "attempts": attempts,
            "fallbackCount": fallback_count,
            "errors": errors,
        }

    @staticmethod
    def _enrich(value: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
        return {
            **value,
            "source": source["source"],
            "title": source["title"],
            "date": source["date"],
        }

    @staticmethod
    def _fallback(item: dict[str, Any]) -> dict[str, Any]:
        text = f"{item['title']} {item['summary']}"
        has_system_signal = any(word in text for word in SYSTEM_TREND_WORDS)
        has_local_signal = any(word in text for word in LOCAL_OR_INSTITUTION_WORDS)
        has_one_off_signal = any(word in text for word in ONE_OFF_WORDS)
        drop = not has_system_signal and has_local_signal and has_one_off_signal
        scope = "institution" if has_local_signal else "provincial"
        return {
            "newsId": item["newsId"],
            "decision": "DROP" if drop else "KEEP",
            "scope": scope,
            "reason": (
                "개별 기관의 일회성 활동으로 판단되어 교육동향 분석에서 제외했다."
                if drop
                else "정책 또는 다수 학교에 영향을 줄 가능성이 있어 교육동향 분석 대상으로 유지했다."
            ),
            "confidence": 0.25,
            "evidenceIds": [item["newsId"]],
            "source": item["source"],
            "title": item["title"],
            "date": item["date"],
            "fallback": True,
        }
