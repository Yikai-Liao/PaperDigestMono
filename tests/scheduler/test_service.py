from __future__ import annotations

import sys
from datetime import UTC, datetime

import pytest
from loguru import logger

from papersys.config import AppConfig, SchedulerConfig, SchedulerJobConfig
from papersys.scheduler import SchedulerService


@pytest.fixture()
def mock_config() -> AppConfig:
    return AppConfig(
        data_root=None,
        scheduler_enabled=True,
        logging_level="INFO",
        scheduler=SchedulerConfig(
            enabled=True,
            timezone="UTC",
            recommend_job=SchedulerJobConfig(
                enabled=True, name="test-recommend", cron="* * * * *"
            ),
            summary_job=SchedulerJobConfig(
                enabled=False, name="test-summary", cron="* * * * *"
            ),
        ),
    )


def test_scheduler_service_init(mock_config: AppConfig) -> None:
    service = SchedulerService(mock_config)
    assert service.config == mock_config
    assert not service.dry_run
    assert service.scheduler is not None


def test_scheduler_service_setup_jobs(mock_config: AppConfig) -> None:
    service = SchedulerService(mock_config)
    service.setup_jobs()

    job = service.scheduler.get_job("recommend")
    assert job is not None
    assert job.id == "recommend"
    assert "next_run_time" in service.get_metrics_snapshot()["recommend"]


def test_scheduler_service_dry_run(mock_config: AppConfig, capsys: pytest.CaptureFixture[str]) -> None:
    logger_id = logger.add(sys.stderr, level="INFO")
    try:
        service = SchedulerService(mock_config, dry_run=True)
        service.setup_jobs()
        service.start()

        assert not service.scheduler.running

        captured = capsys.readouterr()
        assert "[Dry Run] Jobs have been validated and registered" in captured.err
        assert "[Dry Run] Scheduler start is skipped" in captured.err

        metrics = service.get_metrics_snapshot()["recommend"]
        assert metrics["dry_run_count"] >= 1
    finally:
        logger.remove(logger_id)


def test_scheduler_service_start_and_shutdown(mock_config: AppConfig) -> None:
    service = SchedulerService(mock_config)
    service.setup_jobs()

    service.scheduler.start(paused=True)
    assert service.scheduler.running

    service.shutdown()
    assert not service.scheduler.running


def test_scheduler_service_trigger_job(mock_config: AppConfig) -> None:
    service = SchedulerService(mock_config)

    def noop(job_config: SchedulerJobConfig) -> None:  # pragma: no cover - simple stub
        assert job_config.name == "test-recommend"

    service._run_recommend_pipeline = noop  # type: ignore[assignment]
    service.setup_jobs()

    result = service.trigger_job("recommend")

    assert result is True
    manual_jobs = [job for job in service.scheduler.get_jobs() if job.id.startswith("recommend-manual-")]
    assert manual_jobs, "Manual trigger should append a one-off job"


def test_metrics_record_success(mock_config: AppConfig) -> None:
    service = SchedulerService(mock_config)

    executed: list[datetime] = []

    def succeed(_: SchedulerJobConfig) -> None:
        executed.append(datetime.now(UTC))

    service._run_recommend_pipeline = succeed  # type: ignore[assignment]
    service.setup_jobs()

    runner = service._job_runners["recommend"]
    runner()

    metrics = service.get_metrics_snapshot()["recommend"]
    assert metrics["success_count"] == 1
    assert metrics["total_runs"] == 1
    assert metrics["last_status"] == "success"
    assert metrics["last_duration_seconds"] is not None
    assert executed


def test_metrics_record_failure(mock_config: AppConfig) -> None:
    service = SchedulerService(mock_config)

    def failing(_: SchedulerJobConfig) -> None:
        raise RuntimeError("boom")

    service._run_recommend_pipeline = failing  # type: ignore[assignment]
    service.setup_jobs()

    runner = service._job_runners["recommend"]

    with pytest.raises(RuntimeError):
        runner()

    metrics = service.get_metrics_snapshot()["recommend"]
    assert metrics["failure_count"] == 1
    assert metrics["total_runs"] == 1
    assert metrics["last_status"] == "failure"
    assert metrics["last_error"] == "boom"


def test_export_metrics_prometheus(mock_config: AppConfig) -> None:
    service = SchedulerService(mock_config)

    def succeed(_: SchedulerJobConfig) -> None:
        return None

    service._run_recommend_pipeline = succeed  # type: ignore[assignment]
    service.setup_jobs()

    runner = service._job_runners["recommend"]
    runner()

    payload = service.export_metrics()
    assert "scheduler_job_runs_total" in payload
    assert 'job_id="recommend"' in payload
    assert "scheduler_job_success_total" in payload
    assert payload.endswith("\n")
