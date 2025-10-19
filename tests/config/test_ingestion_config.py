"""Unit tests for ingestion configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from papersys.config import AppConfig, IngestionConfig, load_config


def test_ingestion_config_minimal(tmp_path: Path) -> None:
    """Test loading minimal ingestion configuration."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
        data_root = "./data"

        [ingestion]
        enabled = true
        output_dir = "metadata/raw"
        """,
        encoding="utf-8",
    )

    app_config = load_config(AppConfig, config_path)
    assert app_config.ingestion is not None
    assert app_config.ingestion.enabled is True
    assert app_config.ingestion.output_dir == "metadata/raw"
    assert app_config.ingestion.batch_size == 1000  # default
    assert app_config.ingestion.categories == []  # default empty
def test_ingestion_config_full(tmp_path: Path) -> None:
    """Test loading full ingestion configuration with all fields."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
        [ingestion]
        enabled = true
        output_dir = "test/raw"
        start_date = "2024-01-01"
        end_date = "2024-12-31"
        batch_size = 500
        max_retries = 5
        retry_delay = 10.0
        oai_base_url = "https://custom.oai.endpoint"
        metadata_prefix = "CustomFormat"
        categories = ["cs.AI", "cs.LG"]
        save_raw_responses = true
        """,
        encoding="utf-8",
    )

    app_config = load_config(AppConfig, config_path)
    ing = app_config.ingestion
    assert ing is not None
    assert ing.enabled is True
    assert ing.output_dir == "test/raw"
    assert ing.start_date == "2024-01-01"
    assert ing.end_date == "2024-12-31"
    assert ing.batch_size == 500
    assert ing.max_retries == 5
    assert ing.retry_delay == 10.0
    assert ing.oai_base_url == "https://custom.oai.endpoint"
    assert ing.categories == ["cs.AI", "cs.LG"]
    assert ing.save_raw_responses is True


def test_ingestion_config_no_section(tmp_path: Path) -> None:
    """Test that missing ingestion section results in None."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
        data_root = "./data"
        """,
        encoding="utf-8",
    )

    app_config = load_config(AppConfig, config_path)
    assert app_config.ingestion is None


def test_ingestion_config_rejects_extra_fields(tmp_path: Path) -> None:
    """Test that extra fields are rejected (strict validation)."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
        [ingestion]
        enabled = true
        output_dir = "metadata/raw"
        curated_dir = "metadata/curated"
        unknown_field = "should fail"
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        load_config(AppConfig, config_path)
