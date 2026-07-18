from __future__ import annotations

import io
import unittest
import zipfile
from datetime import datetime

from crawler.collect import (
    KST,
    briefing_window,
    choose_best_summary,
    detail_url_from_seq,
    extract_hwpx_text_from_bytes,
    has_hard_failure_boilerplate,
    is_low_quality_summary,
    strip_attachment_header,
    strip_repeated_title,
)


class CollectorContentTest(unittest.TestCase):
    def test_monday_briefing_covers_previous_72_hours(self) -> None:
        window_start, window_end = briefing_window(datetime(2026, 7, 20, 8, 5, tzinfo=KST))

        self.assertEqual(window_start, datetime(2026, 7, 17, 8, 0, tzinfo=KST))
        self.assertEqual(window_end, datetime(2026, 7, 20, 8, 0, tzinfo=KST))

    def test_weekday_briefing_covers_previous_24_hours(self) -> None:
        window_start, window_end = briefing_window(datetime(2026, 7, 24, 8, 5, tzinfo=KST))

        self.assertEqual(window_start, datetime(2026, 7, 23, 8, 0, tzinfo=KST))
        self.assertEqual(window_end, datetime(2026, 7, 24, 8, 0, tzinfo=KST))

    def test_before_eight_uses_previous_briefing_day_rule(self) -> None:
        window_start, window_end = briefing_window(datetime(2026, 7, 21, 7, 30, tzinfo=KST))

        self.assertEqual(window_start, datetime(2026, 7, 17, 8, 0, tzinfo=KST))
        self.assertEqual(window_end, datetime(2026, 7, 20, 8, 0, tzinfo=KST))

    def test_detail_url_includes_source_specific_parameters(self) -> None:
        source = {
            "listUrl": "https://example.com/list.do?boardID=8&m=0401&s=news",
            "detailPath": "/view.do",
            "seqParam": "boardSeq",
            "detailParams": {"lev": "0", "statusYN": "W", "opType": "N"},
        }

        url = detail_url_from_seq(source, "12345")

        self.assertIn("boardSeq=12345", url)
        self.assertIn("statusYN=W", url)
        self.assertIn("opType=N", url)

    def test_strips_repeated_title_with_fragmented_whitespace(self) -> None:
        title = "인천광역시교육청, 부평 특수학교 설립 추진"
        content = "인천광역시교육청 , 부평 특수학교 설립 추진\n인천광역시교육청은 주민 협의회를 개최했다."

        cleaned = strip_repeated_title(content, title)

        self.assertEqual(cleaned, "인천광역시교육청은 주민 협의회를 개최했다.")

    def test_boilerplate_page_is_low_quality(self) -> None:
        content = "본문 바로가기 전체메뉴 보도자료 게시판 상세보기 테이블 첨부파일 다운로드 횟수"

        self.assertTrue(is_low_quality_summary(content, "학생 안전 대응 강화"))
        self.assertTrue(has_hard_failure_boilerplate(content))

    def test_extracts_text_from_hwpx_section_xml(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "Contents/section0.xml",
                '<hp:section xmlns:hp="urn:hancom"><hp:p><hp:run><hp:t>학생 안전 대응 체계를 강화한다.</hp:t></hp:run></hp:p></hp:section>',
            )

        extracted = extract_hwpx_text_from_bytes(buffer.getvalue())

        self.assertIn("학생 안전 대응 체계를 강화한다.", extracted)

    def test_attachment_replaces_gyeongbuk_boilerplate(self) -> None:
        html = "보도자료 게시판 상세보기 테이블 작성자 등록일 카테고리 첨부파일 다운로드 횟수"
        attachment = "경북교육청은 통합 기상상황판을 구축해 학교의 기상 재난 대응 체계를 강화한다고 밝혔다."

        summary, origin = choose_best_summary("통합 기상상황판 구축", html, attachment, "gyeongbuk")

        self.assertEqual(origin, "attachment")
        self.assertIn("기상 재난 대응 체계", summary)

    def test_strips_attachment_metadata_before_title(self) -> None:
        document = "보도자료\n2026. 7. 15.\n담당부서 교육안전과\n학생 안전 대응 강화\n경북교육청은 안전시스템을 운영한다."

        cleaned = strip_attachment_header(document, "학생 안전 대응 강화")

        self.assertEqual(cleaned, "경북교육청은 안전시스템을 운영한다.")

    def test_strips_attachment_header_despite_department_and_quote_variants(self) -> None:
        title = "[교육안전과]경북교육청, '안전하이' 구축...학생 안전 강화"
        document = "보도자료\n담당부서 교육안전과\n경북교육청, ‘안전하이’ 구축…학생 안전 강화\n경북교육청은 시스템을 정식 운영한다."

        cleaned = strip_attachment_header(document, title)

        self.assertEqual(cleaned, "경북교육청은 시스템을 정식 운영한다.")


if __name__ == "__main__":
    unittest.main()
