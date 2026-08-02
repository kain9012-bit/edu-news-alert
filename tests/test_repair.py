from __future__ import annotations

import unittest

from harness.reporting.repair import clean_body, source_summary


class CleanBodyTest(unittest.TestCase):
    def test_restores_broken_numbers_and_bullets(self) -> None:
        raw = (
            "폭발적인 행정심판 청구 증가 속\n‘60\n일 재결\n’\n획기적 성과 달성\n"
            "◦\n도교육청\n,\n행정심판 청구 신속 대응 위해 업무 프로세스 개선 추진\n"
            "경기도교육청\n(\n교육감 안민석\n)\n이 업무 프로세스 개선을 추진했다\n.\n"
            "지난해 평균\n128\n일이 소요되던 재결 기간을\n2026\n년\n7\n월 기준\n60\n일로 단축했다."
        )
        cleaned = clean_body(raw)
        self.assertIn("60일 재결", cleaned)
        self.assertIn("128일", cleaned)
        self.assertIn("2026년 7월", cleaned)
        self.assertNotIn("◦", cleaned)
        self.assertNotIn("\n", cleaned)

    def test_removes_subtitle_and_english_footnote_but_keeps_hyphen_words(self) -> None:
        raw = (
            "- 온라인 사전입력 안내 -\n"
            "경북교육청(교육감 임종식)은 설명회를 개최했다.\n"
            "교육부는 대학기초연구소 지원(G-LAMP) 사업을 발표한다.\n"
            "*G-LAMP : Global-Learning & Academic research institution"
        )
        cleaned = clean_body(raw)
        self.assertNotIn("온라인 사전입력 안내", cleaned)  # 부제 제거
        self.assertIn("(G-LAMP)", cleaned)  # 단어 내 하이픈 보존
        self.assertNotIn("Global-Learning", cleaned)  # 영문 각주 제거
        self.assertIn("설명회를 개최했다", cleaned)

    def test_keeps_clean_body_unchanged(self) -> None:
        raw = "서울시교육청은 기초학력 지원을 강화한다고 밝혔다. 맞춤형 학습을 제공한다."
        self.assertEqual(clean_body(raw), raw)


class SourceSummaryTest(unittest.TestCase):
    def test_produces_readable_korean_points(self) -> None:
        body = (
            "- 부제 머리말 -\n경북교육청(교육감 임종식)은 31일 설명회를 개최했다고 밝혔다.\n"
            "이번 설명회는 변경된 제도를 안내하기 위해 마련됐다."
        )
        points = source_summary({"body": body, "title": "경북교육청, 설명회 개최"})
        self.assertEqual(len(points), 2)
        self.assertTrue(all(p and "\n" not in p for p in points))
        self.assertIn("설명회를 개최했다", points[0])


if __name__ == "__main__":
    unittest.main()
