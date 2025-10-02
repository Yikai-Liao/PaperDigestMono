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

        [llm]
        model = "test-model"
        """.strip(),
        encoding="utf-8",
    )

    cfg = load_config(SummaryPipelineConfig, config_file)

    assert cfg.pdf.output_dir == "./pdfs"
    assert cfg.pdf.delay == 3
    assert cfg.pdf.max_retry == 3
    assert cfg.pdf.fetch_latex_source is False
    assert cfg.llm.model == "test-model"
    assert cfg.llm.language == "en"
    assert cfg.llm.enable_latex is False


def test_summary_pipeline_config_full(tmp_path: Path) -> None:
    """Test loading a fully specified summary pipeline config."""
    config_file = tmp_path / "summary.toml"
    config_file.write_text(
        """
        [pdf]
        output_dir = "./documents"
        delay = 5
        max_retry = 5
        fetch_latex_source = true

        [llm]
        model = "deepseek-v3"
        language = "zh"
        enable_latex = true
        """.strip(),
        encoding="utf-8",
    )

    cfg = load_config(SummaryPipelineConfig, config_file)

    assert cfg.pdf.output_dir == "./documents"
    assert cfg.pdf.delay == 5
    assert cfg.pdf.max_retry == 5
    assert cfg.pdf.fetch_latex_source is True
    assert cfg.llm.model == "deepseek-v3"
    assert cfg.llm.language == "zh"
    assert cfg.llm.enable_latex is True


def test_summary_pipeline_rejects_extra_fields(tmp_path: Path) -> None:
    """Ensure extra fields are rejected in summary config."""
    config_file = tmp_path / "summary.toml"
    config_file.write_text(
        """
        [pdf]
        output_dir = "./pdfs"
        extra_field = "should fail"

        [llm]
        model = "test"
        """.strip(),
        encoding="utf-8",
    )

    with pytest.raises(Exception):  # Pydantic ValidationError
        load_config(SummaryPipelineConfig, config_file)
