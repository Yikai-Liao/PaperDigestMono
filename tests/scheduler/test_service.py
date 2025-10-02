import sys

import pytest
from loguru import logger

from papersys.config import AppConfig, SchedulerConfig, SchedulerJobConfig
from papersys.scheduler import SchedulerService


@pytest.fixture
def mock_config() -> AppConfig:
    """Provides a mock AppConfig with scheduler settings for testing."""
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
            backup_job=SchedulerJobConfig(
                enabled=True, name="test-backup", cron="*/5 * * * *"
            ),
        )
    )


def test_scheduler_service_init(mock_config):
    """Test that the SchedulerService initializes correctly."""
    service = SchedulerService(mock_config)
    assert service.config == mock_config
    assert not service.dry_run
    assert service.scheduler is not None


def test_scheduler_service_setup_jobs(mock_config):
    """Test that jobs are registered correctly based on the config."""
    service = SchedulerService(mock_config)
    service.setup_jobs()

    assert service.scheduler.get_job("recommend") is not None
    assert service.scheduler.get_job("summary") is None  # Disabled in config
    assert service.scheduler.get_job("backup") is not None


def test_scheduler_service_dry_run(mock_config, capsys):
    """Test that dry_run prevents the scheduler from starting."""
    logger_id = logger.add(sys.stderr, level="INFO")
    try:
        service = SchedulerService(mock_config, dry_run=True)
        service.setup_jobs()
        service.start()

        assert not service.scheduler.running

        captured = capsys.readouterr()
        assert "[Dry Run] Jobs have been validated and registered" in captured.err
        assert "[Dry Run] Scheduler start is skipped" in captured.err
    finally:
        logger.remove(logger_id)


def test_scheduler_service_start_and_shutdown(mock_config):
    """Test the start and shutdown methods of the scheduler."""
    service = SchedulerService(mock_config)
    service.setup_jobs()

    service.scheduler.start(paused=True)
    assert service.scheduler.running

    service.shutdown()
    assert not service.scheduler.running


def test_scheduler_service_trigger_job(mock_config):
    """Triggering a job should schedule an immediate run."""
    service = SchedulerService(mock_config)
    service.setup_jobs()

    result = service.trigger_job("recommend")

    assert result is True
    manual_jobs = [job for job in service.scheduler.get_jobs() if job.id.startswith("recommend-manual-")]
    assert manual_jobs, "Manual trigger should append a one-off job"