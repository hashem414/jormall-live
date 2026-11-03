from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests

from .config import Settings


class OpenAIUpstreamError(RuntimeError):
    pass


@dataclass(frozen=True)
class RetrievedChunk:
    index: int
    file_id: str
    filename: str
    score: float
    text: str
    attributes: dict[str, Any]
    section: str


def _extract_output_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    parts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and content.get("type") == "output_text":
                parts.append(str(content.get("text") or ""))
    return "\n".join(parts).strip()


class OpenAIHTTPClient:
    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.settings = settings
        self.session = session or requests.Session()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.session.post(
                f"{self.settings.openai_base_url}{path}",
                headers=self._headers,
                json=payload,
                timeout=(self.settings.connect_timeout_seconds, self.settings.read_timeout_seconds),
            )
        except requests.RequestException as exc:
            raise OpenAIUpstreamError("The OpenAI service could not be reached.") from exc
        if not response.ok:
            try:
                detail = response.json().get("error", {}).get("message", "")
            except (ValueError, AttributeError):
                detail = ""
            suffix = f": {detail[:300]}" if detail else ""
            raise OpenAIUpstreamError(f"OpenAI returned HTTP {response.status_code}{suffix}")
        try:
            return response.json()
        except ValueError as exc:
            raise OpenAIUpstreamError("OpenAI returned an invalid JSON response.") from exc

    def search_vector_store(self, question: str) -> list[dict[str, Any]]:
        payload = {
            "query": question,
            "max_num_results": min(12, max(self.settings.search_max_results * 2, 8)),
            "rewrite_query": True,
        }
        result = self._post(f"/vector_stores/{self.settings.vector_store_id}/search", payload)
        return [item for item in (result.get("data") or []) if isinstance(item, dict)]

    def create_answer(self, instructions: str, user_input: str) -> dict[str, Any]:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "answer": {"type": "string"},
                "used_live_page": {"type": "boolean"},
                "used_document_indexes": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
            },
            "required": ["answer", "used_live_page", "used_document_indexes"],
        }
        payload = self._post(
            "/responses",
            {
                "model": self.settings.model,
                "reasoning": {"effort": self.settings.reasoning_effort},
                "instructions": instructions,
                "input": user_input,
                "max_output_tokens": self.settings.max_output_tokens,
                "store": False,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "jormall_hybrid_answer",
                        "strict": True,
                        "schema": schema,
                    }
                },
            },
        )
        raw = _extract_output_text(payload)
        if not raw and payload.get("status") == "incomplete":
            reason = (payload.get("incomplete_details") or {}).get("reason") or "unknown reason"
            raise OpenAIUpstreamError(f"The AI response was incomplete: {reason}.")
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise OpenAIUpstreamError("The AI response did not match the required answer format.") from exc
        if not isinstance(parsed, dict) or not isinstance(parsed.get("answer"), str):
            raise OpenAIUpstreamError("The AI response was missing its answer.")
        return parsed
