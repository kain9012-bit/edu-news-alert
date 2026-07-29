import unittest

from harness.notify_telegram import build_caption


def report_with_omissions(count: int) -> dict:
    return {
        "metadata": {
            "windowEnd": "2026-07-29T08:00:00+09:00",
            "omittedCount": count,
        },
        "validation": {"status": "PASS"},
        "items": [
            {
                "title": "기초학력 지원 체계 확대",
                "source": "서울특별시교육청",
            }
        ],
    }


class TelegramCaptionTest(unittest.TestCase):
    def test_mentions_omissions_only_when_present(self) -> None:
        caption = build_caption(report_with_omissions(1))

        self.assertIn("교육동향 1건 · 검증 PASS", caption)
        self.assertIn("※ AI 검증·원문 품질 사유로 1건 제외", caption)

    def test_does_not_show_zero_omissions(self) -> None:
        caption = build_caption(report_with_omissions(0))

        self.assertIn("교육동향 1건 · 검증 PASS", caption)
        self.assertNotIn("제외", caption)


if __name__ == "__main__":
    unittest.main()
