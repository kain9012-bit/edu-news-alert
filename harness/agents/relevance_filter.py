from __future__ import annotations

import json
import re
from typing import Any

from harness.utils import chunks, compact_news, render_prompt
from harness.validators import validate_relevance


SYSTEM_TREND_WORDS = [
    "정책",
    "제도",
    "예산",
    "교육과정",
    "전면 시행",
    "확대 운영",
    "종합 대책",
    "기본계획",
    "개편",
    "전체 학교",
    "전 학교",
    "지원 계획",
]
LOCAL_OR_INSTITUTION_WORDS = [
    "교육지원청",
    "교육연수원",
    "학생교육문화회관",
    "교육문화회관",
    "도서관",
    "초등학교",
    "중학교",
    "고등학교",
]
ONE_OFF_WORDS = ["방문", "내방", "공연", "전시", "대회", "수상", "체험", "캠페인", "봉사", "업무협약", "간담회"]
ROUTINE_ACTIVITY_WORDS = ONE_OFF_WORDS + ["협의회", "연수", "캠프", "콘서트", "박람회", "성료", "행사", "운영"]
POLICY_EXCEPTION_WORDS = [
    "기본계획",
    "시행계획",
    "조례",
    "예산",
    "전면 시행",
    "의무화",
    "제도",
    "정책",
    "개편",
    "재구조화",
    "모든 학교",
    "전체 학교",
    "전 학교",
]
PERSONNEL_APPOINTMENT_WORDS = [
    "인사 단행",
    "인사단행",
    "인사발령",
    "인사 발령",
    "정기인사",
    "정기 인사",
    "인사 발표",
    "인사 명단",
    "승진·전보",
    "승진 및 전보",
    "전보 인사",
    "고위직 인사",
    "임명장 수여",
]
PERSONNEL_POLICY_WORDS = [
    "인사제도",
    "인사 제도",
    "인사정책",
    "인사 정책",
    "인사기준",
    "인사 기준",
    "인사원칙",
    "인사 원칙",
    "인사혁신",
    "인사 혁신",
    "인사 운영 계획",
]
SUPPORT_OFFICE_PATTERN = re.compile(r"([가-힣]{1,20})교육지원청")


class RelevanceFilterAgent:
    name = "relevance_filter"

    def __init__(self, llm: Any, batch_size: int = 6, max_attempts: int = 2) -> None:
        self.llm = llm
        self.batch_size = max(1, batch_size)
        self.max_attempts = max(1, max_attempts)

    def run(self, news_items: list[dict[str, Any]]) -> dict[str, Any]:
        output: list[dict[str, Any]] = []
        attempts = 0
        fallback_count = 0
        guard_count = 0
        guard_counts = {
            "educationSupportOffice": 0,
            "institutionActivity": 0,
            "personnelAppointment": 0,
        }
        errors: list[dict[str, Any]] = []

        for batch in chunks(news_items, self.batch_size):
            compact = [compact_news(item) for item in batch]
            prefiltered = {
                item["newsId"]: self._support_office_exclusion(item)
                for item in compact
                if self._is_support_office_item(item)
            }
            candidates = [item for item in compact if item["newsId"] not in prefiltered]
            guard_count += len(prefiltered)
            guard_counts["educationSupportOffice"] += len(prefiltered)

            if not candidates:
                output.extend(prefiltered[item["newsId"]] for item in compact)
                continue

            expected_ids = {item["newsId"] for item in candidates}
            source_map = {item["newsId"]: item for item in candidates}
            accepted: list[dict[str, Any]] | None = None
            last_error = ""

            for _ in range(self.max_attempts):
                attempts += 1
                prompt = render_prompt(
                    "relevance_filter.md",
                    ITEMS_JSON=json.dumps(candidates, ensure_ascii=False),
                )
                try:
                    raw = self.llm.generate_json(prompt)
                    values = raw.get("items") if isinstance(raw, dict) else raw
                    if not validate_relevance(values, expected_ids):
                        accepted = [self._enrich(item, source_map[item["newsId"]]) for item in values]
                        accepted = [self._apply_exclusion_guards(item) for item in accepted]
                        guard_count += sum(1 for item in accepted if item.get("guarded"))
                        guard_counts["institutionActivity"] += sum(
                            1 for item in accepted if item.get("guardType") == "institution_activity"
                        )
                        guard_counts["personnelAppointment"] += sum(
                            1 for item in accepted if item.get("guardType") == "personnel_appointment"
                        )
                        break
                except Exception as error:
                    last_error = str(error)[:500]
                    continue

            if accepted is None:
                accepted = [self._fallback(item) for item in candidates]
                fallback_count += len(accepted)
                errors.append({"newsIds": sorted(expected_ids), "error": last_error or "응답 계약 검증 실패"})
            result_map = {item["newsId"]: item for item in accepted}
            result_map.update(prefiltered)
            output.extend(result_map[item["newsId"]] for item in compact)

        return {
            "items": output,
            "attempts": attempts,
            "fallbackCount": fallback_count,
            "guardCount": guard_count,
            "guardCounts": guard_counts,
            "errors": errors,
        }

    @staticmethod
    def _enrich(value: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
        return {
            **value,
            "source": source["source"],
            "title": source["title"],
            "date": source["date"],
        }

    @staticmethod
    def _fallback(item: dict[str, Any]) -> dict[str, Any]:
        if RelevanceFilterAgent._is_support_office_item(item):
            return RelevanceFilterAgent._support_office_exclusion(item)
        text = f"{item['title']} {item['summary']}"
        personnel_appointment = RelevanceFilterAgent._is_personnel_appointment(text)
        has_system_signal = any(word in text for word in SYSTEM_TREND_WORDS)
        has_local_signal = any(word in text for word in LOCAL_OR_INSTITUTION_WORDS)
        has_one_off_signal = any(word in text for word in ONE_OFF_WORDS)
        drop = personnel_appointment or (not has_system_signal and has_local_signal and has_one_off_signal)
        scope = "institution" if has_local_signal else "provincial"
        return {
            "newsId": item["newsId"],
            "decision": "DROP" if drop else "KEEP",
            "scope": scope,
            "reason": (
                "개인의 승진·전보·임용 등을 알리는 인사발령 자료로 교육동향 분석에서 제외했다."
                if personnel_appointment
                else "개별 기관의 일회성 활동으로 판단되어 교육동향 분석에서 제외했다."
                if drop
                else "정책 또는 다수 학교에 영향을 줄 가능성이 있어 교육동향 분석 대상으로 유지했다."
            ),
            "confidence": 0.25,
            "evidenceIds": [item["newsId"]],
            "source": item["source"],
            "title": item["title"],
            "date": item["date"],
            "fallback": True,
        }

    @classmethod
    def _apply_exclusion_guards(cls, item: dict[str, Any]) -> dict[str, Any]:
        return cls._apply_institution_guard(
            cls._apply_personnel_appointment_guard(cls._apply_support_office_guard(item))
        )

    @staticmethod
    def _is_support_office_item(item: dict[str, Any]) -> bool:
        title = str(item.get("title", ""))
        return bool(SUPPORT_OFFICE_PATTERN.search(title))

    @staticmethod
    def _support_office_exclusion(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "newsId": item["newsId"],
            "decision": "DROP",
            "scope": "local",
            "reason": "교육지원청 단위에서 작성한 자료는 교육동향 선별 범위에서 제외했습니다.",
            "confidence": 1.0,
            "evidenceIds": [item["newsId"]],
            "source": item.get("source", ""),
            "title": item.get("title", ""),
            "date": item.get("date", ""),
            "guarded": True,
            "guardType": "education_support_office",
        }

    @classmethod
    def _apply_support_office_guard(cls, item: dict[str, Any]) -> dict[str, Any]:
        if item.get("decision") != "KEEP" or not cls._is_support_office_item(item):
            return item
        return cls._support_office_exclusion(item)

    @staticmethod
    def _is_personnel_appointment(text: str) -> bool:
        return (
            any(word in text for word in PERSONNEL_APPOINTMENT_WORDS)
            and not any(word in text for word in PERSONNEL_POLICY_WORDS)
        )

    @classmethod
    def _apply_personnel_appointment_guard(cls, item: dict[str, Any]) -> dict[str, Any]:
        if item.get("decision") != "KEEP":
            return item
        text = str(item.get("title", ""))
        if not cls._is_personnel_appointment(text):
            return item
        return {
            **item,
            "decision": "DROP",
            "scope": "provincial",
            "reason": "개인의 승진·전보·임용 등을 알리는 인사발령 자료로 정책·제도 변화가 아니어서 제외했습니다.",
            "guarded": True,
            "guardType": "personnel_appointment",
        }

    @staticmethod
    def _apply_institution_guard(item: dict[str, Any]) -> dict[str, Any]:
        if item.get("decision") != "KEEP":
            return item
        text = str(item.get("title", ""))
        institution = any(word in text for word in LOCAL_OR_INSTITUTION_WORDS)
        routine = any(word in text for word in ROUTINE_ACTIVITY_WORDS)
        policy_exception = any(word in text for word in POLICY_EXCEPTION_WORDS)
        if not (institution and routine and not policy_exception):
            return item
        return {
            **item,
            "decision": "DROP",
            "scope": "institution" if "교육지원청" not in text else "local",
            "reason": "교육지원청·직속기관·학교가 주체인 일반 협의회·연수·행사로 정책·제도 변화가 확인되지 않아 제외했습니다.",
            "guarded": True,
            "guardType": "institution_activity",
        }
