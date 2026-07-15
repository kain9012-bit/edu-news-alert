from __future__ import annotations

from collections import defaultdict
from typing import Any


def render_markdown(result: dict[str, Any]) -> str:
    metadata = result["metadata"]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in result.get("selectedItems", []):
        grouped[item.get("category", "기타")].append(item)

    def importance_stars(value: Any) -> str:
        score = value if isinstance(value, int) and not isinstance(value, bool) else 1
        score = max(1, min(5, score))
        return f"{'★' * score}{'☆' * (5 - score)} ({score}점)"

    lines = [
        "# 최근 24시간 교육동향 선별 결과",
        "",
        f"- 대상 기간: {metadata.get('windowStart')} ~ {metadata.get('windowEnd')}",
        f"- 수집 후보: {metadata.get('candidateCount', 0)}건",
        f"- 교육동향 채택: {metadata.get('relevantCount', 0)}건",
        f"- 제외: {metadata.get('filteredOutCount', 0)}건",
        f"- 사용 모델: {metadata.get('model')}",
        f"- 검증 상태: {metadata.get('validationStatus')}",
        "",
        "## 카테고리별 건수",
        "",
    ]
    if result.get("categorySummary"):
        lines.extend(
            f"- {item['category']}: {item['count']}건"
            for item in result["categorySummary"]
        )
    else:
        lines.append("- 채택된 교육동향이 없습니다.")

    for category, items in grouped.items():
        lines.extend(["", f"## {category}", ""])
        for item in items:
            title = item.get("title") or item["newsId"]
            url = item.get("url")
            label = f"[{title}]({url})" if url else title
            lines.extend(
                [
                    f"### {label}",
                    "",
                    f"- 기관: {item.get('source', '')}",
                    f"- 중요도: {importance_stars(item.get('importance'))}",
                    f"- 선정 이유: {item.get('selectionReason', '')}",
                    f"- 분류 요약: {item.get('summary', '')}",
                    "",
                ]
            )

    lines.extend(
        [
            "## 검증",
            "",
            f"- 최종 판정: {result.get('validation', {}).get('status', 'UNKNOWN')}",
            f"- 적합성 대체 처리: {metadata.get('relevanceFallbackCount', 0)}건",
            f"- 기관 활동 제외 규칙 적용: {metadata.get('institutionGuardCount', 0)}건",
            f"- 분류 대체 처리: {metadata.get('classificationFallbackCount', 0)}건",
            "",
            "이 결과는 공개 보도자료를 AI로 선별·분류한 것이며 각 항목은 원문 링크와 newsId를 유지합니다.",
            "",
        ]
    )
    return "\n".join(lines)
