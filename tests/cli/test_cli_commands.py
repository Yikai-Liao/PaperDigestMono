from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

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

        def run(self, sources: list[Any], dry_run: bool = False) -> list[Any]:
            calls["run"] = dry_run
            return []

    monkeypatch.setattr("papersys.cli.SummaryPipeline", DummyPipeline)

    exit_code = main(["--config", str(config_path), "summarize", "--dry-run"])

    assert exit_code == 0
    assert calls["base_path"] is not None
    assert calls["run"] is True


def test_summarize_without_dry_run_warns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: Any,
    config_path: Path,
) -> None:
    config = make_app_config(tmp_path)
    patch_load_config(monkeypatch, config)

    pipelines: list[Any] = []

    class DummyPipeline:
        def __init__(self, cfg: Any, base_path: Path | None = None) -> None:
            self.run_called = False
            pipelines.append(self)

        def run(self, sources: list[Any], dry_run: bool = False) -> list[Any]:
            self.run_called = True
            return []

    monkeypatch.setattr("papersys.cli.SummaryPipeline", DummyPipeline)

    with logger_to_stderr():
        exit_code = main(["--config", str(config_path), "summarize"])

    assert exit_code == 0
    assert pipelines
    assert pipelines[0].run_called is False
    captured = capsys.readouterr()
    assert "Use --dry-run" in captured.err


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
        def __init__(self, cfg: Any) -> None:
            self.cfg = cfg
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
        def __init__(self, cfg: Any) -> None:
            self.cfg = cfg
            instances.append(self)

        def detect_backlog(self, metadata_dir: Path, alias: str) -> list[Path]:
            backlog_calls["metadata_dir"] = metadata_dir
            backlog_calls["alias"] = alias
            return [metadata_dir / "backlog.csv"]

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
        def __init__(self, cfg: Any) -> None:
            self.cfg = cfg
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

    monkeypatch.setattr("papersys.embedding.EmbeddingService", DummyEmbeddingService)

    exit_code = main(["--config", str(config_path), "embed", "--limit", "2"])

    assert exit_code == 0
    assert instances
    assert instances[0].calls == [sample_csv]


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
