from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

from harness.utils import render_prompt
from harness.validators import validate_analysis


class TrendAnalystAgent:
    name = "trend_analyst"

    def __init__(self, llm: Any, max_attempts: int = 2) -> None:
        self.llm = llm
        self.max_attempts = max(1, max_attempts)

    def run(self, classifications: list[dict[str, Any]]) -> dict[str, Any]:
        source_ids = {item["newsId"] for item in classifications}
        analysis_input = self._analysis_input(classifications)
        attempts = 0
        for _ in range(self.max_attempts):
            attempts += 1
            prompt = render_prompt(
                "trend_analyst.md",
                ANALYSIS_INPUT=json.dumps(analysis_input, ensure_ascii=False),
            )
            try:
                value = self.llm.generate_json(prompt)
                if not validate_analysis(value, source_ids):
                    return {**value, "attempts": attempts, "fallback": False}
            except Exception:
                continue
        return {**self._fallback(classifications), "attempts": attempts, "fallback": True}

    @staticmethod
    def _analysis_input(classifications: list[dict[str, Any]]) -> dict[str, Any]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in classifications:
            grouped[item["category"]].append(item)

        categories = []
        for category, items in sorted(grouped.items(), key=lambda pair: len(pair[1]), reverse=True):
            samples = sorted(items, key=lambda item: {"high": 0, "medium": 1, "low": 2}.get(item["importance"], 3))[:12]
            categories.append(
                {
                    "category": category,
                    "count": len(items),
                    "sources": sorted({item.get("source", "") for item in items}),
                    "samples": [
                        {
                            "newsId": item["newsId"],
                            "source": item.get("source", ""),
                            "title": item.get("title", ""),
                            "summary": item.get("summary", "")[:220],
                            "importance": item["importance"],
                        }
                        for item in samples
                    ],
                }
            )
        return {"total": len(classifications), "categories": categories}

    @staticmethod
    def _fallback(classifications: list[dict[str, Any]]) -> dict[str, Any]:
        counts = Counter(item["category"] for item in classifications)
        trends = []
        for category, count in counts.most_common(4):
            items = [item for item in classifications if item["category"] == category]
            sources = sorted({item.get("source", "") for item in items if item.get("source")})
            trends.append(
                {
                    "title": f"{category} 관련 동향",
                    "description": f"{len(sources)}개 기관에서 {count}건의 관련 보도자료가 확인됐다.",
                    "categories": [category],
                    "evidenceIds": [item["newsId"] for item in items[:5]],
                }
            )
        return {
            "headline": "최근 24시간 교육동향",
            "overview": f"총 {len(classifications)}건의 보도자료를 업무 주제별로 분석했다.",
            "trends": trends,
            "notableNewsIds": [
                item["newsId"] for item in classifications if item["importance"] == "high"
            ][:8],
        }
