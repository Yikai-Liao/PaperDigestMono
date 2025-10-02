from __future__ import annotations

import json
from typing import Any, cast

import pytest

from papersys.config.llm import LLMConfig
from papersys.summary.generator import SummarySource


@pytest.fixture()
def llm_config() -> LLMConfig:
    return LLMConfig(
        alias="demo",
        name="gpt-4o-mini",
        base_url="https://api.openai.com",
        api_key="dummy",
        temperature=0.1,
        top_p=0.8,
        num_workers=1,
        reasoning_effort=None,
    )


def _fake_source() -> SummarySource:
    return SummarySource(
        paper_id="test-1234",
        title="Test Driven Summaries",
        abstract="We propose a test harness for JSON-mode detection.",
    )


def test_litellm_client_uses_json_schema(monkeypatch: pytest.MonkeyPatch, llm_config: LLMConfig) -> None:
    from papersys.summary import generator

    captured: dict[str, Any] = {}

    def fake_supports_response_schema(*, model: str, custom_llm_provider: str | None) -> bool:
        captured["schema_probe"] = (model, custom_llm_provider)
        return True

    def fake_get_supported_params(*, model: str, custom_llm_provider: str | None):
        captured["params_probe"] = (model, custom_llm_provider)
        return {"response_format"}

    def fake_completion(**kwargs):
        captured["completion_kwargs"] = kwargs
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"highlights": ["OK"], "summary": "done"})
                    }
                }
            ]
        }

    monkeypatch.setattr(generator, "_SUPPORTS_RESPONSE_SCHEMA", fake_supports_response_schema, raising=False)
    monkeypatch.setattr(generator, "_GET_SUPPORTED_OPENAI_PARAMS", fake_get_supported_params, raising=False)
    monkeypatch.setattr(generator.litellm, "completion", fake_completion)

    client = generator._LiteLLMClient(llm_config, api_base=llm_config.base_url)
    sections = client.summarise(_fake_source(), language="en")

    assert sections["Highlights"] == "OK"
    assert "completion_kwargs" in captured
    completion_kwargs = cast(dict[str, Any], captured["completion_kwargs"])
    response_format = cast(dict[str, Any], completion_kwargs["response_format"])
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "paper_summary"


def test_litellm_client_falls_back_to_json_object(monkeypatch: pytest.MonkeyPatch, llm_config: LLMConfig) -> None:
    from papersys.summary import generator

    captured: dict[str, Any] = {}

    def fake_supports_response_schema(*, model: str, custom_llm_provider: str | None) -> bool:
        captured["schema_probe"] = (model, custom_llm_provider)
        return False

    def fake_get_supported_params(*, model: str, custom_llm_provider: str | None):
        captured["params_probe"] = (model, custom_llm_provider)
        return ["response_format", "temperature"]

    def fake_completion(**kwargs):
        captured["completion_kwargs"] = kwargs
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"highlights": ["OK"], "summary": "done"})
                    }
                }
            ]
        }

    monkeypatch.setattr(generator, "_SUPPORTS_RESPONSE_SCHEMA", fake_supports_response_schema, raising=False)
    monkeypatch.setattr(generator, "_GET_SUPPORTED_OPENAI_PARAMS", fake_get_supported_params, raising=False)
    monkeypatch.setattr(generator.litellm, "completion", fake_completion)

    client = generator._LiteLLMClient(llm_config, api_base=llm_config.base_url)
    sections = client.summarise(_fake_source(), language="en")

    assert sections["Highlights"] == "OK"
    completion_kwargs = cast(dict[str, Any], captured["completion_kwargs"])
    assert completion_kwargs["response_format"] == {"type": "json_object"}


def test_litellm_client_handles_missing_response_format(monkeypatch: pytest.MonkeyPatch, llm_config: LLMConfig) -> None:
    from papersys.summary import generator

    captured: dict[str, Any] = {}

    def fake_supports_response_schema(*, model: str, custom_llm_provider: str | None) -> bool:
        captured["schema_probe"] = (model, custom_llm_provider)
        return False

    def fake_get_supported_params(*, model: str, custom_llm_provider: str | None):
        captured["params_probe"] = (model, custom_llm_provider)
        return []

    def fake_completion(**kwargs):
        captured["completion_kwargs"] = kwargs
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"highlights": ["OK"], "summary": "done"})
                    }
                }
            ]
        }

    monkeypatch.setattr(generator, "_SUPPORTS_RESPONSE_SCHEMA", fake_supports_response_schema, raising=False)
    monkeypatch.setattr(generator, "_GET_SUPPORTED_OPENAI_PARAMS", fake_get_supported_params, raising=False)
    monkeypatch.setattr(generator.litellm, "completion", fake_completion)

    client = generator._LiteLLMClient(llm_config, api_base=llm_config.base_url)
    sections = client.summarise(_fake_source(), language="en")

    assert sections["Highlights"] == "OK"
    completion_kwargs = cast(dict[str, Any], captured["completion_kwargs"])
    assert "response_format" not in completion_kwargs


def test_litellm_client_sets_google_ai_studio_provider(monkeypatch: pytest.MonkeyPatch, llm_config: LLMConfig) -> None:
    from papersys.summary import generator

    captured: dict[str, Any] = {}

    def fake_completion(**kwargs):
        captured["completion_kwargs"] = kwargs
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"highlights": ["OK"], "summary": "done"})
                    }
                }
            ]
        }

    monkeypatch.setattr(generator.litellm, "completion", fake_completion)

    config = llm_config.model_copy(
        update={
            "name": "gemini/gemini-2.5-flash",
            "base_url": "",  # LiteLLM auto-routes via model prefix
            "reasoning_effort": "low",
        }
    )

    client = generator._LiteLLMClient(config, api_base=config.base_url)
    sections = client.summarise(_fake_source(), language="en")

    assert sections["Highlights"] == "OK"
    completion_kwargs = cast(dict[str, Any], captured["completion_kwargs"])
    # Should NOT have custom_llm_provider or api_base since LiteLLM handles routing
    assert "custom_llm_provider" not in completion_kwargs
    assert "api_base" not in completion_kwargs
    assert completion_kwargs["reasoning_effort"] == "low"
