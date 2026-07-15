from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from harness.agents.selection_validator import SelectionValidatorAgent
from harness.agents.relevance_filter import RelevanceFilterAgent
from harness.orchestrator import EducationTrendHarness
from harness.validators import validate_relevance


ROOT = Path(__file__).resolve().parents[1]


class FakeLLM:
    provider = "fake"
    model = "fake-gemini"
    usage = {"requests": 0, "totalTokenCount": 0}

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def generate_json(self, prompt: str) -> dict[str, Any]:
        self.prompts.append(prompt)
        if not self.responses:
            raise AssertionError("예상보다 많은 LLM 호출이 발생했습니다.")
        return self.responses.pop(0)


def load_fixture() -> dict[str, Any]:
    return json.loads(
        (ROOT / "tests" / "fixtures" / "sample_input.json").read_text(encoding="utf-8")
    )


def config() -> dict[str, Any]:
    return {
        "provider": "fake",
        "model": "fake-gemini",
        "batchSize": 6,
        "maxItems": 0,
        "categories": [
            "정책·행정",
            "교육과정·수업",
            "디지털·AI",
            "학생지원·복지",
            "교원·인사",
            "안전·시설",
            "진로·직업교육",
            "지역협력·행사",
            "기타",
        ],
    }


def relevance_response(keep_policy: bool = True) -> dict[str, Any]:
    return {
        "items": [
            {
                "newsId": "policy-1",
                "decision": "KEEP" if keep_policy else "DROP",
                "scope": "provincial" if keep_policy else "institution",
                "reason": "전체 학교에 적용되는 정책 변화다." if keep_policy else "정책적 파급력이 없는 단신이다.",
                "confidence": 0.96,
                "evidenceIds": ["policy-1"],
            },
            {
                "newsId": "event-1",
                "decision": "DROP",
                "scope": "institution",
                "reason": "개별 학교의 일회성 행사다.",
                "confidence": 0.98,
                "evidenceIds": ["event-1"],
            },
        ]
    }


class EducationTrendHarnessTest(unittest.TestCase):
    def test_filters_before_classification_and_outputs_selected_list(self) -> None:
        llm = FakeLLM(
            [
                relevance_response(),
                {
                    "items": [
                        {
                            "newsId": "policy-1",
                            "category": "디지털·AI",
                            "importance": 5,
                            "keywords": ["AI", "수업 지원"],
                            "summary": "전체 학교 대상 AI 수업 지원 정책을 시행한다.",
                            "confidence": 0.95,
                            "evidenceIds": ["policy-1"],
                        }
                    ]
                },
            ]
        )

        result = EducationTrendHarness(llm, config()).run(load_fixture())

        self.assertEqual(result["metadata"]["candidateCount"], 2)
        self.assertEqual(result["metadata"]["relevantCount"], 1)
        self.assertEqual(result["metadata"]["filteredOutCount"], 1)
        self.assertEqual([item["newsId"] for item in result["selectedItems"]], ["policy-1"])
        self.assertEqual([item["newsId"] for item in result["excludedItems"]], ["event-1"])
        self.assertEqual(result["selectedItems"][0]["category"], "디지털·AI")
        self.assertEqual(result["selectedItems"][0]["importance"], 5)
        self.assertEqual(result["validation"]["status"], "PASS")
        self.assertEqual(
            [step["step"] for step in result["trace"]],
            ["filter_relevance", "classify", "validate_selection"],
        )
        self.assertFalse(llm.responses)

    def test_all_dropped_skips_classification(self) -> None:
        llm = FakeLLM([relevance_response(keep_policy=False)])

        result = EducationTrendHarness(llm, config()).run(load_fixture())

        self.assertEqual(result["metadata"]["relevantCount"], 0)
        self.assertEqual(result["metadata"]["filteredOutCount"], 2)
        self.assertEqual(result["metadata"]["validationStatus"], "PASS")
        self.assertEqual(result["selectedItems"], [])
        self.assertEqual(
            [step["step"] for step in result["trace"]],
            ["filter_relevance", "validate_selection"],
        )

    def test_validator_rejects_classification_for_dropped_item(self) -> None:
        validator = SelectionValidatorAgent(config()["categories"])
        payload = load_fixture()
        relevance = relevance_response()["items"]
        invalid_classification = [
            {
                "newsId": "event-1",
                "category": "지역협력·행사",
                "evidenceIds": ["event-1"],
            }
        ]

        result = validator.run(payload["items"], relevance, invalid_classification)

        self.assertEqual(result["status"], "REVISE")
        self.assertTrue(any(item["code"] == "CLASSIFICATION_COVERAGE" for item in result["issues"]))

    def test_validator_rejects_importance_outside_five_point_scale(self) -> None:
        validator = SelectionValidatorAgent(config()["categories"])
        payload = load_fixture()
        relevance = relevance_response()["items"]
        invalid_classification = [
            {
                "newsId": "policy-1",
                "category": "디지털·AI",
                "importance": 6,
                "evidenceIds": ["policy-1"],
            }
        ]

        result = validator.run(payload["items"], relevance, invalid_classification)

        self.assertEqual(result["status"], "REVISE")
        self.assertTrue(any(item["code"] == "IMPORTANCE" for item in result["issues"]))

    def test_relevance_contract_rejects_unknown_evidence(self) -> None:
        errors = validate_relevance(
            [
                {
                    "newsId": "policy-1",
                    "decision": "KEEP",
                    "scope": "provincial",
                    "reason": "정책 변화",
                    "confidence": 0.8,
                    "evidenceIds": ["wrong-id"],
                }
            ],
            {"policy-1"},
        )
        self.assertTrue(any("evidenceIds" in error for error in errors))

    def test_institution_guard_drops_routine_support_office_meeting(self) -> None:
        guarded = RelevanceFilterAgent._apply_institution_guard(
            {
                "newsId": "local-1",
                "decision": "KEEP",
                "scope": "local",
                "reason": "학생 안전 협력 체계를 마련했다.",
                "confidence": 0.9,
                "evidenceIds": ["local-1"],
                "title": "장흥교육지원청, 여름방학 학생생활지도 협의회 개최",
            }
        )

        self.assertEqual(guarded["decision"], "DROP")
        self.assertTrue(guarded["guarded"])

    def test_personnel_appointment_guard_drops_head_office_announcement(self) -> None:
        guarded = RelevanceFilterAgent._apply_exclusion_guards(
            {
                "newsId": "personnel-1",
                "decision": "KEEP",
                "scope": "provincial",
                "reason": "본청 조직 운영에 영향을 준다.",
                "confidence": 0.9,
                "evidenceIds": ["personnel-1"],
                "title": "전남광주통합특별시교육청, 전남청사 고위직 인사 단행",
            }
        )

        self.assertEqual(guarded["decision"], "DROP")
        self.assertEqual(guarded["guardType"], "personnel_appointment")

    def test_personnel_policy_change_remains_eligible(self) -> None:
        guarded = RelevanceFilterAgent._apply_exclusion_guards(
            {
                "newsId": "personnel-policy-1",
                "decision": "KEEP",
                "scope": "provincial",
                "reason": "교원 인사제도를 개편한다.",
                "confidence": 0.9,
                "evidenceIds": ["personnel-policy-1"],
                "title": "교육청, 교원 인사제도 개편안 발표",
            }
        )

        self.assertEqual(guarded["decision"], "KEEP")


if __name__ == "__main__":
    unittest.main()
