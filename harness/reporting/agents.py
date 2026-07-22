from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness.reporting.validators import (
    validate_analysis_items,
    validate_fact_items,
    validate_own_office_summary_items,
    validate_repair_items,
    validate_verification_items,
)
from harness.utils import chunks, read_json, render_prompt


HARNESS_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = HARNESS_ROOT / "contracts"


class ReportAgentError(RuntimeError):
    pass


class _BatchAgent:
    prompt_name = ""
    schema_name = ""
    label = ""

    def __init__(self, llm: Any, batch_size: int = 4, max_attempts: int = 2) -> None:
        self.llm = llm
        self.batch_size = max(1, batch_size)
        self.max_attempts = max(1, max_attempts)
        self.schema = read_json(CONTRACT_ROOT / self.schema_name)

    def validate(self, values: Any, expected_ids: set[str]) -> list[str]:
        raise NotImplementedError

    def run(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        output: list[dict[str, Any]] = []
        attempts = 0
        errors: list[dict[str, Any]] = []
        for batch in chunks(items, self.batch_size):
            expected_ids = {str(item["newsId"]) for item in batch}
            accepted: list[dict[str, Any]] | None = None
            last_errors: list[str] = []
            for _ in range(self.max_attempts):
                attempts += 1
                prompt = render_prompt(
                    self.prompt_name,
                    ITEMS_JSON=json.dumps(batch, ensure_ascii=False),
                )
                try:
                    raw = self.llm.generate_json(prompt, self.schema)
                    values = raw.get("items") if isinstance(raw, dict) else raw
                    validation_errors = self.validate(values, expected_ids)
                    if not validation_errors:
                        accepted = values
                        break
                    last_errors = validation_errors
                except Exception as error:
                    last_errors = [str(error)[:500]]
            if accepted is None:
                errors.append({"newsIds": sorted(expected_ids), "errors": last_errors})
            else:
                output.extend(accepted)
        return {"items": output, "attempts": attempts, "errors": errors}


class FactExtractionAgent(_BatchAgent):
    prompt_name = "report_facts.md"
    schema_name = "report_facts.schema.json"
    label = "extract_facts"

    def validate(self, values: Any, expected_ids: set[str]) -> list[str]:
        return validate_fact_items(values, expected_ids)


class OwnOfficeSummaryAgent(_BatchAgent):
    prompt_name = "report_own_office_summary.md"
    schema_name = "report_own_office_summary.schema.json"
    label = "summarize_own_office"

    def validate(self, values: Any, expected_ids: set[str]) -> list[str]:
        return validate_own_office_summary_items(values, expected_ids)


class TrendAnalysisAgent(_BatchAgent):
    prompt_name = "report_analysis.md"
    schema_name = "report_analysis.schema.json"
    label = "analyze_trends"

    def validate(self, values: Any, expected_ids: set[str]) -> list[str]:
        return validate_analysis_items(values, expected_ids)


class ReportRepairAgent(_BatchAgent):
    prompt_name = "report_repair.md"
    schema_name = "report_repair.schema.json"
    label = "repair_report"

    def validate(self, values: Any, expected_ids: set[str]) -> list[str]:
        return validate_repair_items(values, expected_ids)


class ReportVerificationAgent(_BatchAgent):
    prompt_name = "report_verification.md"
    schema_name = "report_verification.schema.json"
    label = "verify_report"

    def validate(self, values: Any, expected_ids: set[str]) -> list[str]:
        return validate_verification_items(values, expected_ids)