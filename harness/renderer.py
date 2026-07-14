from __future__ import annotations

from typing import Any


def render_markdown(result: dict[str, Any]) -> str:
    metadata = result["metadata"]
    report = result["report"]
    source_map = {item["newsId"]: item for item in result.get("sources", [])}
    lines = [
        f"# {report.get('title', '일일 교육동향')}",
        "",
        f"- 분석 기간: {metadata.get('windowStart')} ~ {metadata.get('windowEnd')}",
        f"- 수집 후보: {metadata.get('candidateCount', metadata.get('processedCount'))}건",
        f"- 교육동향 채택: {metadata.get('relevantCount', metadata.get('processedCount'))}건",
        f"- 적합성 판별 제외: {metadata.get('filteredOutCount', 0)}건",
        f"- 사용 모델: {metadata.get('model')}",
        f"- 검증 상태: {metadata.get('reviewStatus')}",
        "",
        "## 종합 요약",
        "",
        report.get("executiveSummary", ""),
        "",
        "## 핵심 동향",
        "",
    ]

    for trend in report.get("keyTrends", []):
        lines.extend([f"### {trend.get('title', '교육동향')}", "", trend.get("description", ""), ""])
        evidence_links = []
        for news_id in trend.get("evidenceIds", []):
            source = source_map.get(news_id, {})
            title = source.get("title") or news_id
            url = source.get("url")
            evidence_links.append(f"[{title}]({url})" if url else title)
        if evidence_links:
            lines.extend(["근거: " + ", ".join(evidence_links), ""])

    if report.get("notableNews"):
        lines.extend(["## 주요 보도자료", ""])
        for notable in report["notableNews"]:
            source = source_map.get(notable.get("newsId"), {})
            title = source.get("title") or notable.get("newsId", "")
            url = source.get("url")
            label = f"[{title}]({url})" if url else title
            lines.append(f"- {label}: {notable.get('reason', '')}")
        lines.append("")

    if report.get("watchList"):
        lines.extend(["## 계속 확인할 사항", ""])
        lines.extend(f"- {item}" for item in report["watchList"])
        lines.append("")

    lines.extend(
        [
            "## 검증",
            "",
            f"- 최종 판정: {result.get('validation', {}).get('status', 'UNKNOWN')}",
            f"- 적합성 판별 대체 처리: {metadata.get('relevanceFallbackCount', 0)}건",
            f"- 분류 대체 처리: {metadata.get('classificationFallbackCount', 0)}건",
            "",
            "이 보고서는 공개 보도자료를 로컬 LLM으로 분석한 결과이며, 주요 판단에는 원문 링크를 함께 제공합니다.",
            "",
        ]
    )
    return "\n".join(lines)
