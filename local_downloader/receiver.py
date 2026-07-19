from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable


ARTIFACT_NAME = "daily-education-trend-report"
REQUIRED_SUFFIXES = ("json", "html", "hwpx")
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_BYTES = 80 * 1024 * 1024
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class ReportDownloadError(RuntimeError):
    pass


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_response(request: urllib.request.Request, opener: Callable[..., Any], timeout: int):
    if opener is not urllib.request.urlopen:
        return opener(request, timeout=timeout)
    direct_opener = urllib.request.build_opener(_NoRedirectHandler)
    try:
        return direct_opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        location = exc.headers.get("Location") if exc.headers else None
        if exc.code not in (301, 302, 303, 307, 308) or not location:
            raise
        original_host = urllib.parse.urlparse(request.full_url).hostname
        redirect_host = urllib.parse.urlparse(location).hostname
        headers = {"User-Agent": "edu-news-alert-local-downloader"}
        if original_host == redirect_host:
            headers = dict(request.header_items())
        redirected = urllib.request.Request(location, headers=headers)
        return urllib.request.urlopen(redirected, timeout=timeout)


@dataclass(frozen=True)
class ParsedReport:
    artifact_id: str
    report_id: str
    report_date: date
    files: dict[str, bytes]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class DownloadedReport:
    artifact_id: str
    report_id: str
    report_date: date
    directory: Path
    filenames: tuple[str, ...]
    changed: bool


def is_weekday(value: date) -> bool:
    return value.weekday() < 5


def validate_repository(value: str) -> str:
    repository = value.strip().strip("/")
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise ValueError("저장소는 소유자/저장소 형식으로 입력해 주세요.")
    return repository


def report_directory_complete(save_root: Path, report_date: date) -> bool:
    compact = report_date.strftime("%Y%m%d")
    folder = save_root / report_date.isoformat()
    return all((folder / f"오늘의 교육동향 ({compact}).{suffix}").is_file() for suffix in REQUIRED_SUFFIXES)


def _request_bytes(
    url: str,
    token: str,
    *,
    accept: str,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> bytes:
    clean_token = token.strip()
    if not clean_token:
        raise ReportDownloadError("GitHub 읽기 토큰이 비어 있습니다.")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "Authorization": f"Bearer {clean_token}",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "edu-news-alert-local-downloader",
        },
    )
    try:
        with _open_response(request, opener, timeout=60) as response:
            payload = response.read(MAX_ARCHIVE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ReportDownloadError("GitHub 인증에 실패했습니다. 토큰과 Actions 읽기 권한을 확인해 주세요.") from exc
        if exc.code == 404:
            raise ReportDownloadError("비공개 보고서 저장소를 찾지 못했습니다. 저장소 이름과 토큰 권한을 확인해 주세요.") from exc
        raise ReportDownloadError(f"GitHub에서 파일을 받지 못했습니다. HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ReportDownloadError("GitHub에 연결하지 못했습니다. 인터넷 연결을 확인해 주세요.") from exc
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise ReportDownloadError("GitHub 결과 파일의 크기가 허용 범위를 넘었습니다.")
    return payload


def _request_json(
    url: str,
    token: str,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    payload = _request_bytes(
        url,
        token,
        accept="application/vnd.github+json",
        opener=opener,
    )
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReportDownloadError("GitHub 응답을 읽을 수 없습니다.") from exc
    if not isinstance(value, dict):
        raise ReportDownloadError("GitHub 응답 형식이 올바르지 않습니다.")
    return value


def _artifacts_url(repository: str) -> str:
    name = urllib.parse.quote(ARTIFACT_NAME, safe="")
    return f"https://api.github.com/repos/{validate_repository(repository)}/actions/artifacts?per_page=100&name={name}"


def check_github_connection(
    repository: str,
    token: str,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> None:
    payload = _request_json(_artifacts_url(repository), token, opener)
    if "artifacts" not in payload:
        raise ReportDownloadError("저장소의 Actions 결과 목록을 확인하지 못했습니다.")


def _parse_json_report(payload: bytes) -> dict[str, Any]:
    try:
        report = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReportDownloadError("보고서 JSON을 읽을 수 없습니다.") from exc
    if not isinstance(report, dict):
        raise ReportDownloadError("보고서 JSON의 최상위 값이 객체가 아닙니다.")
    metadata = report.get("metadata")
    validation = report.get("validation")
    if not isinstance(metadata, dict) or not isinstance(validation, dict):
        raise ReportDownloadError("보고서 JSON에 metadata 또는 validation이 없습니다.")
    if validation.get("status") != "PASS":
        raise ReportDownloadError("검증을 통과하지 않은 보고서입니다.")
    if not str(metadata.get("status", "")).startswith("completed"):
        raise ReportDownloadError("완료되지 않은 보고서입니다.")
    return report


def parse_report_archive(payload: bytes, artifact_id: str) -> ParsedReport:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ReportDownloadError("GitHub 결과 파일이 올바른 ZIP 패키지가 아닙니다.") from exc

    files: dict[str, bytes] = {}
    total = 0
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            parts = PurePosixPath(info.filename).parts
            if not parts or ".." in parts:
                raise ReportDownloadError("GitHub 결과 파일에 안전하지 않은 경로가 있습니다.")
            suffix = Path(parts[-1]).suffix.lower().lstrip(".")
            if suffix not in REQUIRED_SUFFIXES:
                continue
            if suffix in files:
                raise ReportDownloadError(f".{suffix} 보고서 파일이 두 개 이상입니다.")
            total += info.file_size
            if total > MAX_EXTRACTED_BYTES:
                raise ReportDownloadError("압축을 푼 보고서 크기가 허용 범위를 넘었습니다.")
            files[suffix] = archive.read(info)

    missing = [suffix for suffix in REQUIRED_SUFFIXES if suffix not in files]
    if missing:
        raise ReportDownloadError("필수 보고서 파일이 없습니다: " + ", ".join(missing))

    report = _parse_json_report(files["json"])
    metadata = report["metadata"]
    raw_date = str(metadata.get("windowEnd") or metadata.get("generatedAt") or "")[:10]
    try:
        report_date = date.fromisoformat(raw_date)
    except ValueError as exc:
        raise ReportDownloadError("JSON에서 보고서 날짜를 확인할 수 없습니다.") from exc
    if not is_weekday(report_date):
        raise ReportDownloadError("주말 날짜의 교육동향 보고서는 받지 않습니다.")
    report_id = str(metadata.get("reportId") or "").strip()
    if not report_id:
        raise ReportDownloadError("JSON에 보고서 고유번호가 없습니다.")
    if not files["hwpx"].startswith(b"PK"):
        raise ReportDownloadError("HWPX 파일이 올바른 문서 패키지가 아닙니다.")
    html_prefix = files["html"][:512].lower()
    if b"<html" not in html_prefix and b"<!doctype html" not in html_prefix:
        raise ReportDownloadError("HTML 파일 형식이 올바르지 않습니다.")
    return ParsedReport(
        artifact_id=str(artifact_id),
        report_id=report_id,
        report_date=report_date,
        files=files,
        metadata=metadata,
    )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def save_report(report: ParsedReport, save_root: Path) -> DownloadedReport:
    root = save_root.expanduser().resolve()
    target_dir = root / report.report_date.isoformat()
    target_dir.mkdir(parents=True, exist_ok=True)
    compact = report.report_date.strftime("%Y%m%d")
    targets = {suffix: target_dir / f"오늘의 교육동향 ({compact}).{suffix}" for suffix in REQUIRED_SUFFIXES}
    changed = any(
        not path.is_file() or _sha256(path.read_bytes()) != _sha256(report.files[suffix])
        for suffix, path in targets.items()
    )
    if changed:
        temporary_paths: list[Path] = []
        try:
            for suffix, target in targets.items():
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    prefix=f".{target.stem}-",
                    suffix=".part",
                    dir=target_dir,
                    delete=False,
                ) as handle:
                    handle.write(report.files[suffix])
                    handle.flush()
                    os.fsync(handle.fileno())
                    temporary_paths.append(Path(handle.name))
            for suffix, temporary in zip(REQUIRED_SUFFIXES, temporary_paths):
                os.replace(temporary, targets[suffix])
        finally:
            for temporary in temporary_paths:
                temporary.unlink(missing_ok=True)
    return DownloadedReport(
        artifact_id=report.artifact_id,
        report_id=report.report_id,
        report_date=report.report_date,
        directory=target_dir,
        filenames=tuple(targets[suffix].name for suffix in REQUIRED_SUFFIXES),
        changed=changed,
    )


def load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"processedArtifacts": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"processedArtifacts": []}
    if not isinstance(payload, dict) or not isinstance(payload.get("processedArtifacts", []), list):
        return {"processedArtifacts": []}
    return payload


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = [entry for entry in state.get("processedArtifacts", []) if isinstance(entry, dict)][-100:]
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps({"processedArtifacts": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _created_at(artifact: dict[str, Any]) -> datetime:
    raw = str(artifact.get("created_at") or "")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def download_from_github(
    repository: str,
    token: str,
    save_root: Path,
    state_path: Path,
    lookback_days: int = 14,
    opener: Callable[..., Any] = urllib.request.urlopen,
    today: date | None = None,
) -> list[DownloadedReport]:
    repository = validate_repository(repository)
    current_date = today or date.today()
    earliest_date = current_date - timedelta(days=max(1, lookback_days))
    listing = _request_json(_artifacts_url(repository), token, opener)
    artifacts = listing.get("artifacts")
    if not isinstance(artifacts, list):
        raise ReportDownloadError("GitHub Actions 결과 목록 형식이 올바르지 않습니다.")

    state = load_state(state_path)
    processed_entries = [entry for entry in state.get("processedArtifacts", []) if isinstance(entry, dict)]
    processed = {str(entry.get("artifactId")): entry for entry in processed_entries if entry.get("artifactId")}
    downloaded: list[DownloadedReport] = []

    candidates = [
        artifact for artifact in artifacts
        if isinstance(artifact, dict)
        and artifact.get("name") == ARTIFACT_NAME
        and not artifact.get("expired")
    ]
    candidates.sort(key=_created_at)
    for artifact in candidates:
        artifact_id = str(artifact.get("id") or "")
        if not artifact_id:
            continue
        prior = processed.get(artifact_id)
        if prior:
            try:
                prior_date = date.fromisoformat(str(prior.get("reportDate")))
            except ValueError:
                prior_date = None
            if prior_date and report_directory_complete(save_root, prior_date):
                continue
        archive_url = str(artifact.get("archive_download_url") or "")
        if not archive_url:
            archive_url = f"https://api.github.com/repos/{repository}/actions/artifacts/{artifact_id}/zip"
        archive_payload = _request_bytes(
            archive_url,
            token,
            accept="application/vnd.github+json",
            opener=opener,
        )
        try:
            report = parse_report_archive(archive_payload, artifact_id)
        except ReportDownloadError:
            continue
        if report.report_date < earliest_date or report.report_date > current_date:
            continue
        result = save_report(report, save_root)
        downloaded.append(result)
        processed[artifact_id] = {
            "artifactId": artifact_id,
            "reportId": report.report_id,
            "reportDate": report.report_date.isoformat(),
        }

    state["processedArtifacts"] = list(processed.values())
    save_state(state_path, state)
    downloaded.sort(key=lambda item: item.report_date)
    return downloaded