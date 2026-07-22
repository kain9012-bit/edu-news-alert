from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any


NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)*")
DEPARTMENT_ASSIGNMENT_PATTERN = re.compile(
    r"(관련|담당|주관)\s*부서|[가-힣]{2,15}(과|담당관|팀)\s*(에서|이|가|은|는)?\s*(담당|추진|검토)"
)
OVERSTATEMENT_PATTERN = re.compile(r"반드시|즉시\s*도입|전면\s*도입해야|확정해야|의무화해야")
BOILERPLATE_PATTERNS = (
    "본문 바로가기",
    "전체메뉴",
    "첨부파일 다운로드 횟수",
    "요청하신 페이지를 찾을 수 없습니다",
    "QUICK MENU",
)


def _validate_id_coverage(values: Any, expected_ids: set[str], label: str) -> list[str]:
    if not isinstance(values, list):
        return [f"{label} 결과가 배열이 아닙니다."]
    ids = [str(item.get("newsId", "")) for item in values if isinstance(item, dict)]
    if len(ids) != len(values):
        return [f"{label} 결과에 객체가 아닌 항목이 있습니다."]
    errors: list[str] = []
    unknown = set(ids) - expected_ids
    if unknown:
        errors.append(f"{label} 결과에 알 수 없는 newsId가 있습니다: {sorted(unknown)}")
    if set(ids) != expected_ids or len(ids) != len(expected_ids):
        errors.append(f"{label} 결과의 newsId 구성이 입력과 다릅니다.")
    return errors


def _validate_points(value: Any, minimum: int, maximum: int, label: str) -> list[str]:
    if not isinstance(value, list):
        return [f"{label}이 배열이 아닙니다."]
    errors: list[str] = []
    if not minimum <= len(value) <= maximum:
        errors.append(f"{label} 개수는 {minimum}~{maximum}개여야 합니다.")
    for index, point in enumerate(value):
        if not isinstance(point, str) or not point.strip():
            errors.append(f"{label}[{index}]가 비어 있습니다.")
        elif len(point.strip()) > 320:
            errors.append(f"{label}[{index}]가 지나치게 깁니다.")
    return errors


def validate_fact_items(values: Any, expected_ids: set[str]) -> list[str]:
    errors = _validate_id_coverage(values, expected_ids, "사실정리")
    if not isinstance(values, list):
        return errors
    for item in values:
        if not isinstance(item, dict):
            continue
        news_id = str(item.get("newsId", ""))
        errors.extend(f"{news_id}: {error}" for error in _validate_points(item.get("summaryPoints"), 1, 5, "내용 요약"))
        errors.extend(f"{news_id}: {error}" for error in _validate_points(item.get("sourceFacts"), 1, 8, "근거 사실"))
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            errors.append(f"{news_id}: confidence 범위가 잘못됐습니다.")
    return errors


def validate_analysis_items(values: Any, expected_ids: set[str]) -> list[str]:
    errors = _validate_id_coverage(values, expected_ids, "동향분석")
    if not isinstance(values, list):
        return errors
    for item in values:
        if not isinstance(item, dict):
            continue
        news_id = str(item.get("newsId", ""))
        errors.extend(f"{news_id}: {error}" for error in _validate_points(item.get("analysisPoints"), 1, 5, "교육동향 분석"))
        errors.extend(f"{news_id}: {error}" for error in _validate_points(item.get("applicationReviewPoints"), 0, 5, "전북교육 적용 검토"))
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            errors.append(f"{news_id}: confidence 범위가 잘못됐습니다.")
    return errors


def validate_verification_items(values: Any, expected_ids: set[str]) -> list[str]:
    errors = _validate_id_coverage(values, expected_ids, "검증")
    if not isinstance(values, list):
        return errors
    for item in values:
        if not isinstance(item, dict):
            continue
        news_id = str(item.get("newsId", ""))
        if item.get("status") not in {"PASS", "REVISE"}:
            errors.append(f"{news_id}: 검증 status가 잘못됐습니다.")
        if not isinstance(item.get("issues"), list):
            errors.append(f"{news_id}: issues가 배열이 아닙니다.")
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            errors.append(f"{news_id}: confidence 범위가 잘못됐습니다.")
    return errors


def body_quality_issues(body: str, minimum_chars: int) -> list[str]:
    normalized = " ".join((body or "").split())
    issues: list[str] = []
    if len(normalized) < minimum_chars:
        issues.append(f"본문이 {minimum_chars}자보다 짧습니다.")
    boilerplate_hits = sum(pattern.lower() in normalized.lower() for pattern in BOILERPLATE_PATTERNS)
    if boilerplate_hits >= 2:
        issues.append("게시판 메뉴 문구가 본문보다 많이 포함된 것으로 보입니다.")
    return issues


def validate_report_item(item: dict[str, Any], source_body: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    sections = (
        ("summaryPoints", item.get("summaryPoints", []), 1, 5),
        ("analysisPoints", item.get("analysisPoints", []), 1, 5),
        ("applicationReviewPoints", item.get("applicationReviewPoints", []), 0, 5),
    )
    for field, points, minimum, maximum in sections:
        for error in _validate_points(points, minimum, maximum, field):
            issues.append({"code": "FORMAT", "field": field, "message": error})
        if not isinstance(points, list):
            continue
        normalized_points = [" ".join(point.split()) for point in points if isinstance(point, str)]
        for left in range(len(normalized_points)):
            for right in range(left + 1, len(normalized_points)):
                if SequenceMatcher(None, normalized_points[left], normalized_points[right]).ratio() >= 0.82:
                    issues.append({
                        "code": "DUPLICATE",
                        "field": field,
                        "pointIndex": right,
                        "message": "같은 영역에 의미가 거의 같은 항목이 반복됩니다.",
                    })
        for index, point in enumerate(normalized_points):
            if len(point) >= 80 and point in source_body:
                issues.append({
                    "code": "LONG_COPY",
                    "field": field,
                    "pointIndex": index,
                    "message": "원문을 길게 그대로 옮긴 문장이 있습니다.",
                })
            if DEPARTMENT_ASSIGNMENT_PATTERN.search(point):
                issues.append({
                    "code": "DEPARTMENT_ASSIGNMENT",
                    "field": field,
                    "pointIndex": index,
                    "message": "관련 부서 또는 담당 업무를 임의로 지정한 표현이 있습니다.",
                })
            if field == "applicationReviewPoints" and OVERSTATEMENT_PATTERN.search(point):
                issues.append({
                    "code": "OVERSTATEMENT",
                    "field": field,
                    "pointIndex": index,
                    "message": "적용 검토안이 확정적 지시처럼 표현됐습니다.",
                })
            if field != "applicationReviewPoints":
                source_numbers = set(NUMBER_PATTERN.findall(source_body))
                invented_numbers = set(NUMBER_PATTERN.findall(point)) - source_numbers
                if invented_numbers:
                    issues.append({
                        "code": "UNSUPPORTED_NUMBER",
                        "field": field,
                        "pointIndex": index,
                        "message": f"원문에서 확인되지 않는 수치가 있습니다: {sorted(invented_numbers)}",
                    })
    return issues


def validate_summary_item(item: dict[str, Any], source_body: str) -> list[dict[str, Any]]:
    """Validate a summary-only item without requiring analysis sections."""
    summary_only = {
        **item,
        "analysisPoints": ["요약 전용 검증 자리표시자"],
        "applicationReviewPoints": [],
    }
    return [
        issue
        for issue in validate_report_item(summary_only, source_body)
        if issue.get("field") == "summaryPoints"
    ]
