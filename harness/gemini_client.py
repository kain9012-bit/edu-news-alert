from __future__ import annotations

import json
from typing import Any

import requests

from harness.llm_client import parse_json_response


class GeminiError(RuntimeError):
    pass


class GeminiClient:
    provider = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash-lite",
        timeout_seconds: int = 240,
        max_output_tokens: int = 1536,
    ) -> None:
        if not api_key.strip():
            raise GeminiError("GEMINI_API_KEY가 설정되지 않았습니다.")
        self.api_key = api_key.strip()
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max(256, max_output_tokens)
        self.usage = {
            "requests": 0,
            "promptTokenCount": 0,
            "candidatesTokenCount": 0,
            "thoughtsTokenCount": 0,
            "totalTokenCount": 0,
        }

    def ensure_model(self) -> None:
        response = requests.get(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}",
            headers={"x-goog-api-key": self.api_key},
            timeout=20,
        )
        if not response.ok:
            raise GeminiError(f"Gemini 모델 확인 실패 ({response.status_code}): {response.text[:300]}")

    def generate_json(self, prompt: str) -> Any:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            headers={
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": self.max_output_tokens,
                    "responseMimeType": "application/json",
                },
            },
            timeout=self.timeout_seconds,
        )
        if not response.ok:
            raise GeminiError(f"Gemini 요청 실패 ({response.status_code}): {response.text[:500]}")

        payload = response.json()
        self._record_usage(payload.get("usageMetadata", {}))
        candidates = payload.get("candidates") or []
        if not candidates:
            feedback = json.dumps(payload.get("promptFeedback", {}), ensure_ascii=False)
            raise GeminiError(f"Gemini 응답 후보가 없습니다: {feedback[:300]}")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
        if not text.strip():
            raise GeminiError("Gemini 응답에 텍스트가 없습니다.")
        return parse_json_response(text)

    def _record_usage(self, usage: dict[str, Any]) -> None:
        self.usage["requests"] += 1
        for key in ["promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount", "totalTokenCount"]:
            self.usage[key] += int(usage.get(key, 0) or 0)
