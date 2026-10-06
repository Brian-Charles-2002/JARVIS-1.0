"""Gemini client wrapper using the official `google-genai` SDK.

Isolates every API interaction: connection, function-calling round-trips, error
handling and limited exponential-backoff retries. Never logs the API key.
"""
from __future__ import annotations

import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

# JARVIS drives function calling manually, so the SDK's AFC advisory is noise.
warnings.filterwarnings(
    "ignore",
    message=r"Direct use of automatic function calling.*",
    category=UserWarning,
)

from ai.prompts import system_instruction
from ai.tool_adapter import build_tools, to_contents
from config.settings import Settings
from core.conversation import ChatMessage, ChatPart
from core.exceptions import AIError, AuthenticationError, RateLimitError
from core.logging_setup import get_logger

logger = get_logger("ai.gemini")

_RETRYABLE_CODES = {429, 500, 502, 503, 504}


@dataclass
class ModelResponse:
    kind: str  # "text" | "function_calls"
    text: str = ""
    function_calls: list[dict[str, Any]] = field(default_factory=list)


class GeminiClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_model

    # --- low level ----------------------------------------------------------
    def _generate(self, contents: list[ChatMessage], tools: list[dict[str, Any]] | None,
                  system: str, temperature: float = 0.6) -> types.GenerateContentResponse:
        config_kwargs: dict[str, Any] = {
            "system_instruction": system,
            "temperature": temperature,
        }
        if tools:
            config_kwargs["tools"] = build_tools(tools)
        config = types.GenerateContentConfig(**config_kwargs)
        sdk_contents = to_contents(contents)
        return self._call_with_retry(sdk_contents, config)

    def _call_with_retry(self, sdk_contents, config) -> types.GenerateContentResponse:
        last_error: Exception | None = None
        attempts = 4
        delay = 1.0
        for attempt in range(attempts):
            try:
                return self._client.models.generate_content(
                    model=self._model, contents=sdk_contents, config=config
                )
            except Exception as exc:  # noqa: BLE001 - classify SDK errors
                last_error = exc
                raw_code = getattr(exc, "code", None)
                try:
                    code = int(raw_code) if raw_code is not None else None
                except (TypeError, ValueError):
                    code = None
                message = str(exc)
                lowered = message.lower()
                is_auth = (
                    code in (401, 403)
                    or (code == 400 and ("api key" in lowered or "api_key" in lowered
                                         or "permission" in lowered or "authenticat" in lowered))
                )
                if is_auth:
                    raise AuthenticationError(f"Gemini rejected the API key: {_short(message)}") from exc
                if code == 429 or "rate limit" in lowered or "quota" in lowered:
                    if attempt < attempts - 1:
                        logger.warning("Rate limited; backing off %.1fs", delay)
                        time.sleep(delay)
                        delay *= 2
                        continue
                    raise RateLimitError(f"Gemini rate limit exceeded: {_short(message)}") from exc
                if code in _RETRYABLE_CODES or "timeout" in lowered or "unavailable" in lowered or "connection" in lowered:
                    if attempt < attempts - 1:
                        time.sleep(delay)
                        delay *= 2
                        continue
                raise AIError(f"Gemini request failed: {_short(message)}") from exc
        raise AIError(f"Gemini request failed after retries: {_short(str(last_error))}")

    # --- public API ---------------------------------------------------------
    def respond(self, contents: list[ChatMessage], tools: list[dict[str, Any]] | None,
                system: str | None = None) -> ModelResponse:
        """Send the conversation + tool schemas and return text or function calls."""
        system = system or system_instruction(self.settings.assistant_name)
        response = self._generate(contents, tools, system)
        return _parse_response(response)

    def summarize(self, text: str) -> str:
        """Summarize older conversation content into a compact note."""
        prompt = f"Summarize the following conversation in <=5 bullet lines, keeping names, paths and URLs:\n\n{text}"
        response = self._generate(
            [ChatMessage(role="user", parts=[ChatPart(text=prompt)])], None,
            "You summarize conversations concisely for an assistant's memory.",
        )
        return _parse_response(response).text

    def analyze_image(self, image_path: str | Path, instruction: str) -> str:
        """Vision: describe/analyze a screenshot. Only called on explicit request."""
        path = Path(image_path)
        if not path.exists():
            raise AIError(f"Image not found: {path}")
        mime = "image/png" if path.suffix.lower() in (".png",) else "image/jpeg"
        parts = [
            types.Part.from_bytes(data=path.read_bytes(), mime_type=mime),
            types.Part.from_text(text=instruction),
        ]
        response = self._client.models.generate_content(
            model=self._model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction="You analyze screenshots of a Windows desktop accurately and concisely."
            ),
        )
        return _parse_response(response).text

    def health_check(self) -> bool:
        """Lightweight connectivity/validation call."""
        try:
            self._client.models.generate_content(
                model=self._model,
                contents=[types.Content(role="user", parts=[types.Part.from_text(text="ping")])],
                config=types.GenerateContentConfig(max_output_tokens=8),
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini health check failed: %s", _short(str(exc)))
            return False


def _text_part(text: str) -> types.Part:
    return types.Part.from_text(text=text)


def _parse_response(response: types.GenerateContentResponse) -> ModelResponse:
    candidate = response.candidates[0] if response.candidates else None
    if candidate is None or candidate.content is None:
        return ModelResponse(kind="text", text="")
    texts: list[str] = []
    calls: list[dict[str, Any]] = []
    for part in candidate.content.parts or []:
        if getattr(part, "function_call", None):
            fc = part.function_call
            call: dict[str, Any] = {"name": fc.name, "args": dict(fc.args or {}), "id": fc.id}
            # Newer Gemini models attach a thought_signature to function-call
            # parts; it must be echoed back verbatim or the next request 400s.
            sig = getattr(part, "thought_signature", None)
            if sig is not None:
                call["thought_signature"] = sig
            calls.append(call)
        elif getattr(part, "text", None):
            texts.append(part.text)
    if calls:
        return ModelResponse(kind="function_calls", text="".join(texts).strip(), function_calls=calls)
    return ModelResponse(kind="text", text="".join(texts).strip())


def _short(message: str, limit: int = 200) -> str:
    message = message.replace("\n", " ")
    return message[:limit]
