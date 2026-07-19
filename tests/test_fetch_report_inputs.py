import unittest
from datetime import date

from harness.fetch_report_inputs import historical_source


def selection_for(report_date="2026-07-17"):
    return {
        "metadata": {
            "windowStart": "2026-07-16T08:00:00+09:00",
            "windowEnd": f"{report_date}T08:00:00+09:00",
            "validationStatus": "PASS",
        },
        "selectedItems": [
            {"newsId": "news-1"},
            {"newsId": "news-2"},
        ],
    }


class HistoricalReportInputTest(unittest.TestCase):
    def test_builds_source_only_from_selected_ids(self):
        news = [
            {"id": "news-1", "summary": "first"},
            {"id": "ignored", "summary": "other"},
            {"id": "news-2", "summary": "second"},
        ]
        source = historical_source(selection_for(), news, date(2026, 7, 17))
        self.assertEqual(source["windowStart"], "2026-07-16T08:00:00+09:00")
        self.assertEqual(source["windowEnd"], "2026-07-17T08:00:00+09:00")
        self.assertEqual([item["id"] for item in source["items"]], ["news-1", "news-2"])

    def test_rejects_missing_source_or_weekend_date(self):
        with self.assertRaisesRegex(ValueError, "원문"):
            historical_source(selection_for(), [{"id": "news-1"}], date(2026, 7, 17))
        with self.assertRaisesRegex(ValueError, "주말"):
            historical_source(
                selection_for("2026-07-18"),
                [{"id": "news-1"}, {"id": "news-2"}],
                date(2026, 7, 18),
            )


if __name__ == "__main__":
    unittest.main()