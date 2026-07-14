from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from harness.orchestrator import EducationTrendHarness
from harness.validators import validate_relevance


ROOT = Path(__file__).resolve().parents[1]


class FakeLLM:
    model = "fake-exaone"

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
        "model": "fake-exaone",
        "batchSize": 6,
        "maxItems": 0,
        "maxReviewAttempts": 2,
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


class EducationTrendHarnessTest(unittest.TestCase):
    def test_filters_before_classification_and_keeps_evidence_chain(self) -> None:
        llm = FakeLLM(
            [
                {
                    "items": [
                        {
                            "newsId": "policy-1",
                            "decision": "KEEP",
                            "scope": "provincial",
                            "reason": "전체 학교에 적용되는 정책 변화다.",
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
                },
                {
                    "items": [
                        {
                            "newsId": "policy-1",
                            "category": "디지털·AI",
                            "importance": "high",
                            "keywords": ["AI", "수업 지원"],
                            "summary": "전체 학교 대상 AI 수업 지원 정책을 시행한다.",
                            "confidence": 0.95,
                            "evidenceIds": ["policy-1"],
                        }
                    ]
                },
                {
                    "headline": "AI 수업 지원 확대",
                    "overview": "전북에서 AI 기반 수업 지원이 전체 학교로 확대됐다.",
                    "trends": [
                        {
                            "title": "AI 수업 지원 정책",
                            "description": "교원 연수와 수업 도구 지원이 함께 추진된다.",
                            "categories": ["디지털·AI"],
                            "evidenceIds": ["policy-1"],
                        }
                    ],
                    "notableNewsIds": ["policy-1"],
                },
                {
                    "title": "일일 교육동향",
                    "executiveSummary": "AI 기반 수업 지원 정책이 확대됐다.",
                    "keyTrends": [
                        {
                            "title": "AI 수업 지원 확대",
                            "description": "전체 학교 대상 지원이 시작됐다.",
                            "evidenceIds": ["policy-1"],
                        }
                    ],
                    "notableNews": [
                        {"newsId": "policy-1", "reason": "광역 정책 변화"}
                    ],
                    "watchList": ["세부 시행계획 확인"],
                },
                {"status": "PASS", "issues": [], "revisionInstructions": ""},
            ]
        )

        result = EducationTrendHarness(llm, config()).run(load_fixture())

        self.assertEqual(result["metadata"]["candidateCount"], 2)
        self.assertEqual(result["metadata"]["relevantCount"], 1)
        self.assertEqual(result["metadata"]["filteredOutCount"], 1)
        self.assertEqual([item["newsId"] for item in result["classifications"]], ["policy-1"])
        self.assertEqual([item["newsId"] for item in result["sources"]], ["policy-1"])
        self.assertEqual(result["validation"]["status"], "PASS")
        self.assertEqual(
            [step["step"] for step in result["trace"]],
            ["filter_relevance", "classify", "analyze", "write_report_1", "review_1"],
        )
        self.assertFalse(llm.responses)

    def test_all_dropped_returns_valid_empty_briefing(self) -> None:
        llm = FakeLLM(
            [
                {
                    "items": [
                        {
                            "newsId": item["id"],
                            "decision": "DROP",
                            "scope": "institution",
                            "reason": "개별 기관의 일회성 활동이다.",
                            "confidence": 0.9,
                            "evidenceIds": [item["id"]],
                        }
                        for item in load_fixture()["items"]
                    ]
                }
            ]
        )

        result = EducationTrendHarness(llm, config()).run(load_fixture())

        self.assertEqual(result["metadata"]["relevantCount"], 0)
        self.assertEqual(result["metadata"]["filteredOutCount"], 2)
        self.assertEqual(result["metadata"]["reviewStatus"], "PASS")
        self.assertEqual(result["report"]["keyTrends"], [])
        self.assertEqual([step["step"] for step in result["trace"]], ["filter_relevance"])

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


if __name__ == "__main__":
    unittest.main()
