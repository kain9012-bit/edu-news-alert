from __future__ import annotations

from typing import Any


RELEVANCE_DECISIONS = {"KEEP", "DROP"}
SCOPES = {"national", "provincial", "local", "institution"}


def validate_input(payload: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["입력은 JSON 객체여야 합니다."]
    if not isinstance(payload.get("items"), list):
        errors.append("items 배열이 없습니다.")
        return errors
    seen: set[str] = set()
    for index, item in enumerate(payload["items"]):
        news_id = item.get("id") if isinstance(item, dict) else None
        if not news_id:
            errors.append(f"items[{index}]에 id가 없습니다.")
        elif news_id in seen:
            errors.append(f"중복 newsId: {news_id}")
        else:
            seen.add(news_id)
        if isinstance(item, dict) and not item.get("title"):
            errors.append(f"items[{index}]에 title이 없습니다.")
    return errors

def validate_classifications(
    values: Any,
    expected_ids: set[str],
    categories: set[str],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(values, list):
        return ["분류 결과가 배열이 아닙니다."]
    returned_ids: list[str] = []
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            errors.append(f"분류[{index}]가 객체가 아닙니다.")
            continue
        news_id = str(item.get("newsId", ""))
        returned_ids.append(news_id)
        if news_id not in expected_ids:
            errors.append(f"알 수 없는 newsId: {news_id}")
        if item.get("category") not in categories:
            errors.append(f"허용되지 않은 category: {item.get('category')}")
        importance = item.get("importance")
        if not isinstance(importance, int) or isinstance(importance, bool) or not 1 <= importance <= 5:
            errors.append(f"잘못된 importance: {item.get('importance')}")
        if not isinstance(item.get("keywords"), list):
            errors.append(f"{news_id}: keywords가 배열이 아닙니다.")
        if not str(item.get("summary", "")).strip():
            errors.append(f"{news_id}: summary가 없습니다.")
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            errors.append(f"{news_id}: confidence 범위가 잘못됐습니다.")
        if item.get("evidenceIds") != [news_id]:
            errors.append(f"{news_id}: evidenceIds가 원문 ID와 다릅니다.")
    if set(returned_ids) != expected_ids or len(returned_ids) != len(expected_ids):
        errors.append("입력과 분류 결과의 newsId 구성이 다릅니다.")
    return errors


def validate_relevance(values: Any, expected_ids: set[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(values, list):
        return ["적합성 판별 결과가 배열이 아닙니다."]
    returned_ids: list[str] = []
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            errors.append(f"적합성[{index}]가 객체가 아닙니다.")
            continue
        news_id = str(item.get("newsId", ""))
        returned_ids.append(news_id)
        if news_id not in expected_ids:
            errors.append(f"알 수 없는 newsId: {news_id}")
        if item.get("decision") not in RELEVANCE_DECISIONS:
            errors.append(f"{news_id}: decision이 잘못됐습니다.")
        if item.get("scope") not in SCOPES:
            errors.append(f"{news_id}: scope가 잘못됐습니다.")
        if not str(item.get("reason", "")).strip():
            errors.append(f"{news_id}: reason이 없습니다.")
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            errors.append(f"{news_id}: confidence 범위가 잘못됐습니다.")
        if item.get("evidenceIds") != [news_id]:
            errors.append(f"{news_id}: evidenceIds가 원문 ID와 다릅니다.")
    if set(returned_ids) != expected_ids or len(returned_ids) != len(expected_ids):
        errors.append("입력과 적합성 판별 결과의 newsId 구성이 다릅니다.")
    return errors
