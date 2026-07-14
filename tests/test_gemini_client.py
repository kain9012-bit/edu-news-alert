from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from harness.gemini_client import GeminiClient


class GeminiClientTest(unittest.TestCase):
    @patch("harness.gemini_client.requests.post")
    def test_generate_json_uses_secret_header_and_records_usage(self, post: Mock) -> None:
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "candidates": [
                {"content": {"parts": [{"text": '{"items": []}'}]}}
            ],
            "usageMetadata": {
                "promptTokenCount": 30,
                "candidatesTokenCount": 5,
                "totalTokenCount": 35,
            },
        }
        post.return_value = response
        client = GeminiClient("secret-value", max_output_tokens=512)

        result = client.generate_json("테스트")

        self.assertEqual(result, {"items": []})
        request = post.call_args
        self.assertEqual(request.kwargs["headers"]["x-goog-api-key"], "secret-value")
        self.assertEqual(request.kwargs["json"]["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(client.usage["requests"], 1)
        self.assertEqual(client.usage["totalTokenCount"], 35)


if __name__ == "__main__":
    unittest.main()
