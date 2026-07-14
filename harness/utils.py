from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def compact_news(item: dict[str, Any], summary_limit: int = 650) -> dict[str, Any]:
    return {
        "newsId": item.get("id", ""),
        "source": item.get("source") or item.get("sourceName") or item.get("sourceId") or "",
        "title": normalize_space(item.get("title", ""))[:220],
        "date": item.get("date") or item.get("publishedAt") or "",
        "summary": normalize_space(item.get("summary") or item.get("contentPreview") or "")[:summary_limit],
    }


def render_prompt(name: str, **values: str) -> str:
    prompt = (ROOT / "prompts" / name).read_text(encoding="utf-8")
    for key, value in values.items():
        prompt = prompt.replace("{{" + key + "}}", value)
    return prompt


def chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[index : index + size] for index in range(0, len(items), size)]
