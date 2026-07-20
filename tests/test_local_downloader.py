import io
import json
import tempfile
import unittest
import urllib.error
import urllib.request
import zipfile
from unittest.mock import Mock, patch
from datetime import date
from pathlib import Path

from local_downloader.receiver import (
    ARTIFACT_NAME,
    _open_response,
    _request_json,
    ReportDownloadError,
    download_from_github,
    parse_report_archive,
    report_directory_complete,
    save_report,
    check_github_connection,
)
from local_downloader import scheduler
from local_downloader.settings import DownloaderSettings, load_settings, save_settings


REPORT_DATE = date(2026, 7, 17)
REPORT_ID = "20260716T230000Z-test1234"
REPOSITORY = "kain9012-bit/edu-news-alert-private-reports"


def make_archive(report_date=REPORT_DATE, report_id=REPORT_ID, validation_status="PASS"):
    payload = {
        "metadata": {
            "reportId": report_id,
            "status": "completed",
            "windowEnd": f"{report_date.isoformat()}T08:00:00+09:00",
        },
        "items": [],
        "omittedItems": [],
        "validation": {"status": validation_status},
        "trace": [],
    }
    compact = report_date.strftime("%Y%m%d")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            f"오늘의 교육동향 ({compact}).json",
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )
        archive.writestr(
            f"오늘의 교육동향 ({compact}).html",
            b"<!doctype html><html><body>report</body></html>",
        )
        archive.writestr(
            f"오늘의 교육동향 ({compact}).hwpx",
            b"PK\x03\x04hwpx-test-package",
        )
    return output.getvalue()


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit=-1):
        return self.payload


class FakeGitHub:
    def __init__(self):
        self.archive = make_archive()
        self.requests = []

    def __call__(self, request, timeout=60):
        self.requests.append((request, timeout))
        if "actions/artifacts?" in request.full_url:
            listing = {
                "total_count": 1,
                "artifacts": [
                    {
                        "id": 101,
                        "name": ARTIFACT_NAME,
                        "expired": False,
                        "created_at": "2026-07-17T00:20:00Z",
                        "archive_download_url": (
                            f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/101/zip"
                        ),
                    }
                ],
            }
            return FakeResponse(json.dumps(listing).encode("utf-8"))
        if request.full_url.endswith("/artifacts/101/zip"):
            return FakeResponse(self.archive)
        raise AssertionError(f"Unexpected URL: {request.full_url}")


class LocalDownloaderTest(unittest.TestCase):
    def test_accepts_verified_weekday_report_archive(self):
        report = parse_report_archive(make_archive(), "101")
        self.assertEqual(report.artifact_id, "101")
        self.assertEqual(report.report_id, REPORT_ID)
        self.assertEqual(report.report_date, REPORT_DATE)
        self.assertEqual(set(report.files), {"json", "html", "hwpx"})

    def test_rejects_weekend_or_unverified_report(self):
        with self.assertRaisesRegex(ReportDownloadError, "주말"):
            parse_report_archive(make_archive(date(2026, 7, 18), "weekend"), "102")
        with self.assertRaisesRegex(ReportDownloadError, "검증"):
            parse_report_archive(make_archive(validation_status="FAIL"), "103")

    def test_saves_canonical_files_to_dated_document_folder(self):
        report = parse_report_archive(make_archive(), "101")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = save_report(report, root)
            self.assertTrue(report_directory_complete(root, REPORT_DATE))
            self.assertEqual(result.directory, root / REPORT_DATE.isoformat())
            self.assertTrue(result.changed)
            second = save_report(report, root)
            self.assertFalse(second.changed)

    def test_downloads_once_and_restores_deleted_file(self):
        github = FakeGitHub()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = root / "state.json"
            first = download_from_github(
                repository=REPOSITORY,
                token="github-token",
                save_root=root / "reports",
                state_path=state,
                opener=github,
                today=date(2026, 7, 19),
            )
            second = download_from_github(
                repository=REPOSITORY,
                token="github-token",
                save_root=root / "reports",
                state_path=state,
                opener=github,
                today=date(2026, 7, 19),
            )
            missing_hwpx = (
                root
                / "reports"
                / REPORT_DATE.isoformat()
                / f"오늘의 교육동향 ({REPORT_DATE.strftime('%Y%m%d')}).hwpx"
            )
            missing_hwpx.unlink()
            restored = download_from_github(
                repository=REPOSITORY,
                token="github-token",
                save_root=root / "reports",
                state_path=state,
                opener=github,
                today=date(2026, 7, 19),
            )
            saved_state = json.loads(state.read_text(encoding="utf-8"))

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(len(restored), 1)
        self.assertEqual(saved_state["processedArtifacts"][0]["artifactId"], "101")
        archive_calls = [
            request for request, _timeout in github.requests
            if request.full_url.endswith("/artifacts/101/zip")
        ]
        self.assertEqual(len(archive_calls), 2)
        self.assertEqual(archive_calls[0].get_header("Authorization"), "Bearer github-token")

    def test_cross_host_redirect_does_not_forward_github_token(self):
        request = urllib.request.Request(
            f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/101/zip",
            headers={"Authorization": "Bearer github-token", "User-Agent": "test"},
        )
        redirect = urllib.error.HTTPError(
            request.full_url,
            302,
            "Found",
            {"Location": "https://example-storage.invalid/signed-report.zip"},
            None,
        )
        direct_opener = Mock()
        direct_opener.open.side_effect = redirect
        signed_response = FakeResponse(b"zip")
        with patch("local_downloader.receiver.urllib.request.build_opener", return_value=direct_opener):
            with patch("local_downloader.receiver.urllib.request.urlopen", return_value=signed_response) as follow:
                response = _open_response(request, urllib.request.urlopen, timeout=60)
        redirected_request = follow.call_args.args[0]
        self.assertIs(response, signed_response)
        self.assertIsNone(redirected_request.get_header("Authorization"))

    def test_transient_github_503_is_retried(self):
        attempts = []

        def flaky_opener(request, timeout=60):
            attempts.append((request, timeout))
            if len(attempts) < 3:
                raise urllib.error.HTTPError(
                    request.full_url,
                    503,
                    "Service Unavailable",
                    {},
                    None,
                )
            return FakeResponse(b'{"ok": true}')

        with patch("local_downloader.receiver.time.sleep") as sleep:
            payload = _request_json(
                "https://api.github.com/test",
                "github-token",
                opener=flaky_opener,
            )

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(len(attempts), 3)
        self.assertEqual(sleep.call_count, 2)
    def test_connection_checks_actions_listing(self):
        github = FakeGitHub()
        check_github_connection(REPOSITORY, "github-token", opener=github)
        self.assertEqual(len(github.requests), 1)

    def test_settings_round_trip_without_plaintext_token(self):
        settings = DownloaderSettings(
            repository=REPOSITORY,
            save_root=r"C:\Users\kain9\Documents\오늘의 교육동향",
            auto_receive=True,
        )
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            save_settings(settings, "secret-value", path=path, protect=lambda _value: "opaque-ciphertext")
            raw = path.read_text(encoding="utf-8")
            loaded, token = load_settings(path=path, unprotect=lambda _value: "secret-value")
        self.assertNotIn("secret-value", raw)
        self.assertEqual(loaded, settings)
        self.assertEqual(token, "secret-value")

    def test_scheduler_uses_user_logon_entry_without_onlogon_task(self):
        with patch.object(
            scheduler,
            "launch_command",
            side_effect=['"receiver.exe" --scheduled', '"receiver.exe" --startup-check'],
        ), patch.object(scheduler, "_run_schtasks") as run_tasks, patch.object(
            scheduler,
            "_install_logon_entry",
        ) as install_logon:
            scheduler.install_tasks()

        self.assertEqual(run_tasks.call_count, 2)
        first_args = run_tasks.call_args_list[0].args[0]
        fallback_args = run_tasks.call_args_list[1].args[0]
        self.assertIn("09:15", first_args)
        self.assertIn("09:45", fallback_args)
        self.assertNotIn("ONLOGON", first_args + fallback_args)
        install_logon.assert_called_once_with('"receiver.exe" --startup-check')

    def test_scheduler_rolls_back_morning_task_when_logon_entry_fails(self):
        with patch.object(
            scheduler,
            "launch_command",
            side_effect=['"receiver.exe" --scheduled', '"receiver.exe" --startup-check'],
        ), patch.object(scheduler, "_run_schtasks") as run_tasks, patch.object(
            scheduler,
            "_install_logon_entry",
            side_effect=OSError("registry failure"),
        ), patch.object(scheduler, "_remove_logon_entry") as remove_logon:
            with self.assertRaises(OSError):
                scheduler.install_tasks()

        self.assertEqual(run_tasks.call_count, 4)
        self.assertEqual(run_tasks.call_args_list[2].args[0][:3], ["/Delete", "/F", "/TN"])
        self.assertEqual(run_tasks.call_args_list[3].args[0][:3], ["/Delete", "/F", "/TN"])
        remove_logon.assert_called_once()

if __name__ == "__main__":
    unittest.main()