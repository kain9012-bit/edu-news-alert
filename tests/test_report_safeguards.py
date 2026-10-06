"""2026-10-06 보고서에서 드러난 문제가 다시 생기지 않는지 확인한다.

- 검증 모델이 원문에 없는 옛 교육감 이름을 '원문'이라고 지어내 멀쩡한 분석을 지움
- OpenRouter에서 추론 토큰이 출력 한도에 합산돼 수정 단계 JSON이 잘림
- 잘린 뒤 스키마를 빼고 재요청해 형식이 무너짐
- 요약만 남길 때 원문을 '<2026.'처럼 숫자 뒤 마침표에서 잘라 깨진 문장이 실림
"""

from __future__ import annotations

import json
import unittest

import harness.openrouter_client as orc
from harness.reporting.repair import (
    fallback_summary,
    is_hallucinated_source_claim,
    source_summary,
    validation_issues,
)

GYEONGGI_BODY = "경기도교육청(교육감 안민석)은 10월 2일 에스토니아와 공동 성명을 발표했다. 안민석 교육감은"


class HallucinatedSourceClaimTest(unittest.TestCase):
    def test_drops_invented_former_superintendent(self) -> None:
        msg = "원문에서 경기도교육감은 임태희이나 보고서에는 안민석으로 잘못 기재됨"
        self.assertTrue(is_hallucinated_source_claim(msg, GYEONGGI_BODY))

    def test_keeps_real_name_mismatch(self) -> None:
        msg = "원문에서 경기도교육감은 안민석이나 보고서에는 임태희로 잘못 기재됨"
        self.assertFalse(is_hallucinated_source_claim(msg, GYEONGGI_BODY))

    def test_ignores_non_person_issues(self) -> None:
        for msg in [
            "원문에서 확인되지 않는 수치가 있습니다: ['10']",
            "원문은 '올해 상반기'라고 명시했으나 보고서는 '2026년 상반기'로 잘못 기재함",
            "관련 부서 또는 담당 업무를 임의로 지정한 표현이 있습니다.",
        ]:
            self.assertFalse(is_hallucinated_source_claim(msg, GYEONGGI_BODY), msg)

    def test_validation_issues_filters_invented_claim(self) -> None:
        item = {
            "newsId": "g1",
            "summaryPoints": ["경기도교육청이 에스토니아와 AI 교육 협력 공동 성명을 발표함"],
            "analysisPoints": ["해외 교육부와의 협력 체계를 마련한 사례임"],
            "applicationReviewPoints": ["전북은 해외 교육기관 협력 사례로 참고를 검토할 수 있음"],
        }
        verification = {
            "status": "REVISE",
            "issues": [{
                "field": "item", "pointIndex": -1, "code": "OTHER",
                "message": "원문에서 경기도교육감은 임태희이나 보고서에는 안민석으로 잘못 기재됨",
            }],
        }
        remaining = [
            i for i in validation_issues(item, GYEONGGI_BODY, verification)
            if "교육감" in i.get("message", "") or "근거 검증" in i.get("message", "")
        ]
        self.assertEqual(remaining, [])


class FallbackSummaryTest(unittest.TestCase):
    SOURCE = {
        "title": "충북교육청, 난치병 학생 의료비 지원",
        "body": "충북교육청은 난치병 학생 의료비를 90%까지 지원하며 1인당 최대 100만 원이다.",
    }

    def test_prefers_existing_summary_without_flagged_or_unsupported_lines(self) -> None:
        item = {"summaryPoints": [
            "충북교육청이 난치병 학생 의료비 지원 사업을 추진함",
            "의료비의 90%까지 지원하며 1인당 최대 100만 원",
            "본인부담은 10% 수준임",
        ]}
        issues = [{"field": "summaryPoints", "pointIndex": 2, "code": "UNSUPPORTED_NUMBER"}]
        points = fallback_summary(item, issues, self.SOURCE)
        self.assertEqual(len(points), 2)
        self.assertFalse(any("10%" in p for p in points))

    def test_source_summary_does_not_split_after_year(self) -> None:
        source = {
            "title": "t",
            "body": "충청북도교육청은 학생의 부담을 덜기 위해 <2026. 난치병 학생 의료비 지원 사업>을 추진한다고 밝혔다. "
                    "이번 사업은 학생의 건강 증진과 학습권 보장을 위한 것이다.",
        }
        first = source_summary(source)[0]
        self.assertFalse(first.endswith("<2026."), first)


class _Resp:
    def __init__(self, payload: dict) -> None:
        self.ok = True
        self.status_code = 200
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload


class OpenRouterRetryTest(unittest.TestCase):
    def test_truncated_response_retries_with_schema_and_bigger_limit(self) -> None:
        calls: list[dict] = []
        responses = [
            {"usage": {"completion_tokens": 4096, "completion_tokens_details": {"reasoning_tokens": 3500}},
             "choices": [{"finish_reason": "length", "message": {"content": '{"items":[{"newsId":"a","x":"잘'}}]},
            {"usage": {"completion_tokens": 5000, "completion_tokens_details": {"reasoning_tokens": 3500}},
             "choices": [{"finish_reason": "stop", "message": {"content": '{"items":[{"newsId":"a"}]}'}}]},
        ]

        def fake_post(self, body):  # noqa: ANN001
            calls.append({"type": body["response_format"]["type"], "max": body["max_tokens"]})
            return _Resp(responses[len(calls) - 1])

        original = orc.OpenRouterClient._post
        orc.OpenRouterClient._post = fake_post
        try:
            client = orc.OpenRouterClient(api_key="k", model="google/gemini-3.5-flash", max_output_tokens=16384)
            result = client.generate_json("p", {"type": "object"})
        finally:
            orc.OpenRouterClient._post = original

        self.assertEqual(result, {"items": [{"newsId": "a"}]})
        self.assertEqual([c["type"] for c in calls], ["json_schema", "json_schema"])
        self.assertEqual(calls[1]["max"], 32768)
        self.assertEqual(client.usage["thoughtsTokenCount"], 7000)


if __name__ == "__main__":
    unittest.main()
