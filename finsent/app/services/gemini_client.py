from __future__ import annotations

import json
from typing import Any

import requests

from finsent.app.config.settings import settings


class GeminiClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.api_key = api_key or settings.gemini_api_key
        self.model = model or settings.gemini_model
        self.timeout = timeout or settings.gemini_timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            }
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model)

    def generate_json(
        self,
        prompt: str,
        *,
        use_search_grounding: bool = False,
        temperature: float = 0.1,
        max_output_tokens: int = 1024,
    ) -> dict[str, Any] | list[Any] | None:
        if not self.configured:
            return None

        payload: dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
                "responseMimeType": "application/json",
            },
        }
        if use_search_grounding:
            payload["tools"] = [{"google_search": {}}]

        response = self.session.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            data=json.dumps(payload),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        text = self._extract_text(data)
        if not text:
            return None
        return self._parse_json(text)

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        candidates = payload.get("candidates") or []
        if not candidates:
            return ""
        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []
        chunks: list[str] = []
        for part in parts:
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
        return "\n".join(chunks).strip()

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any] | list[Any] | None:
        raw = text.strip()
        candidates = [raw]

        if "```" in raw:
            fence_chunks = raw.split("```")
            for chunk in fence_chunks:
                candidate = chunk.strip()
                if not candidate:
                    continue
                if candidate.lower().startswith("json"):
                    candidate = candidate[4:].strip()
                candidates.append(candidate)

        first_brace = raw.find("{")
        last_brace = raw.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            candidates.append(raw[first_brace : last_brace + 1])

        first_bracket = raw.find("[")
        last_bracket = raw.rfind("]")
        if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
            candidates.append(raw[first_bracket : last_bracket + 1])

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, (dict, list)):
                return parsed
        return None
