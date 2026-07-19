from __future__ import annotations

from typing import Any


CHANGE_LEVEL_CAPS = {
    "routine_operation": 2,
    "project_change": 3,
    "policy_change": 4,
    "system_change": 5,
}

FACILITY_OPERATION_TERMS = (
    "시설개선",
    "환경개선",
    "시설 개선",
    "환경 개선",
    "개보수",
    "보수공사",
    "시설공사",
    "시설 공사",
)
STRUCTURAL_CHANGE_TERMS = (
    "법령",
    "조례",
    "의무화",
    "기준 도입",
    "기준 개편",
    "제도 도입",
    "제도 개편",
    "배분 방식",
)


def calibrate_importance(
    value: Any,
    change_level: str,
    assessment_text: str = "",
) -> tuple[int, str, bool]:
    """Normalize change level and apply its hard importance ceiling."""
    model_score = value if isinstance(value, int) and not isinstance(value, bool) else 1
    model_score = max(1, min(model_score, 5))
    model_level = change_level if change_level in CHANGE_LEVEL_CAPS else "routine_operation"

    text = assessment_text.replace(" ", "")
    facility_operation = any(term.replace(" ", "") in text for term in FACILITY_OPERATION_TERMS)
    structural_change = any(term.replace(" ", "") in text for term in STRUCTURAL_CHANGE_TERMS)
    calibrated_level = (
        "routine_operation"
        if facility_operation and not structural_change
        else model_level
    )

    calibrated_score = min(model_score, CHANGE_LEVEL_CAPS[calibrated_level])
    adjusted = calibrated_score != model_score or calibrated_level != model_level
    return calibrated_score, calibrated_level, adjusted