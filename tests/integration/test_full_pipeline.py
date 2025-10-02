from __future__ import annotations

from pathlib import Path
from typing import Iterable, cast

import polars as pl

from papersys.config.app import AppConfig
from papersys.config.llm import LLMConfig
from papersys.config.recommend import DataConfig, PredictConfig, RecommendPipelineConfig
from papersys.config.summary import PdfFetchConfig, SummaryLLMConfig, SummaryPipelineConfig
from papersys.recommend.pipeline import RecommendationPipeline
from papersys.summary.models import SummarySource
from papersys.summary.pipeline import SummaryPipeline


def _build_app_config(base_dir: Path) -> AppConfig:
    preference_dir = base_dir / "preferences"
    metadata_dir = base_dir / "metadata"
    embeddings_root = base_dir / "embeddings"
    output_dir = base_dir / "recommend-output"
    pdf_dir = base_dir / "summary-output"

    preference_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    data_cfg = DataConfig(
        embedding_columns=["jasper_v1", "conan_v1"],
        preference_dir=str(preference_dir),
        metadata_dir=str(metadata_dir),
        metadata_pattern="metadata-*.csv",
        embeddings_root=str(embeddings_root),
        categories=["cs.AI"],
        background_start_year=2024,
        preference_start_year=2024,
        embed_repo_id="local/test-embeddings",
        content_repo_id="local/test-content",
    )
    predict_cfg = PredictConfig(
        last_n_days=60,
        start_date="",
        end_date="",
        high_threshold=0.05,
        boundary_threshold=0.01,
        sample_rate=1.0,
        output_path=str(output_dir / "recommendations.jsonl"),
    )
    recommend_cfg = RecommendPipelineConfig(
        data=data_cfg,
        predict=predict_cfg,
    )

    summary_cfg = SummaryPipelineConfig(
        pdf=PdfFetchConfig(
            output_dir=str(pdf_dir),
            delay=0,
            max_retry=1,
            fetch_latex_source=False,
        ),
        llm=SummaryLLMConfig(
            model="demo-llm",
            language="en",
            enable_latex=False,
        ),
    )

    llm_cfg = LLMConfig(
        alias="demo-llm",
        name="StubModel",
        base_url="http://localhost",
        api_key="dummy",
        temperature=0.1,
        top_p=0.9,
        num_workers=1,
        reasoning_effort=None,
    )

    return AppConfig(
        data_root=base_dir,
        scheduler_enabled=False,
        embedding_models=[],
        logging_level="INFO",
        ingestion=None,
        embedding=None,
        scheduler=None,
        backup=None,
        recommend_pipeline=recommend_cfg,
        summary_pipeline=summary_cfg,
        llms=[llm_cfg],
    )


def _write_preference_dataset(base_dir: Path, ids: Iterable[str]) -> None:
    ids_list = list(ids)
    preference_dir = base_dir / "preferences"
    payload = pl.DataFrame(
        {
            "id": ids_list,
            "preference": ["like"] * len(ids_list),
        }
    )
    payload.write_csv(preference_dir / "events.csv", include_header=True)


def _seed_workspace_data(base_dir: Path) -> list[str]:
    metadata_dir = base_dir / "metadata"
    embeddings_root = base_dir / "embeddings"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    embeddings_root.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "id": "paper-0001",
            "title": "Few-Shot Summaries with Structured Prompts",
            "abstract": "We study lightweight pipelines for reliable academic summarisation.",
            "categories": ["cs.AI"],
            "updated": "2025-09-15",
            "jasper_v1": [0.25, 0.75, 0.5],
            "conan_v1": [0.1, 0.4, 0.3],
        },
        {
            "id": "paper-0002",
            "title": "Graph Distillation for Scientific Papers",
            "abstract": "A graph-based distillation approach improves recommendation relevance.",
            "categories": ["cs.AI"],
            "updated": "2025-09-18",
            "jasper_v1": [0.2, 0.3, 0.7],
            "conan_v1": [0.6, 0.2, 0.5],
        },
        {
            "id": "paper-0003",
            "title": "Interactive Retrieval-Augmented Generation",
            "abstract": "Interactive RAG techniques align user preference feedback with ranking models.",
            "categories": ["cs.AI"],
            "updated": "2025-09-20",
            "jasper_v1": [0.3, 0.4, 0.8],
            "conan_v1": [0.3, 0.6, 0.2],
        },
    ]
    metadata_rows = []
    for row in rows:
        categories = cast(list[str], row["categories"])
        metadata_rows.append(
            {
                "paper_id": row["id"],
                "title": row["title"],
                "abstract": row["abstract"],
                "categories": ";".join(categories),
                "updated_at": row["updated"],
            }
        )
    pl.DataFrame(metadata_rows).write_csv(metadata_dir / "metadata-2025.csv", include_header=True)

    for alias in ("jasper_v1", "conan_v1"):
        alias_dir = embeddings_root / alias
        alias_dir.mkdir(parents=True, exist_ok=True)
        vectors = [
            {
                "paper_id": row["id"],
                "embedding": [float(value) for value in row[alias]],
                "generated_at": "2025-09-01T00:00:00+00:00",
                "model_dim": len(row[alias]),
                "source": "integration-test",
            }
            for row in rows
        ]
        pl.DataFrame(
            {
                "paper_id": [item["paper_id"] for item in vectors],
                "embedding": [item["embedding"] for item in vectors],
                "generated_at": [item["generated_at"] for item in vectors],
                "model_dim": [item["model_dim"] for item in vectors],
                "source": [item["source"] for item in vectors],
            }
        ).write_parquet(alias_dir / "2025.parquet")
    return [str(row["id"]) for row in rows]


def test_full_pipeline_generates_summaries_without_mutating_workspace(tmp_path: Path) -> None:
    config = _build_app_config(tmp_path)
    candidate_ids = _seed_workspace_data(tmp_path)
    _write_preference_dataset(tmp_path, candidate_ids[:1])

    assert config.recommend_pipeline is not None
    assert config.summary_pipeline is not None

    recommendation_pipeline = RecommendationPipeline(config, base_path=tmp_path)
    artifacts = recommendation_pipeline.run(force_include_all=True)

    assert artifacts.dataset.preferred.height == 1
    assert artifacts.dataset.background.height >= 1
    assert artifacts.result.recommended.height >= 1

    language = config.summary_pipeline.llm.language
    sources: list[SummarySource] = []
    for row in artifacts.result.recommended.iter_rows(named=True):
        sources.append(
            SummarySource(
                paper_id=row["id"],
                title=row["title"],
                abstract=row["abstract"],
                language=language,
            )
        )

    summary_pipeline = SummaryPipeline(config, base_path=tmp_path)
    outputs = summary_pipeline.run(sources)

    assert len(outputs) == len(sources)
    for artifact in outputs:
        assert artifact.pdf_path.exists()
        assert artifact.pdf_path.parent == tmp_path / "summary-output"
        assert artifact.markdown_path.exists()
        assert artifact.markdown_path.parent == (tmp_path / "summary-output" / "markdown")
        rendered = artifact.markdown_path.read_text(encoding="utf-8")
        assert artifact.source.title in rendered
        assert "Highlights" in rendered