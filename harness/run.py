from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from harness.gemini_client import GeminiClient
from harness.llm_client import OllamaClient
from harness.orchestrator import EducationTrendHarness
from harness.renderer import render_markdown
from harness.utils import read_json, write_json


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="교육동향 분석 AI Agent 하네스")
    parser.add_argument("--input", default="public/latest.json", help="입력 JSON 경로")
    parser.add_argument("--output", default="public/briefings", help="결과 디렉터리")
    parser.add_argument("--config", default="harness/config.json", help="하네스 설정 JSON")
    parser.add_argument("--provider", choices=["gemini", "ollama"], help="LLM 제공자")
    parser.add_argument("--model", help="Ollama 모델명")
    parser.add_argument("--ollama-url", help="Ollama API 주소")
    parser.add_argument("--max-items", type=int, help="처리할 최대 건수, 0은 전체")
    parser.add_argument("--max-output-tokens", type=int, help="에이전트별 최대 생성 토큰")
    parser.add_argument("--skip-model-check", action="store_true", help="Ollama 모델 확인 생략")
    return parser.parse_args()


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def write_outputs(output_dir: Path, result: dict[str, Any]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    date_key = str(result["metadata"].get("windowEnd") or result["metadata"]["generatedAt"])[:10]
    json_path = output_dir / f"{date_key}.json"
    markdown_path = output_dir / f"{date_key}.md"
    write_json(json_path, result)
    write_json(output_dir / "latest.json", result)
    markdown = render_markdown(result)
    markdown_path.write_text(markdown, encoding="utf-8")
    (output_dir / "latest.md").write_text(markdown, encoding="utf-8")
    write_json(output_dir / "runs" / f"{result['metadata']['runId']}.json", result)
    return json_path, markdown_path


def main() -> int:
    args = parse_args()
    config = read_json(resolve_path(args.config))
    provider = args.provider or os.environ.get("LLM_PROVIDER") or config.get("provider", "gemini")
    if provider == "ollama":
        model = args.model or os.environ.get("OLLAMA_MODEL") or "exaone3.5:7.8b"
    else:
        model = args.model or os.environ.get("LLM_MODEL") or config["model"]
    max_output_tokens = (
        args.max_output_tokens
        if args.max_output_tokens is not None
        else int(config.get("maxOutputTokens", 1536))
    )
    if provider == "gemini":
        llm = GeminiClient(
            api_key=os.environ.get("GEMINI_API_KEY", ""),
            model=model,
            timeout_seconds=int(config.get("requestTimeoutSeconds", 240)),
            max_output_tokens=max_output_tokens,
        )
    else:
        ollama_url = args.ollama_url or os.environ.get("OLLAMA_URL") or config["ollamaUrl"]
        llm = OllamaClient(
            base_url=ollama_url,
            model=model,
            timeout_seconds=int(config.get("requestTimeoutSeconds", 240)),
            max_output_tokens=max_output_tokens,
        )
    if not args.skip_model_check:
        llm.ensure_model()

    payload = read_json(resolve_path(args.input))
    harness = EducationTrendHarness(llm, config)
    result = harness.run(payload, max_items=args.max_items)
    json_path, markdown_path = write_outputs(resolve_path(args.output), result)
    print(
        json.dumps(
            {
                "status": result["metadata"]["status"],
                "provider": result["metadata"]["provider"],
                "processed": result["metadata"]["processedCount"],
                "validation": result["metadata"]["validationStatus"],
                "json": str(json_path),
                "markdown": str(markdown_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
