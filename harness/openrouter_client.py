"""OpenRouter로 같은 모델을 부르는 클라이언트.

부서 예산으로 받은 OpenRouter 키를 쓰기 위한 것이다. 모델은 지금 쓰던 것을
그대로 두고(google/gemini-3.1-flash-lite, google/gemini-3.5-flash) 경유지만
바꾼다. 프롬프트·스키마가 그대로이므로 결과도 달라지지 않아야 한다.

GeminiClient와 같은 모양(provider, ensure_model, generate_json, usage)을 갖춰
호출하는 쪽을 고치지 않고 바꿔 끼울 수 있게 했다.

주의: 게재현황 AI 보완검색(crawler/ai_coverage_search.py)은 제미나이의 구글
검색 연동에 기대므로 여기로 옮기지 않는다. 그쪽은 무료 한도로 계속 쓴다.
"""

from __future__ import annotations

import json
from typing import Any

import requests

from harness.llm_client import parse_json_response

API_BASE = "https://openrouter.ai/api/v1"


class OpenRouterError(RuntimeError):
    pass


class OpenRouterClient:
    provider = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str = "google/gemini-3.1-flash-lite",
        timeout_seconds: int = 240,
        max_output_tokens: int = 1536,
        referer: str = "https://github.com/kain9012-bit/edu-news-alert",
        title: str = "edu-news-alert",
    ) -> None:
        if not api_key.strip():
            raise OpenRouterError("OPENROUTER_API_KEY가 설정되지 않았습니다.")
        self.api_key = api_key.strip()
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max(256, max_output_tokens)
        # OpenRouter가 사용처를 구분할 때 쓰는 값. 없어도 동작한다.
        self.referer = referer
        self.title = title
        # OpenRouter가 실제로 어느 모델로 처리했는지. 라우팅 확인용.
        self.served_model = ""
        # Gemini 쪽과 같은 이름으로 모아 두어 기존 집계·단가 계산을 그대로 쓴다.
        self.usage = {
            "requests": 0,
            "promptTokenCount": 0,
            "candidatesTokenCount": 0,
            "thoughtsTokenCount": 0,
            "totalTokenCount": 0,
        }

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.referer,
            "X-Title": self.title,
        }

    def ensure_model(self) -> None:
        response = requests.get(f"{API_BASE}/models", headers=self._headers(), timeout=20)
        if not response.ok:
            raise OpenRouterError(
                f"OpenRouter 모델 목록 조회 실패 ({response.status_code}): {response.text[:300]}"
            )
        names = {str(m.get("id")) for m in (response.json().get("data") or [])}
        if names and self.model not in names:
            raise OpenRouterError(
                f"OpenRouter에 '{self.model}' 모델이 없습니다. 모델 이름을 확인하세요."
            )

    # 말머리를 붙이지 말라고 못 박는다. 스키마를 무시하는 모델이 있다
    # (gemini-3.5-flash가 "Here is the JSON requested:"를 붙여 보냈다).
    JSON_ONLY = (
        "\n\n반드시 JSON 값 하나만 출력하세요. 설명·머리말·코드펜스를 붙이지 마세요."
    )

    def _post(self, body: dict[str, Any]) -> requests.Response:
        return requests.post(
            f"{API_BASE}/chat/completions",
            headers=self._headers(),
            json=body,
            timeout=self.timeout_seconds,
        )

    def _read(self, response: requests.Response) -> str:
        if not response.ok:
            raise OpenRouterError(
                f"OpenRouter 요청 실패 ({response.status_code}): {response.text[:500]}"
            )
        payload = response.json()
        if payload.get("error"):
            raise OpenRouterError(
                f"OpenRouter 오류: {json.dumps(payload['error'], ensure_ascii=False)[:300]}"
            )
        self.served_model = str(payload.get("model") or "")
        self._record_usage(payload.get("usage", {}))
        choices = payload.get("choices") or []
        if not choices:
            raise OpenRouterError(f"OpenRouter 응답 후보가 없습니다: {str(payload)[:300]}")
        text = str((choices[0].get("message") or {}).get("content") or "")
        if not text.strip():
            finish = choices[0].get("finish_reason")
            raise OpenRouterError(f"OpenRouter 응답에 텍스트가 없습니다 (finish_reason={finish}).")
        return text

    def generate_json(self, prompt: str, schema: dict[str, Any] | None = None) -> Any:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": self.max_output_tokens,
        }
        if schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "strict": True, "schema": schema},
            }
        else:
            body["response_format"] = {"type": "json_object"}

        response = self._post(body)
        # 스키마를 아예 못 받는 모델은 HTTP 오류로 알려 준다.
        if not response.ok and schema and response.status_code in (400, 404, 422):
            body["response_format"] = {"type": "json_object"}
            body["messages"] = [{"role": "user", "content": prompt + self.JSON_ONLY}]
            response = self._post(body)

        text = self._read(response)
        try:
            return parse_json_response(text)
        except Exception:
            # 200을 주면서 말머리를 붙이는 모델이 있다. 한 번만 더, 더 강하게 요구한다.
            body["response_format"] = {"type": "json_object"}
            body["messages"] = [{"role": "user", "content": prompt + self.JSON_ONLY}]
            return parse_json_response(self._read(self._post(body)))

    def _record_usage(self, usage: dict[str, Any]) -> None:
        self.usage["requests"] += 1
        prompt = int(usage.get("prompt_tokens", 0) or 0)
        completion = int(usage.get("completion_tokens", 0) or 0)
        total = int(usage.get("total_tokens", 0) or 0) or (prompt + completion)
        self.usage["promptTokenCount"] += prompt
        self.usage["candidatesTokenCount"] += completion
        self.usage["totalTokenCount"] += total
