from __future__ import annotations

import json
from typing import Any

from harness.utils import render_prompt
from harness.validators import validate_report


class ReportWriterAgent:
    name = "report_writer"

    def __init__(self, llm: Any, max_attempts: int = 2) -> None:
        self.llm = llm
        self.max_attempts = max(1, max_attempts)

    def run(
        self,
        analysis: dict[str, Any],
        source_ids: set[str],
        window: str,
        review_feedback: str = "없음",
    ) -> dict[str, Any]:
        attempts = 0
        for _ in range(self.max_attempts):
            attempts += 1
            prompt = render_prompt(
                "report_writer.md",
                WINDOW=window,
                ANALYSIS_JSON=json.dumps(analysis, ensure_ascii=False),
                REVIEW_FEEDBACK=review_feedback or "없음",
            )
            try:
                value = self.llm.generate_json(prompt)
                if not validate_report(value, source_ids):
                    return {**value, "attempts": attempts, "fallback": False}
            except Exception:
                continue
        return {**self._fallback(analysis, window), "attempts": attempts, "fallback": True}

    @staticmethod
    def _fallback(analysis: dict[str, Any], window: str) -> dict[str, Any]:
        trends = analysis.get("trends", [])
        notable_ids = analysis.get("notableNewsIds", [])
        return {
            "title": f"일일 교육동향 ({window})",
            "executiveSummary": analysis.get("overview", "수집된 보도자료를 업무 주제별로 분석했다."),
            "keyTrends": [
                {
                    "title": item.get("title", "교육동향"),
                    "description": item.get("description", ""),
                    "evidenceIds": item.get("evidenceIds", []),
                }
                for item in trends
            ],
            "notableNews": [
                {"newsId": news_id, "reason": "중요도 또는 정책 파급력을 기준으로 선정"}
                for news_id in notable_ids
            ],
            "watchList": ["후속 보도자료와 기관별 세부 시행계획을 계속 확인할 필요가 있다."],
        }
