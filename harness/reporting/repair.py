from __future__ import annotations

import re
from typing import Any, Callable

from harness.reporting.validators import validate_report_item
from harness.utils import normalize_space


def verification_input(
    items: list[dict[str, Any]],
    candidate_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "newsId": item["newsId"],
            "sourceBody": candidate_map[item["newsId"]]["body"],
            "report": {
                "summaryPoints": item.get("summaryPoints", []),
                "analysisPoints": item.get("analysisPoints", []),
                "applicationReviewPoints": item.get("applicationReviewPoints", []),
            },
        }
        for item in items
    ]


def source_summary(source: dict[str, Any]) -> list[str]:
    body = normalize_space(str(source.get("body") or ""))
    title = normalize_space(str(source.get("title") or "보도자료"))
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", body)
        if sentence.strip()
    ]
    points: list[str] = []
    for sentence in sentences:
        if sentence == title or len(sentence) < 10:
            continue
        point = sentence if len(sentence) <= 140 else sentence[:137].rstrip() + "..."
        points.append(point)
        if len(points) == 2:
            break
    if not points:
        fallback = body or title
        points.append(fallback if len(fallback) <= 140 else fallback[:137].rstrip() + "...")
    return points


def validation_issues(
    item: dict[str, Any],
    source_body: str,
    verification: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    issues = list(validate_report_item(item, source_body))
    if verification is None:
        issues.append({
            "field": "item",
            "pointIndex": -1,
            "code": "OTHER",
            "message": "근거 검증 결과가 없어 전체 항목을 다시 작성해야 합니다.",
        })
        return issues
    for issue in verification.get("issues", []):
        if not isinstance(issue, dict):
            continue
        issues.append({
            "field": issue.get("field", "item"),
            "pointIndex": issue.get("pointIndex", -1),
            "code": issue.get("code", "OTHER"),
            "message": issue.get("message", "근거에 맞게 수정해야 합니다."),
        })
    if verification.get("status") != "PASS" and not verification.get("issues"):
        issues.append({
            "field": "item",
            "pointIndex": -1,
            "code": "OTHER",
            "message": "근거 검증을 통과하지 못해 전체 항목을 다시 작성해야 합니다.",
        })
    return issues


class ReportRepairCoordinator:
    def __init__(
        self,
        repair_agent: Any,
        verification_agent: Any,
        step: Callable[[str, Callable[[], dict[str, Any]]], dict[str, Any]],
        rounds: int = 2,
    ) -> None:
        self.repair_agent = repair_agent
        self.verification_agent = verification_agent
        self.step = step
        self.rounds = max(1, rounds)

    def run(
        self,
        drafts: list[dict[str, Any]],
        candidate_map: dict[str, dict[str, Any]],
        verification_map: dict[str, dict[str, Any]],
        generation_issues: dict[str, list[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        generation_issues = generation_issues or {}
        current_issues = {
            item["newsId"]: [
                *generation_issues.get(item["newsId"], []),
                *validation_issues(
                    item,
                    candidate_map[item["newsId"]]["body"],
                    verification_map.get(item["newsId"]),
                ),
            ]
            for item in drafts
        }
        repair_errors: list[dict[str, Any]] = []
        verification_errors: list[dict[str, Any]] = []

        for round_number in range(1, self.rounds + 1):
            needs_repair = [item for item in drafts if current_issues[item["newsId"]]]
            if not needs_repair:
                break
            repair_payload = [
                {
                    "newsId": item["newsId"],
                    "source": item.get("source", ""),
                    "title": item.get("title", ""),
                    "sourceBody": candidate_map[item["newsId"]]["body"],
                    "currentReport": {
                        "summaryPoints": item.get("summaryPoints", []),
                        "analysisPoints": item.get("analysisPoints", []),
                        "applicationReviewPoints": item.get("applicationReviewPoints", []),
                    },
                    "validationIssues": current_issues[item["newsId"]],
                }
                for item in needs_repair
            ]
            repair_result = self.step(
                f"repair_report_{round_number}",
                lambda payload=repair_payload: self.repair_agent.run(payload),
            )
            repair_errors.extend(repair_result.get("errors", []))
            repaired_map = {item["newsId"]: item for item in repair_result.get("items", [])}
            repaired_items: list[dict[str, Any]] = []
            for item in needs_repair:
                repaired = repaired_map.get(item["newsId"])
                if repaired is None:
                    continue
                item["summaryPoints"] = repaired["summaryPoints"]
                item["analysisPoints"] = repaired["analysisPoints"]
                item["applicationReviewPoints"] = repaired["applicationReviewPoints"]
                item.setdefault("confidence", {})["repair"] = repaired.get("confidence", 0)
                repaired_items.append(item)
            if not repaired_items:
                continue
            verification_result = self.step(
                f"verify_repair_{round_number}",
                lambda items=repaired_items: self.verification_agent.run(
                    verification_input(items, candidate_map)
                ),
            )
            verification_errors.extend(verification_result.get("errors", []))
            repaired_verification_map = {
                item["newsId"]: item for item in verification_result.get("items", [])
            }
            verification_map.update(repaired_verification_map)
            for item in repaired_items:
                current_issues[item["newsId"]] = validation_issues(
                    item,
                    candidate_map[item["newsId"]]["body"],
                    repaired_verification_map.get(item["newsId"]),
                )

        published: list[dict[str, Any]] = []
        summary_only_count = 0
        for item in drafts:
            news_id = item["newsId"]
            issues = current_issues[news_id]
            if issues:
                item["summaryPoints"] = source_summary(candidate_map[news_id])
                item["analysisPoints"] = []
                item["applicationReviewPoints"] = []
                item["summaryOnly"] = True
                item["validation"] = {
                    "status": "SUMMARY_ONLY",
                    "issues": issues,
                    "confidence": 0,
                }
                summary_only_count += 1
            else:
                verification = verification_map.get(news_id, {})
                item["validation"] = {
                    "status": "PASS",
                    "issues": [],
                    "confidence": verification.get("confidence", 0),
                }
            published.append(item)
        return {
            "items": published,
            "summaryOnlyCount": summary_only_count,
            "repairErrors": repair_errors,
            "verificationErrors": verification_errors,
        }
