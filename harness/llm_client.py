from __future__ import annotations

import json
import re
from typing import Any

import requests


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    provider = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: int = 240,
        max_output_tokens: int = 1536,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max(256, max_output_tokens)
        self.usage: dict[str, int] = {}

    def available_models(self) -> list[str]:
        response = requests.get(f"{self.base_url}/api/tags", timeout=10)
        response.raise_for_status()
        return [item.get("name", "") for item in response.json().get("models", [])]

    def ensure_model(self) -> None:
        models = self.available_models()
        if self.model not in models:
            raise OllamaError(f"Ollama 모델을 찾을 수 없습니다: {self.model} (설치 모델: {', '.join(models)})")

    def generate_json(self, prompt: str) -> Any:
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "format": "json",
                "stream": False,
                "keep_alive": "10m",
                "options": {
                    "temperature": 0.1,
                    "num_ctx": 16384,
                    "num_predict": self.max_output_tokens,
                },
            },
            timeout=self.timeout_seconds,
        )
        if not response.ok:
            raise OllamaError(f"Ollama 요청 실패 ({response.status_code}): {response.text[:300]}")
        text = response.json().get("response", "")
        return parse_json_response(text)


def parse_json_response(text: str) -> Any:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as first_error:
        starts = [idx for idx in [cleaned.find("{"), cleaned.find("[")] if idx >= 0]
        if not starts:
            raise OllamaError(f"LLM JSON 해석 실패: {cleaned[:300]}") from first_error
        start = min(starts)
        end = max(cleaned.rfind("}"), cleaned.rfind("]"))
        if end <= start:
            raise OllamaError(f"LLM JSON 해석 실패: {cleaned[:300]}") from first_error
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as error:
            raise OllamaError(f"LLM JSON 해석 실패: {cleaned[:300]}") from error
