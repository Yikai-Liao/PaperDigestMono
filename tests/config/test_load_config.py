from __future__ import annotations

from pathlib import Path

import pytest

from papersys.config import AppConfig, BaseConfig, load_config


class ExampleConfig(BaseConfig):
    data_root: Path
    feature_enabled: bool


def test_load_config_success(tmp_path: Path) -> None:
    sample = tmp_path / "config.toml"
    sample.write_text(
        """
        data_root = "./cache"
        feature_enabled = true
        """.strip(),
        encoding="utf-8",
    )

    cfg = load_config(ExampleConfig, sample)

    assert cfg.data_root == Path("./cache")
    assert cfg.feature_enabled is True


def test_load_config_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.toml"
    with pytest.raises(FileNotFoundError):
        load_config(ExampleConfig, missing)


def test_app_config_example_file() -> None:
    config_path = Path(__file__).resolve().parents[2] / "config" / "example.toml"
    cfg = load_config(AppConfig, config_path)

    assert cfg.data_root == Path("./data")
    assert cfg.scheduler_enabled is True
    assert cfg.logging_level == "INFO"
