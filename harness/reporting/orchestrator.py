from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from harness.reporting.agents import (
    FactExtractionAgent,
    ReportVerificationAgent,
    TrendAnalysisAgent,
)
from harness.reporting.validators import body_quality_issues, validate_report_item
from harness.utils import normalize_space


class ReportInputError(ValueError):
    pass


class DailyReportHarness:
    def __init__(
        self,
        fact_llm: Any,
        analysis_llm: Any,
        verifier_llm: Any,
        config: dict[str, Any],
    ) -> None:
        self.fact_llm = fact_llm
        self.analysis_llm = analysis_llm
        self.verifier_llm = verifier_llm
        self.config = config
        self.trace: list[dict[str, Any]] = []
        batch_size = int(config.get("batchSize", 4))
        self.fact_agent = FactExtractionAgent(fact_llm, batch_size=batch_size)
        self.analysis_agent = TrendAnalysisAgent(analysis_llm, batch_size=batch_size)
        self.verification_agent = ReportVerificationAgent(verifier_llm, batch_size=batch_size)

    def run(self, selection: dict[str, Any], source_payload: dict[str, Any]) -> dict[str, Any]:
        self.trace = []
        self._validate_inputs(selection, source_payload)
        selected = sorted(
            selection.get("selectedItems", []),
            key=lambda item: (-int(item.get("importance", 1)), str(item.get("title", ""))),
        )
        source_map = {
            str(item.get("id", "")): item
            for item in source_payload.get("items", [])
            if isinstance(item, dict) and item.get("id")
        }
        candidates: list[dict[str, Any]] = []
        omitted: list[dict[str, Any]] = []
        own_office_count = 0
        quality_excluded_count = 0
        max_body_chars = int(self.config.get("maxBodyChars", 6000))
        minimum_chars = int(self.config.get("minBodyChars", 200))

        for item in selected:
            news_id = str(item.get("newsId", ""))
            if self._is_own_office(item):
                own_office_count += 1
                omitted.append(self._omitted(item, "OWN_OFFICE", "전북특별자치도교육청 보도자료는 내부 동향 보고서에서 제외합니다."))
                continue
            if "교육지원청" in str(item.get("title", "")):
                omitted.append(self._omitted(item, "SUPPORT_OFFICE", "교육지원청 단위 보도자료는 내부 동향 보고서에서 제외합니다."))
                continue
            source = source_map.get(news_id)
            if source is None:
                quality_excluded_count += 1
                omitted.append(self._omitted(item, "SOURCE_MISSING", "수집 원문을 찾을 수 없습니다."))
                continue
            body = normalize_space(source.get("summary") or source.get("contentPreview") or "")
            issues = body_quality_issues(body, minimum_chars)
            if issues:
                quality_excluded_count += 1
                omitted.append(self._omitted(item, "BODY_QUALITY", " ".join(issues)))
                continue
            candidates.append(
                {
                    "newsId": news_id,
                    "sourceId": item.get("sourceId") or source.get("sourceId", ""),
                    "source": item.get("source") or source.get("source") or source.get("sourceName", ""),
                    "title": item.get("title") or source.get("title", ""),
                    "date": item.get("date") or source.get("date") or source.get("publishedAt", ""),
                    "url": item.get("url") or source.get("url", ""),
                    "category": item.get("category", "기타"),
                    "importance": item.get("importance", 1),
                    "selectionReason": item.get("selectionReason", ""),
                    "body": body[:max_body_chars],
                }
            )

        if not candidates:
            return self._empty_result(selection, selected, omitted, own_office_count, quality_excluded_count)

        fact_input = [
            {
                "newsId": item["newsId"],
                "source": item["source"],
                "title": item["title"],
                "date": item["date"],
                "sourceBody": item["body"],
            }
            for item in candidates
        ]
        fact_result = self._step("extract_facts", lambda: self.fact_agent.run(fact_input))
        fact_map = {item["newsId"]: item for item in fact_result["items"]}
        for item in candidates:
            if item["newsId"] not in fact_map:
                omitted.append(self._omitted(item, "FACT_EXTRACTION_FAILED", "사실정리 결과가 JSON 계약을 통과하지 못했습니다."))

        analysis_input = [
            {
                "newsId": item["newsId"],
                "source": item["source"],
                "title": item["title"],
                "category": item["category"],
                "importance": item["importance"],
                "summaryPoints": fact_map[item["newsId"]]["summaryPoints"],
                "sourceFacts": fact_map[item["newsId"]]["sourceFacts"],
            }
            for item in candidates
            if item["newsId"] in fact_map
        ]
        analysis_result = self._step("analyze_trends", lambda: self.analysis_agent.run(analysis_input))
        analysis_map = {item["newsId"]: item for item in analysis_result["items"]}
        for item in candidates:
            if item["newsId"] in fact_map and item["newsId"] not in analysis_map:
                omitted.append(self._omitted(item, "ANALYSIS_FAILED", "교육동향 분석 결과가 JSON 계약을 통과하지 못했습니다."))

        draft_items = [
            self._draft_item(item, fact_map[item["newsId"]], analysis_map[item["newsId"]])
            for item in candidates
            if item["newsId"] in fact_map and item["newsId"] in analysis_map
        ]
        candidate_map = {item["newsId"]: item for item in candidates}
        verification_input = [
            {
                "newsId": item["newsId"],
                "sourceBody": candidate_map[item["newsId"]]["body"],
                "report": {
                    "summaryPoints": item["summaryPoints"],
                    "analysisPoints": item["analysisPoints"],
                    "applicationReviewPoints": item["applicationReviewPoints"],
                },
            }
            for item in draft_items
        ]
        verification_result = self._step(
            "verify_report",
            lambda: self.verification_agent.run(verification_input),
        )
        verification_map = {item["newsId"]: item for item in verification_result["items"]}

        published: list[dict[str, Any]] = []
        for item in draft_items:
            news_id = item["newsId"]
            verification = verification_map.get(news_id)
            local_issues = validate_report_item(item, candidate_map[news_id]["body"])
            if verification is None:
                omitted.append(self._omitted(item, "VERIFICATION_FAILED", "검증 결과가 JSON 계약을 통과하지 못했습니다."))
                continue
            combined_issues = [*local_issues, *verification.get("issues", [])]
            if verification.get("status") != "PASS" or combined_issues:
                message = "; ".join(str(issue.get("message", "검증 필요")) for issue in combined_issues[:5])
                omitted.append(self._omitted(item, "REPORT_REVISE", message or "AI 근거 검증에서 수정을 요구했습니다."))
                continue
            item["validation"] = {
                "status": "PASS",
                "issues": [],
                "confidence": verification.get("confidence", 0),
            }
            published.append(item)

        metadata = self._metadata(
            selection=selection,
            source_count=len(selected),
            eligible_count=len(candidates),
            published_count=len(published),
            omitted_count=len(omitted),
            own_office_count=own_office_count,
            quality_excluded_count=quality_excluded_count,
        )
        metadata["status"] = "completed" if not omitted else "completed_with_omissions"
        metadata["usage"] = self._usage_summary()
        metadata["estimatedCostUsd"] = self._estimated_cost(metadata["usage"])
        return {
            "metadata": metadata,
            "items": published,
            "omittedItems": omitted,
            "validation": {
                "status": "PASS",
                "issues": [],
                "checks": {
                    "ownOfficeExcludedBeforeAi": True,
                    "publishedItemsVerified": all(item["validation"]["status"] == "PASS" for item in published),
                    "sourceWindowMatches": True,
                },
            },
            "providerErrors": {
                "facts": fact_result.get("errors", []),
                "analysis": analysis_result.get("errors", []),
                "verification": verification_result.get("errors", []),
            },
            "trace": self.trace,
        }

    def _validate_inputs(self, selection: dict[str, Any], source_payload: dict[str, Any]) -> None:
        if not isinstance(selection, dict) or not isinstance(selection.get("selectedItems"), list):
            raise ReportInputError("교육동향 선별 결과에 selectedItems 배열이 없습니다.")
        if not isinstance(source_payload, dict) or not isinstance(source_payload.get("items"), list):
            raise ReportInputError("수집 원문에 items 배열이 없습니다.")
        metadata = selection.get("metadata", {})
        if metadata.get("validationStatus") != "PASS":
            raise ReportInputError("검증을 통과하지 않은 교육동향 선별 결과입니다.")
        for key in ("windowStart", "windowEnd"):
            if metadata.get(key) != source_payload.get(key):
                raise ReportInputError(f"선별 결과와 수집 원문의 {key}가 다릅니다.")

    def _is_own_office(self, item: dict[str, Any]) -> bool:
        source_id = str(item.get("sourceId", ""))
        source_name = str(item.get("source", ""))
        return (
            source_id in set(self.config.get("ownOfficeSourceIds", ["jeonbuk"]))
            or source_name in set(self.config.get("ownOfficeNames", ["전북특별자치도교육청"]))
        )

    @staticmethod
    def _draft_item(source: dict[str, Any], facts: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
        return {
            "newsId": source["newsId"],
            "sourceId": source["sourceId"],
            "source": source["source"],
            "title": source["title"],
            "date": source["date"],
            "url": source["url"],
            "category": source["category"],
            "importance": source["importance"],
            "selectionReason": source["selectionReason"],
            "summaryPoints": facts["summaryPoints"],
            "analysisPoints": analysis["analysisPoints"],
            "applicationReviewPoints": analysis["applicationReviewPoints"],
            "sourceFacts": facts["sourceFacts"],
            "confidence": {
                "facts": facts.get("confidence", 0),
                "analysis": analysis.get("confidence", 0),
            },
        }

    @staticmethod
    def _omitted(item: dict[str, Any], code: str, reason: str) -> dict[str, Any]:
        return {
            "newsId": item.get("newsId", ""),
            "sourceId": item.get("sourceId", ""),
            "source": item.get("source", ""),
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "code": code,
            "reason": reason,
        }

    def _metadata(
        self,
        selection: dict[str, Any],
        source_count: int,
        eligible_count: int,
        published_count: int,
        omitted_count: int,
        own_office_count: int,
        quality_excluded_count: int,
    ) -> dict[str, Any]:
        source_metadata = selection.get("metadata", {})
        return {
            "reportId": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8],
            "title": "오늘의 교육동향",
            "status": "completed",
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "windowStart": source_metadata.get("windowStart"),
            "windowEnd": source_metadata.get("windowEnd"),
            "windowHours": source_metadata.get("windowHours"),
            "selectionRunId": source_metadata.get("runId"),
            "sourceCount": source_count,
            "eligibleCount": eligible_count,
            "publishedCount": published_count,
            "omittedCount": omitted_count,
            "ownOfficeExcludedCount": own_office_count,
            "qualityExcludedCount": quality_excluded_count,
            "factModel": getattr(self.fact_llm, "model", "unknown"),
            "analysisModel": getattr(self.analysis_llm, "model", "unknown"),
            "verifierModel": getattr(self.verifier_llm, "model", "unknown"),
        }

    def _empty_result(
        self,
        selection: dict[str, Any],
        selected: list[dict[str, Any]],
        omitted: list[dict[str, Any]],
        own_office_count: int,
        quality_excluded_count: int,
    ) -> dict[str, Any]:
        metadata = self._metadata(
            selection,
            len(selected),
            0,
            0,
            len(omitted),
            own_office_count,
            quality_excluded_count,
        )
        metadata["status"] = "completed_empty"
        metadata["usage"] = self._usage_summary()
        metadata["estimatedCostUsd"] = 0.0
        return {
            "metadata": metadata,
            "items": [],
            "omittedItems": omitted,
            "validation": {
                "status": "PASS",
                "issues": [],
                "checks": {
                    "ownOfficeExcludedBeforeAi": True,
                    "publishedItemsVerified": True,
                    "sourceWindowMatches": True,
                },
            },
            "providerErrors": {"facts": [], "analysis": [], "verification": []},
            "trace": self.trace,
        }

    def _usage_summary(self) -> dict[str, Any]:
        stages = {
            "facts": self._usage(self.fact_llm),
            "analysis": self._usage(self.analysis_llm),
            "verification": self._usage(self.verifier_llm),
        }
        total = {
            key: sum(int(stage.get(key, 0)) for stage in stages.values())
            for key in ("requests", "promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount", "totalTokenCount")
        }
        return {"stages": stages, "total": total}

    @staticmethod
    def _usage(llm: Any) -> dict[str, int]:
        raw = getattr(llm, "usage", {}) or {}
        return {
            "model": getattr(llm, "model", "unknown"),
            "requests": int(raw.get("requests", 0) or 0),
            "promptTokenCount": int(raw.get("promptTokenCount", 0) or 0),
            "candidatesTokenCount": int(raw.get("candidatesTokenCount", 0) or 0),
            "thoughtsTokenCount": int(raw.get("thoughtsTokenCount", 0) or 0),
            "totalTokenCount": int(raw.get("totalTokenCount", 0) or 0),
        }

    def _estimated_cost(self, usage: dict[str, Any]) -> float:
        prices = self.config.get("pricingPerMillionTokensUsd", {})
        total = 0.0
        for stage in usage.get("stages", {}).values():
            price = prices.get(stage.get("model"), {})
            prompt = int(stage.get("promptTokenCount", 0))
            output = int(stage.get("candidatesTokenCount", 0)) + int(stage.get("thoughtsTokenCount", 0))
            total += prompt * float(price.get("input", 0)) / 1_000_000
            total += output * float(price.get("output", 0)) / 1_000_000
        return round(total, 6)

    def _step(self, name: str, function: Callable[[], Any]) -> Any:
        started = time.perf_counter()
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            value = function()
            self.trace.append({
                "step": name,
                "status": "success",
                "startedAt": timestamp,
                "durationMs": round((time.perf_counter() - started) * 1000),
            })
            return value
        except Exception as error:
            self.trace.append({
                "step": name,
                "status": "failed",
                "startedAt": timestamp,
                "durationMs": round((time.perf_counter() - started) * 1000),
                "error": str(error)[:500],
            })
            raise