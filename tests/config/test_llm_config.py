"""Unit tests for LLM configuration models."""

from __future__ import annotations

from pathlib import Path

import pytest

from papersys.config import LLMConfig, load_config


def test_llm_config_basic(tmp_path: Path) -> None:
    """Test loading a single LLM configuration."""
    config_file = tmp_path / "llm.toml"
    config_file.write_text(
        """
        alias = "test-model"
        name = "test-model-v1"
        base_url = "https://api.example.com"
        api_key = "test-key-123"
        temperature = 0.5
        top_p = 0.9
        num_workers = 4
        native_json_schema = true
        """.strip(),
        encoding="utf-8",
    )

    cfg = load_config(LLMConfig, config_file)

    assert cfg.alias == "test-model"
    assert cfg.name == "test-model-v1"
    assert cfg.base_url == "https://api.example.com"
    assert cfg.api_key == "test-key-123"
    assert cfg.temperature == 0.5
    assert cfg.top_p == 0.9
    assert cfg.num_workers == 4
    assert cfg.native_json_schema is True
    assert cfg.reasoning_effort is None


def test_llm_config_with_reasoning_effort(tmp_path: Path) -> None:
    """Test LLM config with optional reasoning_effort field."""
    config_file = tmp_path / "llm.toml"
    config_file.write_text(
        """
        alias = "reasoner"
        name = "reasoner-v1"
        base_url = "https://api.example.com"
        api_key = "env:MY_API_KEY"
        temperature = 0.1
        top_p = 0.8
        num_workers = 2
        reasoning_effort = "high"
        native_json_schema = false
        """.strip(),
        encoding="utf-8",
    )

    cfg = load_config(LLMConfig, config_file)

    assert cfg.reasoning_effort == "high"
    assert cfg.native_json_schema is False


def test_llm_config_rejects_extra_fields(tmp_path: Path) -> None:
    """Ensure extra fields are rejected due to strict validation."""
    config_file = tmp_path / "llm.toml"
    config_file.write_text(
        """
        alias = "test"
        name = "test"
        base_url = "https://api.example.com"
        api_key = "key"
        temperature = 0.1
        top_p = 0.8
        num_workers = 1
        unknown_field = "should fail"
        """.strip(),
        encoding="utf-8",
    )

    with pytest.raises(Exception):  # Pydantic ValidationError
        load_config(LLMConfig, config_file)
