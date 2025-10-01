from __future__ import annotations

import textwrap
from pathlib import Path

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
        model = "demo-llm"
        language = "en"
        delay = 0
        max_retry = 1
        enable_latex = false

        [[llms]]
        alias = "demo-llm"
        name = "StubModel"
        base_url = "http://localhost"
        api_key = "dummy"
        temperature = 0.2
        top_p = 0.9
        num_workers = 1
        native_json_schema = true
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
