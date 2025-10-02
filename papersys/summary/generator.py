"""Summary generation utilities powered by LLM configuration."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Dict, Protocol

from loguru import logger
import litellm

from papersys.config.llm import LLMConfig

from .models import SummaryDocument, SummarySource


class SummaryGenerationError(RuntimeError):
    """Raised when the LLM fails to produce a usable summary."""


class _LLMClient(Protocol):
    def summarise(self, source: SummarySource, *, language: str, context: str | None = None) -> dict[str, str]:
        """Return a mapping of section titles to rendered content."""
        ...


class SummaryGenerator:
    """Generate structured summaries using a real or stubbed LLM client."""

    def __init__(self, llm_config: LLMConfig, *, default_language: str, allow_latex: bool = False) -> None:
        self._client = _build_client(llm_config, allow_latex=allow_latex)
        self._default_language = default_language or "en"

    def generate(self, source: SummarySource, *, context: str | None = None) -> SummaryDocument:
        language = source.language or self._default_language
        logger.debug("Generating summary for {} using language {}", source.paper_id, language)
        sections = self._client.summarise(source, language=language, context=context)
        if not sections:
            raise SummaryGenerationError("LLM did not return any sections")
        return SummaryDocument(
            paper_id=source.paper_id,
            title=source.title,
            language=language,
            sections=sections,
        )


_SUMMARY_JSON_SCHEMA: Dict[str, Any] = {
    "name": "paper_summary",
    "schema": {
        "type": "object",
        "properties": {
            "highlights": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
            "summary": {"type": "string"},
        },
        "required": ["highlights", "summary"],
        "additionalProperties": False,
    },
}


_SUPPORTS_RESPONSE_SCHEMA = getattr(litellm, "supports_response_schema", None)
_GET_SUPPORTED_OPENAI_PARAMS = getattr(litellm, "get_supported_openai_params", None)


def _build_client(config: LLMConfig, *, allow_latex: bool) -> _LLMClient:
    base_url_value = config.base_url.strip()
    base_url_lower = base_url_value.lower()
    if base_url_lower.startswith("stub://") or base_url_lower.startswith("http://localhost"):
        logger.debug("Using stub LLM client for alias {}", config.alias)
        return _StubLLMClient(config, allow_latex=allow_latex)
    logger.debug("Using LiteLLM client for alias {}", config.alias)
    return _LiteLLMClient(config, api_base=base_url_value or None, allow_latex=allow_latex)


def _guess_custom_provider(base_url: str | None) -> str | None:
    if not base_url:
        return None
    normalized = base_url.strip().lower()
    if not normalized:
        return None
    provider_hints: tuple[tuple[str, str], ...] = (
        ("bedrock", "bedrock"),
        ("anthropic", "anthropic"),
        ("generativelanguage.googleapis", "google_ai"),
        ("googleapis.com", "google_ai"),
        ("vertex", "vertex_ai"),
        ("azure", "azure"),
        ("groq", "groq"),
        ("deepseek", "deepseek"),
        ("perplexity", "perplexity"),
        ("x.ai", "xai"),
        ("fireworks", "fireworks"),
        ("together.ai", "together_ai"),
    )
    for needle, provider in provider_hints:
        if needle in normalized:
            return provider
    return None


def _check_json_schema_support(model: str, provider: str | None) -> bool:
    if _SUPPORTS_RESPONSE_SCHEMA is None:
        return False
    attempts: list[str | None] = []
    if provider not in attempts:
        attempts.append(provider)
    attempts.append(None)
    seen: set[str | None] = set()
    for candidate in attempts:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            if _SUPPORTS_RESPONSE_SCHEMA(model=model, custom_llm_provider=candidate):  # type: ignore[misc]
                return True
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "LiteLLM schema support probe failed for model {} (provider {}): {}",
                model,
                candidate,
                exc,
            )
    return False


def _check_response_format_support(model: str, provider: str | None) -> bool:
    if _GET_SUPPORTED_OPENAI_PARAMS is None:
        return False
    attempts: list[str | None] = []
    if provider not in attempts:
        attempts.append(provider)
    attempts.append(None)
    seen: set[str | None] = set()
    for candidate in attempts:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            params = _GET_SUPPORTED_OPENAI_PARAMS(model=model, custom_llm_provider=candidate)  # type: ignore[misc]
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "LiteLLM response_format probe failed for model {} (provider {}): {}",
                model,
                candidate,
                exc,
            )
            continue
        if _contains_response_format(params):
            return True
    return False


def _contains_response_format(params: Any) -> bool:
    if params is None:
        return False
    if isinstance(params, dict):
        candidates: Iterable[str] = params.keys()
    elif isinstance(params, Iterable):
        candidates = params
    else:
        return False
    return any(str(item) == "response_format" for item in candidates)


@dataclass(slots=True)
class _LiteLLMClient:
    """Client that delegates LLM calls to LiteLLM."""

    config: LLMConfig
    api_base: str | None
    allow_latex: bool = False
    api_key: str = field(init=False, repr=False)
    _custom_provider: str | None = field(init=False, repr=False, default=None)
    _supports_json_schema: bool = field(init=False, repr=False, default=False)
    _supports_response_format: bool = field(init=False, repr=False, default=False)

    def __post_init__(self) -> None:
        self.api_key = self.config.api_key_secret
        self._custom_provider = _guess_custom_provider(self.api_base or self.config.base_url)
        self._supports_json_schema = _check_json_schema_support(self.config.name, self._custom_provider)
        self._supports_response_format = _check_response_format_support(self.config.name, self._custom_provider)
        logger.debug(
            "LiteLLM client ready for alias {} (model {}) - json_schema_supported={}, response_format_supported={}",
            self.config.alias,
            self.config.name,
            self._supports_json_schema,
            self._supports_response_format,
        )

    def summarise(self, source: SummarySource, *, language: str, context: str | None = None) -> dict[str, str]:
        system_parts = [
            "You are an assistant that produces structured academic paper summaries.",
            "Return valid JSON with two keys: 'highlights' (array of concise bullet sentences) and 'summary' (paragraph string).",
            "Respond in the requested language.",
        ]
        if not self.allow_latex:
            system_parts.append("Do not use LaTeX or math markup in the response; prefer plain text.")
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": " ".join(system_parts),
            }
        ]

        user_parts = [
            f"Language: {language}",
            f"Paper ID: {source.paper_id}",
            f"Title: {source.title}",
            f"Abstract: {source.abstract.strip()}",
        ]
        if context:
            user_parts.append("Paper Content:\n" + context.strip())

        messages.append({"role": "user", "content": "\n".join(user_parts)})

        call_kwargs: Dict[str, Any] = {
            "model": self.config.name,
            "messages": messages,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "api_key": self.api_key,
        }

        if self.api_base:
            call_kwargs["api_base"] = self.api_base

        if self.config.reasoning_effort:
            call_kwargs["reasoning_effort"] = self.config.reasoning_effort

        if self._supports_json_schema:
            call_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": _SUMMARY_JSON_SCHEMA,
                "strict": True,
            }
        elif self._supports_response_format:
            call_kwargs["response_format"] = {"type": "json_object"}

        try:
            response = litellm.completion(**call_kwargs)
        except Exception as exc:  # noqa: BLE001
            raise SummaryGenerationError(f"LLM request failed: {exc}") from exc

        raw_output = _extract_content(response)
        if not raw_output:
            raise SummaryGenerationError("LLM returned empty response")

        payload = _parse_json_payload(raw_output)
        return _format_sections(payload, fallback_text=raw_output, config=self.config, language=language)


@dataclass(slots=True)
class _StubLLMClient:
    """Tiny deterministic stand-in for a real LLM client."""

    config: LLMConfig
    allow_latex: bool = False
    api_key: str = field(init=False, repr=False)

    def summarise(self, source: SummarySource, *, language: str, context: str | None = None) -> dict[str, str]:
        abstract = source.abstract.strip()
        if not abstract:
            abstract = "No abstract provided."
        base_text = context.strip() if context else abstract
        highlights = _first_sentences(base_text or abstract, limit=2)
        bullets = "\n".join(f"- {item}" for item in highlights)
        body = (
            f"This summary was generated by {self.config.name} (alias {self.config.alias}).\n"
            f"Detected language: {language}.\n\n"
            f"Key observations:\n{bullets}\n\n"
            f"Full abstract:\n{abstract}"
        )
        if context:
            body += "\n\nContext excerpt:\n" + context[:2000]
        summary_body = body
        if not self.allow_latex:
            summary_body = summary_body.replace("$", "")
        return {
            "Highlights": "\n".join(highlights) or "No highlights available.",
            "Detailed Summary": summary_body,
        }

    def __post_init__(self) -> None:
        self.api_key = self.config.api_key_secret


def _parse_json_payload(raw_output: str) -> Dict[str, Any]:
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON payload from LLM output, falling back to raw text")
        return {}


def _extract_content(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, dict):
        choices = response.get("choices")
    if not choices:
        return ""

    choice = choices[0]
    message = getattr(choice, "message", None)
    if message is None and isinstance(choice, dict):
        message = choice.get("message")
    if message is None:
        return ""

    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")

    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [str(part).strip() for part in content if str(part).strip()]
        return "\n".join(parts).strip()
    if content is None:
        return ""
    return str(content).strip()


def _format_sections(payload: Dict[str, Any], *, fallback_text: str, config: LLMConfig, language: str) -> dict[str, str]:
    highlights = payload.get("highlights")
    detailed = payload.get("summary") or payload.get("detailed_summary")

    lines: list[str] = []
    if isinstance(highlights, list):
        lines = [str(item).strip() for item in highlights if str(item).strip()]
    elif isinstance(highlights, str) and highlights.strip():
        lines = [part.strip() for part in highlights.split("\n") if part.strip()]

    if not detailed and payload:
        for candidate in ("full_summary", "content", "text"):
            value = payload.get(candidate)
            if isinstance(value, str) and value.strip():
                detailed = value
                break

    if not lines:
        lines = _first_sentences(fallback_text, limit=3)

    if not detailed:
        logger.debug("LLM payload missing detailed summary, using fallback")
        detailed = fallback_text

    bullet_block = "\n".join(lines) if lines else "No highlights available."
    header = (
        f"This summary was generated by {config.name} (alias {config.alias}).\n"
        f"Detected language: {language}.\n"
    )
    detailed_block = f"{header}\n{detailed.strip()}".strip()
    return {
        "Highlights": bullet_block,
        "Detailed Summary": detailed_block,
    }


def _first_sentences(text: str, *, limit: int) -> list[str]:
    sentences: list[str] = []
    for chunk in text.replace("\n", " ").split("."):
        cleaned = chunk.strip()
        if cleaned:
            sentences.append(cleaned + ".")
        if len(sentences) >= limit:
            break
    return sentences


__all__ = ["SummaryGenerator", "SummaryGenerationError"]
