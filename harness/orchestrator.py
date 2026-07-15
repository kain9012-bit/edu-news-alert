from __future__ import annotations

import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable

from harness.agents import ClassifierAgent, RelevanceFilterAgent, SelectionValidatorAgent
from harness.validators import validate_input


class HarnessInputError(ValueError):
    pass


class EducationTrendHarness:
    def __init__(self, llm: Any, config: dict[str, Any]) -> None:
        self.llm = llm
        self.config = config
        self.trace: list[dict[str, Any]] = []
        batch_size = int(config.get("batchSize", 6))
        self.relevance_filter = RelevanceFilterAgent(llm, batch_size=batch_size)
        self.classifier = ClassifierAgent(
            llm,
            categories=config["categories"],
            batch_size=batch_size,
        )
        self.validator = SelectionValidatorAgent(config["categories"])

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
        relevance_result = self._step(
            "filter_relevance",
            lambda: self.relevance_filter.run(items),
        )
        relevance = relevance_result["items"]
        kept_ids = {
            item["newsId"] for item in relevance if item.get("decision") == "KEEP"
        }
        relevant_items = [item for item in items if item["id"] in kept_ids]

        classification_result = (
            self._step("classify", lambda: self.classifier.run(relevant_items))
            if relevant_items
            else {"items": [], "attempts": 0, "fallbackCount": 0}
        )
        classifications = classification_result["items"]
        validation = self._step(
            "validate_selection",
            lambda: self.validator.run(items, relevance, classifications),
        )

        used_fallback = bool(
            relevance_result.get("fallbackCount")
            or classification_result.get("fallbackCount")
        )
        final_status = "completed" if validation["status"] == "PASS" else "needs_review"
        if final_status == "completed" and used_fallback:
            final_status = "completed_with_fallback"

        relevance_map = {item["newsId"]: item for item in relevance}
        classification_map = {item["newsId"]: item for item in classifications}
        selected_items = [
            self._selected_item(item, relevance_map[item["id"]], classification_map[item["id"]])
            for item in relevant_items
            if item["id"] in relevance_map and item["id"] in classification_map
        ]
        excluded_items = [
            self._excluded_item(item, relevance_map[item["id"]])
            for item in items
            if item["id"] in relevance_map and relevance_map[item["id"]].get("decision") == "DROP"
        ]
        category_counts = Counter(item["category"] for item in classifications)

        return {
            "metadata": {
                "runId": run_id,
                "status": final_status,
                "provider": getattr(self.llm, "provider", "unknown"),
                "model": getattr(self.llm, "model", self.config.get("model", "unknown")),
                "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "windowStart": payload.get("windowStart"),
                "windowEnd": payload.get("windowEnd"),
                "inputCount": len(all_items),
                "candidateCount": len(items),
                "relevantCount": len(selected_items),
                "filteredOutCount": len(excluded_items),
                "processedCount": len(selected_items),
                "relevanceFallbackCount": relevance_result.get("fallbackCount", 0),
                "institutionGuardCount": relevance_result.get("guardCount", 0),
                "classificationFallbackCount": classification_result.get("fallbackCount", 0),
                "validationStatus": validation["status"],
                "usage": getattr(self.llm, "usage", {}),
            },
            "categorySummary": [
                {"category": category, "count": count}
                for category, count in category_counts.most_common()
            ],
            "selectedItems": selected_items,
            "excludedItems": excluded_items,
            "relevance": relevance,
            "classifications": classifications,
            "validation": validation,
            "providerErrors": {
                "relevance": relevance_result.get("errors", []),
                "classification": classification_result.get("errors", []),
            },
            "trace": self.trace,
        }

    @staticmethod
    def _selected_item(
        source: dict[str, Any],
        relevance: dict[str, Any],
        classification: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "newsId": source["id"],
            "sourceId": source.get("sourceId", ""),
            "source": source.get("source") or source.get("sourceName") or source.get("sourceId") or "",
            "title": source.get("title", ""),
            "date": source.get("date") or source.get("publishedAt") or "",
            "url": source.get("url", ""),
            "category": classification["category"],
            "importance": classification["importance"],
            "keywords": classification["keywords"],
            "summary": classification["summary"],
            "selectionReason": relevance["reason"],
            "scope": relevance["scope"],
            "relevanceConfidence": relevance["confidence"],
            "classificationConfidence": classification["confidence"],
        }

    @staticmethod
    def _excluded_item(source: dict[str, Any], relevance: dict[str, Any]) -> dict[str, Any]:
        return {
            "newsId": source["id"],
            "sourceId": source.get("sourceId", ""),
            "source": source.get("source") or source.get("sourceName") or source.get("sourceId") or "",
            "title": source.get("title", ""),
            "date": source.get("date") or source.get("publishedAt") or "",
            "url": source.get("url", ""),
            "reason": relevance["reason"],
            "scope": relevance["scope"],
            "confidence": relevance["confidence"],
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
