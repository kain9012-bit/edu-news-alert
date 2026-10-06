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


_BULLET_MARKERS = r"[◦□○▪▫■●▲△▶◆➀-➉①-⑳※▸▹‣·]"


def clean_body(raw: Any) -> str:
    """개조식·표형 보도자료의 깨진 본문을 AI가 분석할 수 있는 한글 문장으로 정리한다.

    수집기가 표·개조식 게시글을 추출하면 숫자와 단위가 줄바꿈으로 쪼개지고(예: "60\\n일"),
    ◦·부제 대시·영문 각주가 섞인다. 이 상태로 분석하면 근거 검증이 원문과 맞지 않는다고
    판단해 항목이 요약만 남는다. 여기서 문장을 복원해 정상 분석이 가능하도록 만든다.
    """
    text = str(raw or "").replace("\r", "")
    # 문두 부제('- .... -'가 한 줄로 끝나는 경우)만 제거한다. 단어 내 하이픈은 건드리지 않는다.
    text = re.sub(r"^\s*[-–—]\s*[^\n]{4,70}?\s*[-–—]\s*(?=\n)", "", text)
    # 줄바꿈으로 쪼개진 숫자를 이어 붙인다("60\n일" -> "60일").
    text = re.sub(r"(\d)\s*\n\s*", r"\1", text)
    # 불릿 기호와 줄머리 대시를 공백으로 바꾼다.
    text = re.sub(_BULLET_MARKERS, " ", text)
    text = re.sub(r"^\s*[-–—]\s+", " ", text, flags=re.M)
    # 영문 각주(*로 시작하는 조각)를 제거한다.
    text = re.sub(r"\*\s*[A-Za-z][^\n]*", " ", text)
    text = text.replace("\n", " ")
    # 숫자와 한글 단위 사이의 불필요한 공백을 제거한다("60 일" -> "60일").
    text = re.sub(r"(\d)\s+(?=[가-힣%])", r"\1", text)
    text = re.sub(r"~\s+(\d)", r"~\1", text)
    # 괄호·문장부호 주변 공백을 정리한다.
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    text = re.sub(r"(?<=[가-힣])\s+\((?=[가-힣])", "(", text)
    text = re.sub(r"\s+([,\.\’”%])", r"\1", text)
    text = re.sub(r"([‘“])\s+", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _clean_fragment(text: str) -> str:
    """개조식 보도자료 조각에서 불릿·부제 대시·깨진 공백을 정리한다."""
    text = text.strip()
    text = re.sub(r"^[\-–—·•*\s]+", "", text)
    text = re.sub(r"[\-–—·•\s]+$", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,\.\’”\)\]%])", r"\1", text)
    text = re.sub(r"([‘“\(\[])\s+", r"\1", text)
    text = re.sub(r"(\d)\s+(?=[가-힣])", r"\1", text)
    text = re.sub(r"~\s+(\d)", r"~\1", text)
    return text.strip()


def _is_korean_body(text: str) -> bool:
    """한글 본문 조각만 남기고 영문 각주·기호줄을 배제한다."""
    if len(text) < 15:
        return False
    hangul = sum(1 for ch in text if "가" <= ch <= "힣")
    non_space = sum(1 for ch in text if not ch.isspace())
    return hangul >= 10 and hangul * 2 >= non_space


def _numbers_supported(text: str, compact_source: str) -> bool:
    """문장 속 숫자가 모두 원문에 있는지. 계산해서 만든 숫자(90%→10%)를 거른다."""
    for number in re.findall(r"\d[\d,\.]*", text or ""):
        token = number.rstrip(".,").replace(",", "")
        if token and token not in compact_source.replace(",", ""):
            return False
    return True


def fallback_summary(
    item: dict[str, Any], issues: list[dict[str, Any]], source: dict[str, Any]
) -> list[str]:
    """분석을 못 살려 요약만 남길 때, 원문 조각 대신 이미 만든 요약에서 성한 줄만 쓴다.

    예전엔 원문을 줄바꿈·마침표로 잘라 썼는데, "<2026. 난치병…>"처럼 연도 뒤
    마침표에서도 잘려 "…위해 <2026." / "…> 을 추진한다고 밝혔다." 같은 깨진 문장이
    보고서에 그대로 실렸다(2026-10-06). 사실 추출 단계의 요약은 원문을 근거로 이미
    다듬어져 있으므로, 지적받은 줄과 원문에 없는 숫자가 든 줄만 빼고 쓴다.
    """
    current = [p for p in (item.get("summaryPoints") or []) if isinstance(p, str)]
    if any(
        issue.get("field") == "summaryPoints" and int(issue.get("pointIndex", -1)) == -1
        for issue in issues
    ):
        current = []  # 요약 전체를 문제 삼았으면 쓰지 않는다
    flagged = {
        int(issue.get("pointIndex", -1))
        for issue in issues
        if issue.get("field") == "summaryPoints"
    }
    compact = re.sub(r"\s+", "", str(source.get("body") or ""))
    kept = [
        point.strip()
        for index, point in enumerate(current)
        if index not in flagged
        and len(point.strip()) >= 8
        and _numbers_supported(re.sub(r"\s+", "", point), compact)
    ]
    return kept[:5] if kept else source_summary(source)


def source_summary(source: dict[str, Any]) -> list[str]:
    """AI 요약이 없을 때 원문에서 읽을 만한 한글 요약 두 줄을 뽑는다.

    개조식(부제·불릿·마침표 없는 머리말) 보도자료도 줄바꿈과 불릿 기호로 조각내고
    깨진 띄어쓰기와 영문 각주를 정리해 사람이 읽기 좋은 형태로 만든다.
    """
    # 줄바꿈으로 쪼개진 숫자·문장을 먼저 이어 붙인 뒤 문장 단위로 자른다.
    body = clean_body(source.get("body") or "")
    title = normalize_space(str(source.get("title") or "보도자료"))
    # 마침표 앞이 숫자면 자르지 않는다("2026. 9. 21." 같은 날짜, "<2026. 사업명>").
    fragments = re.split(
        r"(?<=[가-힣A-Za-z\)\]’”][.!?])\s+|\s*" + _BULLET_MARKERS + r"\s*",
        body,
    )
    points: list[str] = []
    seen: set[str] = set()
    for fragment in fragments:
        cleaned = _clean_fragment(fragment)
        if not cleaned or cleaned == title or cleaned in seen:
            continue
        if not _is_korean_body(cleaned):
            continue
        cleaned = cleaned if len(cleaned) <= 140 else cleaned[:137].rstrip() + "..."
        points.append(cleaned)
        seen.add(cleaned)
        if len(points) == 2:
            break
    if not points:
        fallback = _clean_fragment(normalize_space(body)) or title
        points.append(fallback if len(fallback) <= 140 else fallback[:137].rstrip() + "...")
    return points


# 검증 모델이 "원문에서 경기도교육감은 임태희이나 보고서에는 안민석으로 잘못 기재됨"처럼
# 원문에 없는 내용을 원문이라고 지어내는 일이 있다(2026-10-06). 2026년 7월 교육감이
# 대거 바뀌었는데 모델은 그전 이름을 기억하고 있어서다. 프롬프트로 막아도 새어 나오므로
# 코드로 거른다. 인명에 관한 지적만 대상으로 삼아, 숫자·표현 지적은 건드리지 않는다.
_PERSON_HINT = re.compile(r"교육감|교육장|장관|차관|원장|청장|위원장|총장|시장|도지사|인명|이름|성명")
_SOURCE_CLAIM = re.compile(
    r"원문(?:에서|에는|에|은|는|상)?\s*(?P<src>.{1,40}?)"
    r"(?:이나|인데|이지만|으나|지만|이고|이며)\s*보고서(?:에는|에서|는|에|가)?\s*(?P<rep>.{1,30}?)(?:으로|로|라고|이라고)"
)
_PARTICLES = re.compile(r"(?:은|는|이|가|을|를|의|과|와|라고|이라고|으로|로)$")


def _claimed_value(segment: str) -> str:
    quoted = re.findall(r"['\"‘“]([^'\"’”]{1,30})['\"’”]", segment)
    if quoted:
        return quoted[-1].strip()
    words = re.findall(r"[가-힣A-Za-z0-9]+", segment)
    return _PARTICLES.sub("", words[-1]) if words else ""


def is_hallucinated_source_claim(message: str, source_body: str) -> bool:
    """검증 모델이 원문에 없는 인명을 '원문 내용'이라고 내세운 지적인지 가린다."""
    if not message or not _PERSON_HINT.search(message):
        return False
    match = _SOURCE_CLAIM.search(message)
    if not match:
        return False
    claimed = _claimed_value(match.group("src"))
    reported = _claimed_value(match.group("rep"))
    if not re.fullmatch(r"[가-힣]{2,4}", claimed or ""):
        return False  # 사람 이름 꼴이 아니면 판단하지 않는다
    compact = re.sub(r"\s+", "", source_body or "")
    if claimed in compact:
        return False  # 원문에 정말 있으면 정당한 지적이다
    # 원문에 없는 이름을 내세우고, 보고서 쪽 이름은 원문에 있으면 지어낸 지적이다.
    return not reported or reported in compact


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
    dropped = 0
    for issue in verification.get("issues", []):
        if not isinstance(issue, dict):
            continue
        if is_hallucinated_source_claim(str(issue.get("message", "")), source_body):
            dropped += 1
            continue
        issues.append({
            "field": issue.get("field", "item"),
            "pointIndex": issue.get("pointIndex", -1),
            "code": issue.get("code", "OTHER"),
            "message": issue.get("message", "근거에 맞게 수정해야 합니다."),
        })
    # 지적이 전부 지어낸 것이라 걸러졌다면, REVISE 판정도 근거가 없으므로 통과로 본다.
    real_issues = len(verification.get("issues") or []) - dropped
    if verification.get("status") != "PASS" and real_issues <= 0 and not dropped:
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
                item["summaryPoints"] = fallback_summary(item, issues, candidate_map[news_id])
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
