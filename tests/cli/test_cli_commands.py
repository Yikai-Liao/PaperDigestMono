from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import polars as pl

from papersys.cli import main

from .utils import logger_to_stderr, make_app_config, patch_load_config


@pytest.fixture()
def config_path(tmp_path: Path) -> Path:
    config_file = tmp_path / "config.toml"
    config_file.write_text("placeholder = true")
    return config_file


def test_main_without_command_warns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: Any,
    config_path: Path,
) -> None:
    config = make_app_config(tmp_path)
    patch_load_config(monkeypatch, config)

    with logger_to_stderr():
        exit_code = main(["--config", str(config_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "No command provided" in captured.err


def test_summarize_dry_run_executes_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_path: Path,
) -> None:
    config = make_app_config(tmp_path)
    patch_load_config(monkeypatch, config)

    calls: dict[str, Any] = {}

    class DummyPipeline:
        def __init__(self, cfg: Any, base_path: Path | None = None) -> None:
            calls["base_path"] = base_path

        def describe_sources(self) -> None:
            calls["describe"] = True

        def load_sources_from_recommendations(self, *_: Any, **__: Any) -> list[Any]:  # pragma: no cover
            raise AssertionError("load_sources_from_recommendations should not be called in dry-run")

        def run(self, sources: list[Any], dry_run: bool = False, run_id: str | None = None) -> list[Any]:
            calls["run"] = dry_run
            calls["run_id"] = run_id
            return []

        def run_and_save(self, *_: Any, **__: Any) -> Any:  # pragma: no cover
            raise AssertionError("run_and_save should not be called in dry-run")

    monkeypatch.setattr("papersys.cli.SummaryPipeline", DummyPipeline)

    exit_code = main(["--config", str(config_path), "summarize", "--dry-run"])

    assert exit_code == 0
    assert calls["base_path"] is not None
    assert calls["run"] is True
    assert calls["describe"] is True


def test_summarize_runs_with_input(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_path: Path,
) -> None:
    config = make_app_config(tmp_path)
    patch_load_config(monkeypatch, config)

    calls: dict[str, Any] = {}

    class DummyPipeline:
        def __init__(self, cfg: Any, base_path: Path | None = None) -> None:
            calls["base_path"] = base_path

        def describe_sources(self) -> None:
            calls["describe"] = True

        def load_sources_from_recommendations(self, path: Path, limit: int | None = None) -> list[Any]:
            calls["load"] = {"path": path, "limit": limit}
            return ["source"]

        def run_and_save(self, sources: list[Any], limit: int | None = None) -> Any:
            calls["run_and_save"] = {"sources": sources, "limit": limit}
            return SimpleNamespace(
                artifacts=[],
                jsonl_path=tmp_path / "data" / "summaries" / "2025-10.jsonl",
                manifest_path=tmp_path / "data" / "summaries" / "manifest-123.json",
                markdown_dir=tmp_path / "data" / "summary-output" / "markdown" / "123",
            )

    monkeypatch.setattr("papersys.cli.SummaryPipeline", DummyPipeline)

    input_path = tmp_path / "data" / "recommendations" / "run" / "recommended.parquet"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text("placeholder", encoding="utf-8")

    exit_code = main([
        "--config",
        str(config_path),
        "summarize",
        "--input",
        str(input_path),
        "--limit",
        "5",
    ])

    assert exit_code == 0
    assert calls["describe"] is True
    assert calls["load"]["path"] == input_path
    assert calls["load"]["limit"] == 5
    assert calls["run_and_save"]["sources"] == ["source"]


def test_serve_dry_run_sets_up_scheduler(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_path: Path,
) -> None:
    config = make_app_config(tmp_path)
    patch_load_config(monkeypatch, config)

    instances: list[Any] = []

    class DummyScheduler:
        def __init__(self, cfg: Any, dry_run: bool) -> None:
            self.dry_run = dry_run
            self.setup_called = False
            self.start_called = False
            instances.append(self)

        def setup_jobs(self) -> None:
            self.setup_called = True

        def start(self) -> None:
            self.start_called = True

        def shutdown(self) -> None:
            raise AssertionError("shutdown should not be called in dry-run")

    monkeypatch.setattr("papersys.cli.SchedulerService", DummyScheduler)

    def _unexpected_create_app(*_: Any) -> None:
        raise AssertionError("create_app should not run in dry-run mode")

    monkeypatch.setattr("papersys.cli.create_app", _unexpected_create_app)
    monkeypatch.setattr("papersys.cli.uvicorn", object())

    exit_code = main(["--config", str(config_path), "serve", "--dry-run"])

    assert exit_code == 0
    assert instances
    scheduler = instances[0]
    assert scheduler.dry_run is True
    assert scheduler.setup_called is True
    assert scheduler.start_called is False


def test_serve_runs_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_path: Path,
) -> None:
    config = make_app_config(tmp_path)
    patch_load_config(monkeypatch, config)

    class DummyScheduler:
        def __init__(self, cfg: Any, dry_run: bool) -> None:
            self.dry_run = dry_run

        def setup_jobs(self) -> None:
            return None

        def start(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

    class DummyApp:
        def on_event(self, _event: str):
            def decorator(func: Any) -> Any:
                return func

            return decorator

    run_args: dict[str, Any] = {}

    monkeypatch.setattr("papersys.cli.SchedulerService", DummyScheduler)
    monkeypatch.setattr("papersys.cli.create_app", lambda service: DummyApp())

    class _UvicornModule:
        @staticmethod
        def run(*args: Any, **kwargs: Any) -> None:
            run_args["args"] = args
            run_args["kwargs"] = kwargs

    monkeypatch.setattr("papersys.cli.uvicorn", _UvicornModule)

    exit_code = main(["--config", str(config_path), "serve", "--host", "0.0.0.0", "--port", "9000"])

    assert exit_code == 0
    assert run_args["kwargs"]["host"] == "0.0.0.0"
    assert run_args["kwargs"]["port"] == 9000


def test_ingest_runs_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_path: Path,
) -> None:
    config = make_app_config(tmp_path)
    patch_load_config(monkeypatch, config)

    instances: list[Any] = []

    class DummyIngestionService:
        def __init__(self, cfg: Any, base_path: Path | None = None) -> None:
            self.cfg = cfg
            self.base_path = base_path
            self.fetch_args: dict[str, Any] | None = None
            self.dedup_called = False
            instances.append(self)

        def fetch_and_save(self, **kwargs: Any) -> tuple[int, int]:
            self.fetch_args = kwargs
            return 5, 4

        def deduplicate_csv_files(self) -> int:
            self.dedup_called = True
            return 2

    monkeypatch.setattr("papersys.ingestion.IngestionService", DummyIngestionService)

    exit_code = main(
        [
            "--config",
            str(config_path),
            "ingest",
            "--from",
            "2024-01-01",
            "--to",
            "2024-01-02",
            "--limit",
            "10",
            "--deduplicate",
        ]
    )

    assert exit_code == 0
    assert instances
    service = instances[0]
    assert service.fetch_args == {
        "from_date": "2024-01-01",
        "until_date": "2024-01-02",
        "limit": 10,
    }
    assert service.dedup_called is True


def test_ingest_disabled_exits(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, config_path: Path, capsys: Any) -> None:
    config = make_app_config(tmp_path, include_ingestion=False)
    patch_load_config(monkeypatch, config)

    with logger_to_stderr():
        exit_code = main(["--config", str(config_path), "ingest"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Ingestion is not enabled" in captured.err


def test_embed_backlog_flow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_path: Path,
) -> None:
    config = make_app_config(tmp_path)
    patch_load_config(monkeypatch, config)

    backlog_calls: dict[str, Any] = {}
    instances: list[Any] = []

    class DummyEmbeddingService:
        def __init__(self, cfg: Any, base_path: Path | None = None) -> None:
            self.cfg = cfg
            self.base_path = base_path
            instances.append(self)

        def detect_backlog(self, metadata_dir: Path, model_cfg: Any) -> pl.DataFrame:
            backlog_calls["metadata_dir"] = metadata_dir
            backlog_calls["alias"] = getattr(model_cfg, "alias", "")
            path = metadata_dir / "backlog.csv"
            return pl.DataFrame({"origin": [str(path)]})

        def refresh_backlog(self, metadata_dir: Path, model_cfg: Any) -> pl.DataFrame:
            backlog_calls["refreshed"] = True
            return pl.DataFrame({"origin": []})

        def generate_embeddings_for_csv(
            self,
            csv_path: Path,
            model_cfg: Any,
            *,
            limit: int | None = None,
        ) -> tuple[int, Any]:
            backlog_calls.setdefault("processed", []).append((csv_path, limit))
            return 3, None

    monkeypatch.setattr("papersys.embedding.EmbeddingService", DummyEmbeddingService)

    assert config.ingestion is not None
    metadata_dir = Path(config.ingestion.output_dir)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    (metadata_dir / "backlog.csv").write_text("paper_id,title\n1,Example\n", encoding="utf-8")

    exit_code = main(["--config", str(config_path), "embed", "--backlog", "--limit", "5"])

    assert exit_code == 0
    assert backlog_calls["alias"] == "test"
    assert backlog_calls["processed"][0][1] == 5
    assert instances


def test_embed_full_generation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_path: Path,
) -> None:
    config = make_app_config(tmp_path)
    patch_load_config(monkeypatch, config)

    assert config.ingestion is not None
    assert config.ingestion is not None
    metadata_dir = Path(config.ingestion.output_dir)
    sample_csv = metadata_dir / "sample.csv"
    sample_csv.parent.mkdir(parents=True, exist_ok=True)
    sample_csv.write_text("id,title\n1,Example\n")

    instances: list[Any] = []

    class DummyEmbeddingService:
        def __init__(self, cfg: Any, base_path: Path | None = None) -> None:
            self.cfg = cfg
            self.base_path = base_path
            self.calls: list[Path] = []
            instances.append(self)

        def generate_embeddings_for_csv(
            self,
            csv_path: Path,
            model_cfg: Any,
            *,
            limit: int | None = None,
        ) -> tuple[int, Any]:
            self.calls.append(csv_path)
            return 1, None

        def refresh_backlog(self, metadata_dir: Path, model_cfg: Any) -> None:  # pragma: no cover - CLI expectation
            return None

    monkeypatch.setattr("papersys.embedding.EmbeddingService", DummyEmbeddingService)

    exit_code = main(["--config", str(config_path), "embed", "--limit", "2"])

    assert exit_code == 0
    assert instances
    assert instances[0].calls == [sample_csv]


def test_recommend_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_path: Path,
) -> None:
    config = make_app_config(tmp_path, include_recommend=True)
    patch_load_config(monkeypatch, config)

    calls: dict[str, Any] = {}

    class DummyPipeline:
        def __init__(self, cfg: Any, base_path: Path | None = None) -> None:
            calls["base_path"] = base_path
            calls["describe"] = 0

        def describe_sources(self) -> None:
            calls["describe"] += 1

        def run_and_save(self, **_: Any) -> None:
            raise AssertionError("run_and_save should not execute during dry-run")

    monkeypatch.setattr("papersys.cli.RecommendationPipeline", DummyPipeline)

    exit_code = main(["--config", str(config_path), "recommend", "--dry-run"])

    assert exit_code == 0
    assert calls["describe"] == 1
    assert calls["base_path"] is not None


def test_recommend_executes_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_path: Path,
) -> None:
    config = make_app_config(tmp_path, include_recommend=True)
    patch_load_config(monkeypatch, config)

    calls: dict[str, Any] = {}

    class DummyPipeline:
        def __init__(self, cfg: Any, base_path: Path | None = None) -> None:
            calls["base_path"] = base_path

        def describe_sources(self) -> None:
            calls["describe"] = True

        def run_and_save(
            self,
            *,
            force_include_all: bool,
            output_dir: Path | None,
        ) -> Any:
            calls["force"] = force_include_all
            calls["output_dir"] = output_dir
            run_dir = tmp_path / "recommendation-run"
            run_dir.mkdir(parents=True, exist_ok=True)
            predictions_path = run_dir / "predictions.parquet"
            recommended_path = run_dir / "recommended.parquet"
            manifest_path = run_dir / "manifest.json"
            predictions_path.write_text("", encoding="utf-8")
            recommended_path.write_text("", encoding="utf-8")
            manifest_path.write_text("{}", encoding="utf-8")
            return SimpleNamespace(
                output_dir=run_dir,
                predictions_path=predictions_path,
                recommended_path=recommended_path,
                manifest_path=manifest_path,
            )

    monkeypatch.setattr("papersys.cli.RecommendationPipeline", DummyPipeline)

    custom_output = Path("custom-output")
    exit_code = main(
        [
            "--config",
            str(config_path),
            "recommend",
            "--force-all",
            "--output-dir",
            str(custom_output),
        ]
    )

    assert exit_code == 0
    assert calls["describe"] is True
    assert calls["force"] is True
    assert calls["output_dir"].is_absolute()
    expected_output = (config.data_root / custom_output).resolve()
    assert calls["output_dir"] == expected_output


def test_config_check_json_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_path: Path,
    capsys: Any,
) -> None:
    config = make_app_config(tmp_path)
    patch_load_config(monkeypatch, config)

    result_payload = {
        "status": "ok",
        "config_path": str(config_path),
        "warnings": [],
    }

    monkeypatch.setattr(
        "papersys.cli.check_config",
        lambda path: (result_payload, 0, {}),
    )

    with logger_to_stderr():
        exit_code = main(["--config", str(config_path), "config", "check", "--format", "json"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert result_payload["config_path"] in captured.out


def test_config_check_text_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_path: Path,
    capsys: Any,
) -> None:
    config = make_app_config(tmp_path)
    patch_load_config(monkeypatch, config)

    result_payload = {
        "status": "error",
        "config_path": str(config_path),
        "warnings": [],
        "error": {
            "type": "validation",
            "message": "boom",
            "details": [{"loc": ["field"], "message": "missing", "type": "value_error"}],
        },
    }

    monkeypatch.setattr(
        "papersys.cli.check_config",
        lambda path: (result_payload, 2, {}),
    )

    with logger_to_stderr():
        exit_code = main(["--config", str(config_path), "config", "check"])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "Configuration error" in captured.err
    assert "field" in captured.err


def test_config_explain_json_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_path: Path,
    capsys: Any,
) -> None:
    config = make_app_config(tmp_path)
    patch_load_config(monkeypatch, config)

    monkeypatch.setattr(
        "papersys.cli.explain_config",
        lambda: [
            {"name": "summary_pipeline.llm.model", "type": "str", "required": True, "default": "llm"},
        ],
    )

    exit_code = main(["--config", str(config_path), "config", "explain", "--format", "json"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "summary_pipeline.llm.model" in captured.out


def test_config_explain_text_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_path: Path,
    capsys: Any,
) -> None:
    config = make_app_config(tmp_path)
    patch_load_config(monkeypatch, config)

    monkeypatch.setattr(
        "papersys.cli.explain_config",
        lambda: [
            {
                "name": "embedding.models",
                "type": "list",
                "required": False,
                "default": [],
                "description": "Configured embedding models",
            }
        ],
    )

    with logger_to_stderr():
        exit_code = main(["--config", str(config_path), "config", "explain"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Configured embedding models" in captured.err
