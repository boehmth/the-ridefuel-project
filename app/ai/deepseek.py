"""
DeepSeek KI-Provider (OpenAI-kompatible API).

Nutzt das openai-SDK mit eigener Base-URL und eigenen Env-Variablen.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY fehlt in .env")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        _client = OpenAI(api_key=api_key, base_url=base_url)
    return _client


MAX_OUTPUT_TOKENS = int(os.getenv("DEEPSEEK_MAX_OUTPUT_TOKENS", "4096"))
TEMPERATURE = float(os.getenv("DEEPSEEK_TEMPERATURE", "1"))


def _extract_json(text: str) -> dict[str, Any]:
    if text is None:
        return {"error": "empty_response"}

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return {"error": "no_json_found", "raw": text}

    json_text = match.group(0)
    open_count = json_text.count("{")
    close_count = json_text.count("}")
    if open_count > close_count:
        json_text += "}" * (open_count - close_count)

    try:
        return json.loads(json_text)
    except Exception as e:
        return {"error": "invalid_json", "detail": str(e), "raw": json_text}


def call_llm(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """Ruft DeepSeek auf und liefert die Antwort als JSON-Dict."""
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    response = _get_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": user_prompt
                + "\n\nFORMAT: Antworte ausschließlich als reines JSON-Objekt. "
                "Kein Markdown, kein Fließtext.",
            },
        ],
        temperature=TEMPERATURE,
        max_tokens=MAX_OUTPUT_TOKENS,
    )
    return _extract_json(response.choices[0].message.content)
