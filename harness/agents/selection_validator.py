from __future__ import annotations

import re
from typing import Any

from harness.importance import CHANGE_LEVEL_CAPS


SUPPORT_OFFICE_PATTERN = re.compile(r"([가-힣]{1,20})교육지원청")


class SelectionValidatorAgent:
    name = "selection_validator"

    def __init__(self, categories: list[str]) -> None:
        self.categories = set(categories)

    def run(
        self,
        candidate_items: list[dict[str, Any]],
        relevance: list[dict[str, Any]],
        classifications: list[dict[str, Any]],
    ) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        candidate_ids = [str(item.get("id", "")) for item in candidate_items]
        candidate_map = {str(item.get("id", "")): item for item in candidate_items}
        relevance_ids = [str(item.get("newsId", "")) for item in relevance]
        keep_ids = {
            str(item.get("newsId", ""))
            for item in relevance
            if item.get("decision") == "KEEP"
        }
        classified_ids = [str(item.get("newsId", "")) for item in classifications]
        candidate_coverage = (
            set(candidate_ids) == set(relevance_ids)
            and len(candidate_ids) == len(set(candidate_ids))
            and len(relevance_ids) == len(set(relevance_ids))
        )
        classification_coverage = (
            keep_ids == set(classified_ids)
            and len(classified_ids) == len(set(classified_ids))
        )

        self._check_same_ids(
            candidate_ids,
            relevance_ids,
            "RELEVANCE_COVERAGE",
            "후보 자료와 적합성 판별 결과의 ID 구성이 다릅니다.",
            issues,
        )
        self._check_same_ids(
            sorted(keep_ids),
            classified_ids,
            "CLASSIFICATION_COVERAGE",
            "KEEP 자료와 분류 결과의 ID 구성이 다릅니다.",
            issues,
        )

        for item in relevance:
            news_id = str(item.get("newsId", ""))
            if item.get("evidenceIds") != [news_id]:
                issues.append(self._issue("RELEVANCE_EVIDENCE", f"{news_id}: 적합성 근거 ID가 원문과 다릅니다.", news_id))
            source = candidate_map.get(news_id, {})
            if item.get("decision") == "KEEP" and SUPPORT_OFFICE_PATTERN.search(str(source.get("title", ""))):
                issues.append(
                    self._issue(
                        "EDUCATION_SUPPORT_OFFICE_SCOPE",
                        f"{news_id}: 교육지원청 단위 자료가 KEEP으로 남아 있습니다.",
                        news_id,
                    )
                )

        for item in classifications:
            news_id = str(item.get("newsId", ""))
            if item.get("evidenceIds") != [news_id]:
                issues.append(self._issue("CLASSIFICATION_EVIDENCE", f"{news_id}: 분류 근거 ID가 원문과 다릅니다.", news_id))
            if item.get("category") not in self.categories:
                issues.append(self._issue("CATEGORY", f"{news_id}: 허용되지 않은 분류입니다.", news_id))
            importance = item.get("importance")
            if not isinstance(importance, int) or isinstance(importance, bool) or not 1 <= importance <= 5:
                issues.append(self._issue("IMPORTANCE", f"{news_id}: 중요도는 1~5 사이 정수여야 합니다.", news_id))
            change_level = item.get("changeLevel")
            if change_level not in CHANGE_LEVEL_CAPS:
                issues.append(self._issue("IMPORTANCE_CHANGE_LEVEL", f"{news_id}: 변화 수준이 올바르지 않습니다.", news_id))
            elif isinstance(importance, int) and not isinstance(importance, bool):
                if importance > CHANGE_LEVEL_CAPS[change_level]:
                    issues.append(self._issue("IMPORTANCE_POLICY", f"{news_id}: 변화 수준별 중요도 상한을 넘었습니다.", news_id))
            if not str(item.get("importanceReason", "")).strip():
                issues.append(self._issue("IMPORTANCE_REASON", f"{news_id}: 중요도 근거가 없습니다.", news_id))

        return {
            "status": "PASS" if not issues else "REVISE",
            "issues": issues,
            "checks": {
                "candidateCoverage": candidate_coverage,
                "classificationCoverage": classification_coverage,
                "evidenceIntegrity": not any("EVIDENCE" in item["code"] for item in issues),
                "importanceIntegrity": not any(item["code"].startswith("IMPORTANCE") for item in issues),
                "supportOfficeExclusion": not any(
                    item["code"] == "EDUCATION_SUPPORT_OFFICE_SCOPE" for item in issues
                ),
            },
        }

    @staticmethod
    def _check_same_ids(
        expected: list[str],
        actual: list[str],
        code: str,
        message: str,
        issues: list[dict[str, Any]],
    ) -> None:
        if set(expected) != set(actual) or len(actual) != len(set(actual)):
            issues.append({"code": code, "message": message, "evidenceIds": []})

    @staticmethod
    def _issue(code: str, message: str, news_id: str) -> dict[str, Any]:
        return {"code": code, "message": message, "evidenceIds": [news_id] if news_id else []}
