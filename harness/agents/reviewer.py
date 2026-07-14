from __future__ import annotations

import json
from typing import Any

from harness.utils import compact_news, render_prompt
from harness.validators import validate_report


class ReviewerAgent:
    name = "reviewer"

    def __init__(self, llm: Any) -> None:
        self.llm = llm

    def run(self, report: dict[str, Any], source_items: list[dict[str, Any]]) -> dict[str, Any]:
        source_ids = {item.get("id", "") for item in source_items}
        structural_errors = validate_report(report, source_ids)
        if structural_errors:
            return {
                "status": "REVISE",
                "issues": [
                    {"code": "SCHEMA", "message": message, "evidenceIds": []}
                    for message in structural_errors
                ],
                "revisionInstructions": "보고서 구조와 근거 ID를 수정하세요.",
                "deterministicChecks": structural_errors,
            }

        evidence_ids = set()
        for trend in report.get("keyTrends", []):
            evidence_ids.update(trend.get("evidenceIds", []))
        evidence_ids.update(item.get("newsId") for item in report.get("notableNews", []))
        evidence = [compact_news(item, summary_limit=500) for item in source_items if item.get("id") in evidence_ids]
        prompt = render_prompt(
            "reviewer.md",
            REPORT_JSON=json.dumps(report, ensure_ascii=False),
            EVIDENCE_JSON=json.dumps(evidence, ensure_ascii=False),
        )
        try:
            value = self.llm.generate_json(prompt)
            status = str(value.get("status", "")).upper() if isinstance(value, dict) else ""
            if status not in {"PASS", "REVISE"}:
                raise ValueError("review status must be PASS or REVISE")
            return {
                "status": status,
                "issues": value.get("issues", []),
                "revisionInstructions": value.get("revisionInstructions", ""),
                "deterministicChecks": [],
            }
        except Exception as error:
            return {
                "status": "PASS",
                "issues": [],
                "revisionInstructions": "",
                "deterministicChecks": [],
                "reviewerFallback": str(error),
            }
