from __future__ import annotations

import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable

from harness.agents import (
    ClassifierAgent,
    RelevanceFilterAgent,
    ReportWriterAgent,
    ReviewerAgent,
    TrendAnalystAgent,
)
from harness.validators import validate_input


class HarnessInputError(ValueError):
    pass


class EducationTrendHarness:
    def __init__(self, llm: Any, config: dict[str, Any]) -> None:
        self.llm = llm
        self.config = config
        self.trace: list[dict[str, Any]] = []
        self.relevance_filter = RelevanceFilterAgent(
            llm,
            batch_size=int(config.get("batchSize", 6)),
        )
        self.classifier = ClassifierAgent(
            llm,
            categories=config["categories"],
            batch_size=int(config.get("batchSize", 6)),
        )
        self.analyst = TrendAnalystAgent(llm)
        self.writer = ReportWriterAgent(llm)
        self.reviewer = ReviewerAgent(llm)

    def run(self, payload: dict[str, Any], max_items: int | None = None) -> dict[str, Any]:
        self.trace = []
        errors = validate_input(payload)
        if errors:
            raise HarnessInputError("; ".join(errors))

        all_items = payload["items"]
        configured_max = int(self.config.get("maxItems", 0))
        limit = configured_max if max_items is None else max_items
        items = all_items[:limit] if limit and limit > 0 else all_items
        if not items:
            raise HarnessInputError("분석할 보도자료가 없습니다.")

        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        window = self._window(payload)

        relevance_result = self._step(
            "filter_relevance",
            lambda: self.relevance_filter.run(items),
        )
        relevance = relevance_result["items"]
        kept_ids = {
            item["newsId"] for item in relevance if item.get("decision") == "KEEP"
        }
        relevant_items = [item for item in items if item["id"] in kept_ids]

        if not relevant_items:
            return self._empty_result(
                payload=payload,
                all_items=all_items,
                candidate_items=items,
                relevance_result=relevance_result,
                relevance=relevance,
                run_id=run_id,
                window=window,
            )

        classification_result = self._step(
            "classify",
            lambda: self.classifier.run(relevant_items),
        )
        classifications = classification_result["items"]
        analysis = self._step("analyze", lambda: self.analyst.run(classifications))

        source_ids = {item["id"] for item in relevant_items}
        feedback = "없음"
        report: dict[str, Any] = {}
        review: dict[str, Any] = {}
        max_reviews = max(1, int(self.config.get("maxReviewAttempts", 2)))
        for attempt in range(1, max_reviews + 1):
            report = self._step(
                f"write_report_{attempt}",
                lambda feedback=feedback: self.writer.run(analysis, source_ids, window, feedback),
            )
            review = self._step(
                f"review_{attempt}",
                lambda report=report: self.reviewer.run(report, relevant_items),
            )
            if review.get("status") == "PASS":
                break
            feedback = review.get("revisionInstructions") or self._issue_text(review.get("issues", []))

        used_fallback = bool(
            relevance_result.get("fallbackCount")
            or classification_result.get("fallbackCount")
            or analysis.get("fallback")
            or report.get("fallback")
            or review.get("reviewerFallback")
        )
        final_status = "completed" if review.get("status") == "PASS" else "needs_review"
        if final_status == "completed" and used_fallback:
            final_status = "completed_with_fallback"

        source_index = [
            {
                "newsId": item["id"],
                "source": item.get("source") or item.get("sourceName") or item.get("sourceId") or "",
                "title": item.get("title", ""),
                "date": item.get("date") or item.get("publishedAt") or "",
                "url": item.get("url", ""),
            }
            for item in relevant_items
        ]
        category_counts = Counter(item["category"] for item in classifications)

        return {
            "metadata": {
                "runId": run_id,
                "status": final_status,
                "model": getattr(self.llm, "model", self.config.get("model", "unknown")),
                "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "windowStart": payload.get("windowStart"),
                "windowEnd": payload.get("windowEnd"),
                "inputCount": len(all_items),
                "candidateCount": len(items),
                "relevantCount": len(relevant_items),
                "filteredOutCount": len(items) - len(relevant_items),
                "processedCount": len(relevant_items),
                "relevanceFallbackCount": relevance_result.get("fallbackCount", 0),
                "classificationFallbackCount": classification_result.get("fallbackCount", 0),
                "reviewStatus": review.get("status"),
            },
            "categorySummary": [
                {"category": category, "count": count}
                for category, count in category_counts.most_common()
            ],
            "relevance": relevance,
            "classifications": classifications,
            "analysis": analysis,
            "report": report,
            "validation": review,
            "sources": source_index,
            "trace": self.trace,
        }

    def _empty_result(
        self,
        payload: dict[str, Any],
        all_items: list[dict[str, Any]],
        candidate_items: list[dict[str, Any]],
        relevance_result: dict[str, Any],
        relevance: list[dict[str, Any]],
        run_id: str,
        window: str,
    ) -> dict[str, Any]:
        report = {
            "title": f"일일 교육동향 ({window})",
            "executiveSummary": "수집된 후보 보도자료 가운데 광역적 정책 변화나 확산 가능성이 확인된 교육동향은 없었습니다.",
            "keyTrends": [],
            "notableNews": [],
            "watchList": ["다음 수집에서 새 정책·제도·사업 발표 여부를 계속 확인합니다."],
            "fallback": False,
        }
        validation = {
            "status": "PASS",
            "issues": [],
            "revisionInstructions": "",
            "deterministicChecks": [],
            "note": "분석 대상이 0건이므로 빈 결과 규칙을 적용했습니다.",
        }
        return {
            "metadata": {
                "runId": run_id,
                "status": (
                    "completed_with_fallback"
                    if relevance_result.get("fallbackCount")
                    else "completed"
                ),
                "model": getattr(self.llm, "model", self.config.get("model", "unknown")),
                "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "windowStart": payload.get("windowStart"),
                "windowEnd": payload.get("windowEnd"),
                "inputCount": len(all_items),
                "candidateCount": len(candidate_items),
                "relevantCount": 0,
                "filteredOutCount": len(candidate_items),
                "processedCount": 0,
                "relevanceFallbackCount": relevance_result.get("fallbackCount", 0),
                "classificationFallbackCount": 0,
                "reviewStatus": "PASS",
            },
            "categorySummary": [],
            "relevance": relevance,
            "classifications": [],
            "analysis": {
                "headline": "교육동향 분석 대상 없음",
                "overview": report["executiveSummary"],
                "trends": [],
                "notableNewsIds": [],
                "fallback": False,
            },
            "report": report,
            "validation": validation,
            "sources": [],
            "trace": self.trace,
        }

    def _step(self, name: str, function: Callable[[], Any]) -> Any:
        started = time.perf_counter()
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            value = function()
            self.trace.append(
                {
                    "step": name,
                    "status": "success",
                    "startedAt": timestamp,
                    "durationMs": round((time.perf_counter() - started) * 1000),
                }
            )
            return value
        except Exception as error:
            self.trace.append(
                {
                    "step": name,
                    "status": "failed",
                    "startedAt": timestamp,
                    "durationMs": round((time.perf_counter() - started) * 1000),
                    "error": str(error)[:500],
                }
            )
            raise

    @staticmethod
    def _window(payload: dict[str, Any]) -> str:
        start = str(payload.get("windowStart") or "기간 미상")
        end = str(payload.get("windowEnd") or "기간 미상")
        return f"{start[:16]} ~ {end[:16]}"

    @staticmethod
    def _issue_text(issues: list[dict[str, Any]]) -> str:
        return " / ".join(str(item.get("message", "")) for item in issues if item.get("message")) or "근거와 형식을 재검토하세요."
