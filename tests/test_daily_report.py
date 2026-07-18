from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from harness.reporting.orchestrator import DailyReportHarness
from harness.reporting.renderers import render_html, write_hwpx


class FakeReportLLM:
    provider = "fake"
    usage = {
        "requests": 0,
        "promptTokenCount": 0,
        "candidatesTokenCount": 0,
        "thoughtsTokenCount": 0,
        "totalTokenCount": 0,
    }

    def __init__(self, model: str, responses: list[dict[str, Any]]) -> None:
        self.model = model
        self.responses = list(responses)
        self.prompts: list[str] = []
        self.schemas: list[dict[str, Any] | None] = []

    def generate_json(self, prompt: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        self.prompts.append(prompt)
        self.schemas.append(schema)
        if not self.responses:
            raise AssertionError("예상보다 많은 LLM 호출이 발생했습니다.")
        return self.responses.pop(0)


def report_config() -> dict[str, Any]:
    return {
        "batchSize": 4,
        "maxBodyChars": 6000,
        "minBodyChars": 120,
        "ownOfficeSourceIds": ["jeonbuk"],
        "ownOfficeNames": ["전북특별자치도교육청"],
        "pricingPerMillionTokensUsd": {
            "fake-lite": {"input": 0.25, "output": 1.5},
            "fake-flash": {"input": 1.5, "output": 9.0},
        },
    }


def inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    metadata = {
        "runId": "selection-run",
        "validationStatus": "PASS",
        "windowStart": "2026-07-16T08:00:00+09:00",
        "windowEnd": "2026-07-17T08:00:00+09:00",
        "windowHours": 24,
    }
    selected = [
        {
            "newsId": "policy-1",
            "sourceId": "seoul",
            "source": "서울특별시교육청",
            "title": "기초학력 지원 체계 확대",
            "date": "2026-07-16",
            "url": "https://example.com/policy-1",
            "category": "학생지원·복지",
            "importance": 4,
            "selectionReason": "여러 학교에 적용되는 정책이다.",
        },
        {
            "newsId": "own-1",
            "sourceId": "jeonbuk",
            "source": "전북특별자치도교육청",
            "title": "전북 기초학력 지원",
            "date": "2026-07-16",
            "url": "https://example.com/own-1",
            "category": "학생지원·복지",
            "importance": 5,
            "selectionReason": "시도 전체 정책이다.",
        },
        {
            "newsId": "support-1",
            "sourceId": "ulsan",
            "source": "울산광역시교육청",
            "title": "강남교육지원청, 학습지원 사업 운영",
            "date": "2026-07-16",
            "url": "https://example.com/support-1",
            "category": "학생지원·복지",
            "importance": 2,
            "selectionReason": "지역 사업이다.",
        },
    ]
    body = (
        "서울특별시교육청은 모든 초등학교의 기초학력 지원을 강화한다고 밝혔다. "
        "학교별 진단 결과를 바탕으로 맞춤형 학습 지원을 제공하고 교원 연수를 함께 운영한다. "
        "지원 과정은 학생 성장 기록과 연계하며 학교 현장의 의견을 반영해 단계적으로 보완한다. "
    )
    source = {
        "windowStart": metadata["windowStart"],
        "windowEnd": metadata["windowEnd"],
        "items": [
            {"id": "policy-1", "sourceId": "seoul", "summary": body},
            {"id": "own-1", "sourceId": "jeonbuk", "summary": body},
            {"id": "support-1", "sourceId": "ulsan", "summary": body},
        ],
    }
    return {"metadata": metadata, "selectedItems": selected}, source


class DailyReportHarnessTest(unittest.TestCase):
    def test_excludes_own_office_and_support_office_before_ai(self) -> None:
        fact = FakeReportLLM("fake-lite", [{
            "items": [{
                "newsId": "policy-1",
                "summaryPoints": ["모든 초등학교의 기초학력 지원을 강화한다."],
                "sourceFacts": ["학교별 진단 결과를 바탕으로 맞춤형 학습 지원을 제공한다."],
                "confidence": 0.95,
            }]
        }])
        analysis = FakeReportLLM("fake-flash", [{
            "items": [{
                "newsId": "policy-1",
                "analysisPoints": ["진단과 지원을 연결하는 체계 강화 흐름으로 볼 수 있다."],
                "applicationReviewPoints": ["전북의 기존 지원 체계와 운영 방식을 비교해 볼 수 있다."],
                "confidence": 0.9,
            }]
        }])
        verifier = FakeReportLLM("fake-lite", [{
            "items": [{"newsId": "policy-1", "status": "PASS", "issues": [], "confidence": 0.93}]
        }])
        selection, source = inputs()

        report = DailyReportHarness(fact, analysis, verifier, report_config()).run(selection, source)

        self.assertEqual(report["metadata"]["publishedCount"], 1)
        self.assertEqual(report["metadata"]["ownOfficeExcludedCount"], 1)
        self.assertEqual({item["code"] for item in report["omittedItems"]}, {"OWN_OFFICE", "SUPPORT_OFFICE"})
        self.assertNotIn("전북 기초학력 지원", fact.prompts[0])
        self.assertNotIn("강남교육지원청", fact.prompts[0])
        self.assertEqual(report["items"][0]["validation"]["status"], "PASS")
        self.assertEqual([step["step"] for step in report["trace"]], ["extract_facts", "analyze_trends", "verify_report"])

    def test_local_validator_omits_department_assignment(self) -> None:
        fact = FakeReportLLM("fake-lite", [{
            "items": [{
                "newsId": "policy-1",
                "summaryPoints": ["모든 초등학교의 기초학력 지원을 강화한다."],
                "sourceFacts": ["학교별 진단 결과를 바탕으로 맞춤형 학습 지원을 제공한다."],
                "confidence": 0.95,
            }]
        }])
        analysis = FakeReportLLM("fake-flash", [{
            "items": [{
                "newsId": "policy-1",
                "analysisPoints": ["진단과 지원을 연결하는 체계 강화 흐름이다."],
                "applicationReviewPoints": ["관련 부서에서 즉시 도입해야 한다."],
                "confidence": 0.8,
            }]
        }])
        verifier = FakeReportLLM("fake-lite", [{
            "items": [{"newsId": "policy-1", "status": "PASS", "issues": [], "confidence": 0.8}]
        }])
        selection, source = inputs()

        report = DailyReportHarness(fact, analysis, verifier, report_config()).run(selection, source)

        self.assertEqual(report["metadata"]["publishedCount"], 0)
        revised = [item for item in report["omittedItems"] if item["code"] == "REPORT_REVISE"]
        self.assertEqual(len(revised), 1)
        self.assertIn("관련 부서", revised[0]["reason"])

    def test_html_and_hwpx_are_rendered_from_same_report(self) -> None:
        fact = FakeReportLLM("fake-lite", [{
            "items": [{
                "newsId": "policy-1",
                "summaryPoints": ["모든 초등학교의 기초학력 지원을 강화한다."],
                "sourceFacts": ["학교별 진단 결과를 바탕으로 맞춤형 학습 지원을 제공한다."],
                "confidence": 0.95,
            }]
        }])
        analysis = FakeReportLLM("fake-flash", [{
            "items": [{
                "newsId": "policy-1",
                "analysisPoints": ["진단과 지원을 연결하는 체계 강화 흐름으로 볼 수 있다."],
                "applicationReviewPoints": [],
                "confidence": 0.9,
            }]
        }])
        verifier = FakeReportLLM("fake-lite", [{
            "items": [{"newsId": "policy-1", "status": "PASS", "issues": [], "confidence": 0.93}]
        }])
        selection, source = inputs()
        report = DailyReportHarness(fact, analysis, verifier, report_config()).run(selection, source)

        rendered = render_html(report)
        self.assertIn("오늘의 교육동향", rendered)
        self.assertIn("직접 적용 검토사항 없음", rendered)
        self.assertNotIn("관련 부서", rendered)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.hwpx"
            validation = write_hwpx(report, output)
            self.assertTrue(output.exists())
            self.assertTrue(validation["validate_package"]["ok"])
            self.assertTrue(validation["reopened"]["ok"])
            from hwpx import HwpxDocument
            text = HwpxDocument.open(output).export_text()
            self.assertIn("오늘의 교육동향", text)
            self.assertIn("기초학력 지원 체계 확대", text)


if __name__ == "__main__":
    unittest.main()