from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from harness.gemini_client import GeminiClient
from harness.reporting import DailyReportHarness
from harness.reporting.renderers import render_html, write_hwpx
from harness.utils import read_json, write_json


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT = (ROOT / "public").resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="내부용 오늘의 교육동향 보고서 생성")
    parser.add_argument("--selection", default="public/briefings/latest.json", help="교육동향 선별 JSON")
    parser.add_argument("--source", default="public/latest.json", help="수집 원문 JSON")
    parser.add_argument("--output", default=".artifacts/daily-report", help="비공개 결과 디렉터리")
    parser.add_argument("--config", default="harness/report_config.json", help="보고서 설정 JSON")
    parser.add_argument("--skip-model-check", action="store_true")
    return parser.parse_args()


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def ensure_private_output(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == PUBLIC_ROOT or PUBLIC_ROOT in resolved.parents:
        raise ValueError("내부 보고서는 public 디렉터리에 저장할 수 없습니다.")
    return resolved


def create_client(api_key: str, model: str, config: dict[str, Any]) -> GeminiClient:
    return GeminiClient(
        api_key=api_key,
        model=model,
        timeout_seconds=int(config.get("requestTimeoutSeconds", 240)),
        max_output_tokens=int(config.get("maxOutputTokens", 4096)),
    )


def main() -> int:
    args = parse_args()
    config = read_json(resolve_path(args.config))
    api_key = os.environ.get("GEMINI_API_KEY", "")
    fact_model = os.environ.get("REPORT_FACT_MODEL") or config["factModel"]
    analysis_model = os.environ.get("REPORT_ANALYSIS_MODEL") or config["analysisModel"]
    verifier_model = os.environ.get("REPORT_VERIFIER_MODEL") or config["verifierModel"]
    fact_llm = create_client(api_key, fact_model, config)
    analysis_llm = create_client(api_key, analysis_model, config)
    verifier_llm = create_client(api_key, verifier_model, config)
    if not args.skip_model_check:
        checked: set[str] = set()
        for client in (fact_llm, analysis_llm, verifier_llm):
            if client.model not in checked:
                client.ensure_model()
                checked.add(client.model)

    selection = read_json(resolve_path(args.selection))
    source_payload = read_json(resolve_path(args.source))
    report = DailyReportHarness(fact_llm, analysis_llm, verifier_llm, config).run(selection, source_payload)

    output_dir = ensure_private_output(resolve_path(args.output))
    output_dir.mkdir(parents=True, exist_ok=True)
    date_key = str(report["metadata"].get("windowEnd") or report["metadata"]["generatedAt"])[:10]
    compact_date = date_key.replace("-", "")
    base_name = f"오늘의 교육동향 ({compact_date})"
    json_path = output_dir / f"{base_name}.json"
    html_path = output_dir / f"{base_name}.html"
    hwpx_path = output_dir / f"{base_name}.hwpx"

    html_path.write_text(render_html(report), encoding="utf-8")
    hwpx_validation = write_hwpx(report, hwpx_path)
    report["rendering"] = {
        "canonical": "json",
        "html": html_path.name,
        "hwpx": hwpx_path.name,
        "hwpxValidation": {
            "hardGates": hwpx_validation.get("hard_gates", {}),
            "packageOk": hwpx_validation.get("validate_package", {}).get("ok", False),
            "documentOk": hwpx_validation.get("validate_document", {}).get("ok", False),
            "reopenedOk": hwpx_validation.get("reopened", {}).get("ok", False),
            "visualReviewRequired": hwpx_validation.get("visual_review_required", True),
        },
    }
    write_json(json_path, report)
    print(json.dumps({
        "status": report["metadata"]["status"],
        "published": report["metadata"]["publishedCount"],
        "omitted": report["metadata"]["omittedCount"],
        "estimatedCostUsd": report["metadata"]["estimatedCostUsd"],
        "json": str(json_path),
        "html": str(html_path),
        "hwpx": str(hwpx_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())