# llm.py
from __future__ import annotations

import json
import re
from typing import Any

import pymupdf  # PyMuPDF
import httpx

from config import settings

SYSTEM_PROMPT = (
    "Ты — эксперт по тендерной документации. Извлекай из документа "
    "структурированную информацию и отвечай ТОЛЬКО валидным JSON без пояснений."
)

USER_TEMPLATE = """Проанализируй тендерную документацию ниже и верни строго JSON такого формата:
{{
  "contract_amount": "сумма контракта (строка, например: «1 250 000 руб.» или «не указано»)",
  "execution_period": "сроки выполнения работ (строка, например: «до 30.06.2026» или «не указано»)",
  "requirements": ["ключевое требование к исполнителю", ...],
  "penalties": ["описание каждого штрафа или неустойки", ...]
}}

Если каких-то данных в документе нет — используй пустую строку "" или пустой список [],
не выдумывай информацию.

Текст документа:
---
{document}
---"""


async def extract_text(path: str) -> str:
    """Извлекает текст из PDF-файла через PyMuPDF."""
    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        raise ValueError(f"Не удалось открыть PDF: {exc}") from exc
    try:
        pages = [page.get_text() or "" for page in doc]
        text = "\n".join(pages).strip()
        return text or "В документе не найден текст."
    finally:
        doc.close()


def _extract_json(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
        content = re.sub(r"\s*```$", "", content)
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("LLM ответ не содержал JSON.")
    return json.loads(content[start : end + 1])


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [line.strip() for line in value.splitlines() if line.strip()]
    return []


def _normalize(parsed: dict) -> dict[str, Any]:
    def clean(name: str) -> str | None:
        value = str(parsed.get(name) or "").strip()
        return value or None

    result = {
        "contract_amount": clean("contract_amount"),
        "execution_period": clean("execution_period"),
        "requirements": _as_list(parsed.get("requirements")),
        "penalties": _as_list(parsed.get("penalties")),
        "raw_llm_response": parsed,
    }
    return result


async def summarize_document(text: str) -> dict[str, Any]:
    """Вызывает Ollama и возвращает нормализованную выжимку по документу."""
    user_message = USER_TEMPLATE.format(
        document=text[: settings.llm_max_chars]
    )
    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "temperature": 0.0,
        "format": "json",
        "options": {"num_predict": 2000},
    }
    url = settings.ollama_url.rstrip("/") + "/api/chat"
    timeout = httpx.Timeout(settings.llm_timeout_seconds)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

    content = data["message"]["content"]
    parsed = _extract_json(content)
    return _normalize(parsed)