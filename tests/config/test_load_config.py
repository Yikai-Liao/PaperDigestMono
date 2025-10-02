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
    """Test loading the complete example.toml with all pipeline configs."""
    config_path = Path(__file__).resolve().parents[2] / "config" / "example.toml"
    cfg = load_config(AppConfig, config_path)

    # Legacy/general fields
    assert cfg.data_root == Path("./data")
    assert cfg.scheduler_enabled is True
    assert cfg.logging_level == "INFO"

    # Recommendation pipeline
    assert cfg.recommend_pipeline is not None
    assert cfg.recommend_pipeline.data.cache_dir == "./cache"
    assert cfg.recommend_pipeline.data.embedding_columns == ["jasper_v1", "conan_v1"]
    assert cfg.recommend_pipeline.trainer.seed == 42
    assert cfg.recommend_pipeline.trainer.logistic_regression.C == 1.0
    assert cfg.recommend_pipeline.predict.last_n_days == 7
    assert cfg.recommend_pipeline.predict.high_threshold == 0.85

    # Summary pipeline
    assert cfg.summary_pipeline is not None
    assert cfg.summary_pipeline.pdf.output_dir == "./pdfs"
    assert cfg.summary_pipeline.pdf.model == "deepseek-r1"
    assert cfg.summary_pipeline.pdf.language == "zh"

    # Backup configuration
    assert cfg.backup is not None
    assert cfg.backup.enabled is True
    assert cfg.backup.sources == [Path("./config"), Path("./devlog"), Path("./papersys")]
    assert cfg.backup.destination.storage == "local"
    assert cfg.backup.destination.path == Path("./backups")
    assert cfg.backup.retention == 5

    # Scheduler configuration
    assert cfg.scheduler is not None
    assert cfg.scheduler.enabled is True
    assert cfg.scheduler.timezone == "Asia/Shanghai"
    assert cfg.scheduler.recommend_job is not None
    assert cfg.scheduler.recommend_job.name == "recommendation-pipeline"
    assert cfg.scheduler.recommend_job.cron == "0 5 * * *"
    assert cfg.scheduler.summary_job is not None
    assert cfg.scheduler.summary_job.cron == "0 6 * * *"
    assert cfg.scheduler.backup_job is not None
    assert cfg.scheduler.backup_job.cron == "30 3 * * *"
    assert cfg.scheduler.backup_job.name == "nightly-backup"

    # LLM configurations
    assert len(cfg.llms) == 2
    deepseek = next((llm for llm in cfg.llms if llm.alias == "deepseek-r1"), None)
    assert deepseek is not None
    assert deepseek.name == "deepseek-reasoner"
    assert deepseek.num_workers == 10