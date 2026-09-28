"""OpenRouter 키·모델이 실제로 동작하는지 확인한다. 키는 환경변수로만 받는다."""
import os, sys
sys.path.insert(0, ".")
from harness.openrouter_client import OpenRouterClient, OpenRouterError

key = os.environ.get("OPENROUTER_API_KEY", "")
if not key:
    print("OPENROUTER_API_KEY 환경변수가 없습니다."); raise SystemExit(1)

SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}, "sum": {"type": "integer"}},
    "required": ["ok", "sum"],
    "additionalProperties": False,
}
PROMPT = 'JSON으로만 답하세요. {"ok": true, "sum": <3+4의 값>}'

for model in ["google/gemini-3.1-flash-lite", "google/gemini-3.5-flash"]:
    try:
        c = OpenRouterClient(api_key=key, model=model, max_output_tokens=1024)
        c.ensure_model()
        out = c.generate_json(PROMPT, SCHEMA)
        good = out.get("sum") == 7
        print(f"  {'OK  ' if good else '이상'} 요청={model}")
        print(f"       실제응답모델={c.served_model}  결과={out}  토큰={c.usage['totalTokenCount']}")
    except OpenRouterError as e:
        print(f"  실패 {model}\n       {str(e)[:220]}")
    except Exception as e:
        print(f"  실패 {model}\n       {type(e).__name__}: {str(e)[:220]}")
