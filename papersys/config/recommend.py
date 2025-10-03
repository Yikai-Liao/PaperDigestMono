"""Recommendation pipeline configuration models."""

from __future__ import annotations

from pydantic import Field

from papersys.config.base import BaseConfig


class LogisticRegressionConfig(BaseConfig):
    """Logistic regression hyperparameters."""

    C: float = Field(1.0, gt=0.0, description="Inverse of regularization strength")
    max_iter: int = Field(1000, ge=1, description="Maximum iteration count")


class TrainerConfig(BaseConfig):
    """Configuration for recommendation model training."""

    seed: int = Field(42, description="Random seed for reproducibility")
    bg_sample_rate: float = Field(5.0, gt=0.0, description="Background sampling rate")
    logistic_regression: LogisticRegressionConfig = Field(
        default_factory=lambda: LogisticRegressionConfig(),
        description="Logistic regression parameters",
    )


class DataConfig(BaseConfig):
    """Configuration for recommendation data sources."""

    categories: list[str] = Field(
        default_factory=lambda: ["cs.CL", "cs.CV", "cs.AI", "cs.LG", "stat.ML", "cs.IR", "cs.CY"],
        description="Arxiv paper categories to consider",
    )
    embedding_columns: list[str] = Field(..., description="Embedding column names")
    preference_dir: str = Field("./preferences", description="Directory containing preference data")
    metadata_dir: str = Field("./metadata", description="Directory containing metadata CSV files")
    metadata_pattern: str = Field(
        "metadata-*.csv",
        description="Glob pattern (relative to metadata_dir) to select metadata CSV files",
    )
    embeddings_root: str = Field(
        "./embeddings",
        description="Root directory that stores per-model embedding parquet files",
    )
    background_start_year: int = Field(2024, ge=2000, description="Start year for background corpus")
    preference_start_year: int = Field(2023, ge=2000, description="Start year for preference data")


class PredictConfig(BaseConfig):
    """Configuration for recommendation prediction parameters."""

    last_n_days: int = Field(7, ge=1, description="Number of recent days to predict")
    start_date: str = Field("", description="Prediction start date (YYYY-MM-DD), empty uses last_n_days")
    end_date: str = Field("", description="Prediction end date (YYYY-MM-DD), empty uses last_n_days")
    high_threshold: float = Field(0.85, ge=0.0, le=1.0, description="High-confidence threshold")
    boundary_threshold: float = Field(0.6, ge=0.0, le=1.0, description="Boundary threshold")
    sample_rate: float = Field(0.001, gt=0.0, le=1.0, description="Sampling rate for predictions")
    output_dir: str = Field(
        "./recommendations",
        description="Directory for recommendation pipeline outputs (relative to data root if not absolute)",
    )
    output_path: str = Field(
        "predictions.parquet",
        description="Filename (or absolute path) for scored prediction output",
    )
    recommended_path: str = Field(
        "recommended.parquet",
        description="Filename (or absolute path) for recommended subset",
    )
    manifest_path: str = Field(
        "manifest.json",
        description="Filename (or absolute path) for recommendation manifest metadata",
    )


class RecommendPipelineConfig(BaseConfig):
    """Complete recommendation pipeline configuration."""

    data: DataConfig
    trainer: TrainerConfig = Field(default_factory=lambda: TrainerConfig())
    predict: PredictConfig


__all__ = [
    "LogisticRegressionConfig",
    "TrainerConfig",
    "DataConfig",
    "PredictConfig",
    "RecommendPipelineConfig",
]
