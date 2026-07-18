import json
import tempfile
import unittest
from pathlib import Path

from harness.send_report_email import (
    SMTP_HOST,
    SMTP_PORT,
    build_message,
    discover_report_files,
    send_report_email,
)


class FakeSmtp:
    instances = []

    def __init__(self, host, port, **kwargs):
        self.host = host
        self.port = port
        self.kwargs = kwargs
        self.login_args = None
        self.message = None
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, message):
        self.message = message


class ReportEmailTest(unittest.TestCase):
    def make_files(self, root: Path):
        (root / "오늘의 교육동향 (20260718).json").write_text(json.dumps({
            "metadata": {"windowEnd": "2026-07-18T08:00:00+09:00"}
        }), encoding="utf-8")
        (root / "오늘의 교육동향 (20260718).html").write_text(
            "<html><body><h1>오늘의 교육동향</h1></body></html>", encoding="utf-8"
        )
        (root / "오늘의 교육동향 (20260718).hwpx").write_bytes(b"hwpx-package")
        return discover_report_files(root)

    def test_builds_html_message_with_all_report_attachments(self):
        with tempfile.TemporaryDirectory() as temp:
            files = self.make_files(Path(temp))
            message = build_message(files, "sender@gmail.com", "recipient@gmail.com")

        self.assertEqual(message["Subject"], "[오늘의 교육동향] 2026년 7월 18일")
        self.assertEqual(message["X-Education-Trend-Date"], "2026-07-18")
        self.assertIn("오늘의 교육동향", message.get_body(preferencelist=("html",)).get_content())
        self.assertEqual(
            {part.get_filename() for part in message.iter_attachments()},
            {
                "오늘의 교육동향 (20260718).json",
                "오늘의 교육동향 (20260718).html",
                "오늘의 교육동향 (20260718).hwpx",
            },
        )

    def test_sends_with_gmail_ssl_and_strips_app_password_spaces(self):
        FakeSmtp.instances.clear()
        with tempfile.TemporaryDirectory() as temp:
            files = self.make_files(Path(temp))
            send_report_email(
                files,
                "sender@gmail.com",
                "abcd efgh ijkl mnop",
                "recipient@gmail.com",
                smtp_factory=FakeSmtp,
            )

        smtp = FakeSmtp.instances[-1]
        self.assertEqual((smtp.host, smtp.port), (SMTP_HOST, SMTP_PORT))
        self.assertEqual(smtp.login_args, ("sender@gmail.com", "abcdefghijklmnop"))
        self.assertEqual(smtp.message["To"], "recipient@gmail.com")

    def test_requires_exactly_one_file_for_each_format(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "report.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "html"):
                discover_report_files(root)


if __name__ == "__main__":
    unittest.main()
