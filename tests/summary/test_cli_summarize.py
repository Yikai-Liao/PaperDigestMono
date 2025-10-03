from __future__ import annotations

import textwrap
import json
from pathlib import Path

import polars as pl

from papersys.cli import main


def _write_config(path: Path, data_root: Path) -> None:
    content = textwrap.dedent(
        f"""
        data_root = "{data_root.as_posix()}"
        scheduler_enabled = false
        embedding_models = []
        logging_level = "INFO"

    [summary_pipeline.pdf]
    output_dir = "summary-output"
    delay = 0
    max_retry = 1
    fetch_latex_source = false

    [summary_pipeline.llm]
    model = "demo-llm"
    language = "en"
    enable_latex = false

        [[llms]]
        alias = "demo-llm"
        name = "StubModel"
        base_url = "http://localhost"
        api_key = "dummy"
        temperature = 0.2
        top_p = 0.9
        num_workers = 1
        """
    ).strip()
    path.write_text(content, encoding="utf-8")


def test_cli_summarize_dry_run(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _write_config(config_path, data_root)

    exit_code = main(["--config", str(config_path), "summarize", "--dry-run"])

    assert exit_code == 0
    pdf_dir = data_root / "summary-output"
    markdown_dir = pdf_dir / "markdown"
    assert pdf_dir.exists()
    assert markdown_dir.exists()


def test_cli_summarize_generates_outputs(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _write_config(config_path, data_root)

    recommend_dir = data_root / "recommendations" / "20251004-000000"
    recommend_dir.mkdir(parents=True, exist_ok=True)
    recommended_path = recommend_dir / "recommended.parquet"
    pl.DataFrame(
        {
            "id": ["2504.00004"],
            "title": ["A Synthetic Summary"],
            "abstract": ["Test abstract"],
            "score": [0.87],
        }
    ).write_parquet(recommended_path)

    exit_code = main([
        "--config",
        str(config_path),
        "summarize",
        "--input",
        str(recommended_path),
        "--limit",
        "1",
    ])

    assert exit_code == 0

    summaries_root = data_root / "summaries"
    jsonl_files = list(summaries_root.glob("*.jsonl"))
    manifest_files = list(summaries_root.glob("manifest-*.json"))
    assert jsonl_files
    assert manifest_files

    record = json.loads(jsonl_files[0].read_text(encoding="utf-8").strip().splitlines()[-1])
    assert record["id"] == "2504.00004"

    manifest = json.loads(manifest_files[0].read_text(encoding="utf-8"))
    assert manifest["summarized"] == 1
