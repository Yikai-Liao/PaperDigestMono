"""Unit tests for summary pipeline configuration models."""

from __future__ import annotations

from pathlib import Path

import pytest

from papersys.config import SummaryPipelineConfig, load_config


def test_summary_pipeline_config_minimal(tmp_path: Path) -> None:
    """Test loading a minimal summary pipeline config with defaults."""
    config_file = tmp_path / "summary.toml"
    config_file.write_text(
        """
        [pdf]
        model = "test-model"
        """.strip(),
        encoding="utf-8",
    )

    cfg = load_config(SummaryPipelineConfig, config_file)

    assert cfg.pdf.model == "test-model"
    assert cfg.pdf.output_dir == "./pdfs"
    assert cfg.pdf.delay == 3
    assert cfg.pdf.max_retry == 3
    assert cfg.pdf.language == "en"
    assert cfg.pdf.enable_latex is False
    assert len(cfg.pdf.acceptable_cache_model) > 0  # Default patterns


def test_summary_pipeline_config_full(tmp_path: Path) -> None:
    """Test loading a fully specified summary pipeline config."""
    config_file = tmp_path / "summary.toml"
    config_file.write_text(
        """
        [pdf]
        output_dir = "./documents"
        delay = 5
        max_retry = 5
        model = "deepseek-v3"
        language = "zh"
        enable_latex = true
        acceptable_cache_model = ["model-a*", "model-b*"]
        """.strip(),
        encoding="utf-8",
    )

    cfg = load_config(SummaryPipelineConfig, config_file)

    assert cfg.pdf.output_dir == "./documents"
    assert cfg.pdf.delay == 5
    assert cfg.pdf.max_retry == 5
    assert cfg.pdf.model == "deepseek-v3"
    assert cfg.pdf.language == "zh"
    assert cfg.pdf.enable_latex is True
    assert cfg.pdf.acceptable_cache_model == ["model-a*", "model-b*"]


def test_summary_pipeline_rejects_extra_fields(tmp_path: Path) -> None:
    """Ensure extra fields are rejected in summary config."""
    config_file = tmp_path / "summary.toml"
    config_file.write_text(
        """
        [pdf]
        model = "test"
        extra_field = "should fail"
        """.strip(),
        encoding="utf-8",
    )

    with pytest.raises(Exception):  # Pydantic ValidationError
        load_config(SummaryPipelineConfig, config_file)
