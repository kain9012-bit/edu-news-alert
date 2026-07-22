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


def inputs(include_own_source: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
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
    own_body = (
        "전북특별자치도교육청은 도내 모든 초등학교를 대상으로 기초학력 지원을 강화한다고 밝혔다. "
        "학교별 진단 결과를 바탕으로 맞춤형 학습 지원을 제공하고 교원 연수를 함께 운영한다. "
        "지원 과정은 학생 성장 기록과 연계하며 학교 현장의 의견을 반영해 단계적으로 보완한다. "
    )
    source_items = [
        {"id": "policy-1", "sourceId": "seoul", "summary": body},
        {"id": "support-1", "sourceId": "ulsan", "summary": body},
    ]
    if include_own_source:
        source_items.append(
            {
                "id": "own-1",
                "sourceId": "jeonbuk",
                "source": "전북특별자치도교육청",
                "title": "전북 기초학력 지원",
                "date": "2026-07-16",
                "url": "https://example.com/own-1",
                "summary": own_body,
            }
        )
    source = {
        "windowStart": metadata["windowStart"],
        "windowEnd": metadata["windowEnd"],
        "items": source_items,
    }
    return {"metadata": metadata, "selectedItems": selected}, source


class DailyReportHarnessTest(unittest.TestCase):
    def test_includes_all_own_office_sources_without_importance_or_selection(self) -> None:
        fact = FakeReportLLM("fake-lite", [
            {
                "items": [{
                    "newsId": "policy-1",
                    "summaryPoints": ["모든 초등학교의 기초학력 지원을 강화한다."],
                    "sourceFacts": ["학교별 진단 결과를 바탕으로 맞춤형 학습 지원을 제공한다."],
                    "confidence": 0.95,
                }]
            },
            {
                "items": [{
                    "newsId": "own-1",
                    "summaryPoints": [
                        "도내 모든 초등학교의 기초학력 지원을 강화한다.",
                        "학교별 진단 결과에 따라 맞춤형 학습 지원과 교원 연수를 운영한다.",
                    ],
                    "confidence": 0.94,
                }]
            },
        ])
        analysis = FakeReportLLM("fake-flash", [{
            "items": [{
                "newsId": "policy-1",
                "analysisPoints": ["진단과 지원을 연결하는 체계 강화 흐름으로 볼 수 있다."],
                "applicationReviewPoints": ["전북의 기존 지원 체계와 운영 방식을 비교해 볼 수 있다."],
                "confidence": 0.9,
            }]
        }])
        verifier = FakeReportLLM("fake-lite", [{
            "items": [
                {"newsId": "policy-1", "status": "PASS", "issues": [], "confidence": 0.93},
                {"newsId": "own-1", "status": "PASS", "issues": [], "confidence": 0.92},
            ]
        }])
        selection, source = inputs(include_own_source=True)

        report = DailyReportHarness(fact, analysis, verifier, report_config()).run(selection, source)

        self.assertFalse(any(item.get("newsId") == "own-1" for item in selection["selectedItems"]))
        self.assertEqual(report["metadata"]["publishedCount"], 1)
        self.assertEqual(report["metadata"]["ownOfficeEligibleCount"], 1)
        self.assertEqual(report["metadata"]["ownOfficePublishedCount"], 1)
        self.assertEqual({item["code"] for item in report["omittedItems"]}, {"SUPPORT_OFFICE"})
        self.assertNotIn("전북 기초학력 지원", fact.prompts[0])
        self.assertIn("전북 기초학력 지원", fact.prompts[1])
        self.assertNotIn("전북 기초학력 지원", analysis.prompts[0])
        self.assertNotIn("강남교육지원청", fact.prompts[0])
        self.assertIn('"newsId": "own-1"', verifier.prompts[0])
        self.assertIn('"analysisPoints": []', verifier.prompts[0])
        own_item = report["ownOfficeItems"][0]
        self.assertEqual(own_item["validation"]["status"], "PASS")
        self.assertLessEqual(len(own_item["summaryPoints"]), 2)
        self.assertNotIn("importance", own_item)
        self.assertNotIn("category", own_item)
        self.assertNotIn("analysisPoints", own_item)
        self.assertNotIn("applicationReviewPoints", own_item)
        rendered = render_html(report)
        own_html = rendered.split('id="own-item-1"', 1)[1].split("</article>", 1)[0]
        self.assertIn("전북 기초학력 지원", own_html)
        self.assertIn("https://example.com/own-1", own_html)
        self.assertNotIn('class="stars"', own_html)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report-with-own-office.hwpx"
            write_hwpx(report, output)
            from hwpx import HwpxDocument
            text = HwpxDocument.open(output).export_text()
            self.assertIn("https://example.com/own-1", text)
            self.assertGreater(
                text.rfind("전북 기초학력 지원"), text.rfind("전북교육청 보도자료")
            )
        self.assertEqual(
            [step["step"] for step in report["trace"]],
            ["extract_facts", "summarize_own_office", "analyze_trends", "verify_report"],
        )

    def test_keeps_own_office_source_when_ai_summary_fails(self) -> None:
        fact = FakeReportLLM("fake-lite", [
            {
                "items": [{
                    "newsId": "policy-1",
                    "summaryPoints": ["모든 초등학교의 기초학력 지원을 강화한다."],
                    "sourceFacts": ["학교별 진단 결과를 바탕으로 맞춤형 학습 지원을 제공한다."],
                    "confidence": 0.95,
                }]
            },
            {"items": []},
            {"items": []},
        ])
        analysis = FakeReportLLM("fake-flash", [{
            "items": [{
                "newsId": "policy-1",
                "analysisPoints": ["진단과 지원을 연결하는 체계 강화 흐름이다."],
                "applicationReviewPoints": [],
                "confidence": 0.9,
            }]
        }])
        verifier = FakeReportLLM("fake-lite", [{
            "items": [
                {"newsId": "policy-1", "status": "PASS", "issues": [], "confidence": 0.9},
                {"newsId": "own-1", "status": "PASS", "issues": [], "confidence": 0.9},
            ]
        }])
        selection, source = inputs(include_own_source=True)

        report = DailyReportHarness(fact, analysis, verifier, report_config()).run(selection, source)

        self.assertEqual(report["metadata"]["ownOfficePublishedCount"], 1)
        own_item = report["ownOfficeItems"][0]
        self.assertEqual(own_item["newsId"], "own-1")
        self.assertEqual(own_item["validation"]["status"], "REVIEW")
        self.assertTrue(own_item["reviewRequired"])
        self.assertGreaterEqual(len(own_item["summaryPoints"]), 1)
        self.assertLessEqual(len(own_item["summaryPoints"]), 2)
        self.assertIn("https://example.com/own-1", render_html(report))

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
        # 중요도가 낮은 항목은 검증에서 걸리면 그대로 제외된다.
        selection["selectedItems"][0]["importance"] = 2

        report = DailyReportHarness(fact, analysis, verifier, report_config()).run(selection, source)

        self.assertEqual(report["metadata"]["publishedCount"], 0)
        revised = [item for item in report["omittedItems"] if item["code"] == "REPORT_REVISE"]
        self.assertEqual(len(revised), 1)
        self.assertIn("관련 부서", revised[0]["reason"])

    def test_high_importance_item_kept_for_review_when_verification_fails(self) -> None:
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
                "analysisPoints": ["체계 강화 흐름이다."],
                "applicationReviewPoints": ["관련 부서에서 즉시 도입해야 한다."],
                "confidence": 0.8,
            }]
        }])
        verifier = FakeReportLLM("fake-lite", [{
            "items": [{"newsId": "policy-1", "status": "REVISE", "issues": [{"message": "부서 지정 표현"}], "confidence": 0.4}]
        }])
        selection, source = inputs()  # policy-1 중요도 4

        report = DailyReportHarness(fact, analysis, verifier, report_config()).run(selection, source)

        self.assertEqual(report["metadata"]["publishedCount"], 1)
        self.assertEqual(report["metadata"]["reviewCount"], 1)
        item = report["items"][0]
        self.assertTrue(item["reviewRequired"])
        self.assertEqual(item["validation"]["status"], "REVIEW")
        self.assertEqual(item["applicationReviewPoints"], [])
        self.assertFalse(any(o["code"] == "REPORT_REVISE" for o in report["omittedItems"]))
        rendered = render_html(report)
        self.assertIn("검토 필요", rendered)
        self.assertNotIn("관련 부서", rendered)

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
        self.assertIn("전북교육청 보도자료", rendered)

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
            self.assertIn("전북교육청 보도자료", text)


if __name__ == "__main__":
    unittest.main()