import sys

import pytest
from loguru import logger

from papersys.config import AppConfig, SchedulerConfig, SchedulerJobConfig
from papersys.scheduler import SchedulerService


@pytest.fixture
def mock_config() -> AppConfig:
    """Provides a mock AppConfig with scheduler settings for testing."""
    return AppConfig(
        scheduler=SchedulerConfig(
            enabled=True,
            recommend_job=SchedulerJobConfig(
                enabled=True, name="test-recommend", cron_schedule="* * * * *"
            ),
            summary_job=SchedulerJobConfig(
                enabled=False, name="test-summary", cron_schedule="* * * * *"
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


def test_scheduler_service_dry_run(mock_config, capsys):
    """Test that dry_run prevents the scheduler from starting."""
    # Reconfigure logger to ensure capture by capsys
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    service = SchedulerService(mock_config, dry_run=True)
    service.setup_jobs()
    service.start()

    assert not service.scheduler.running

    captured = capsys.readouterr()
    assert "[Dry Run] Jobs have been validated and registered" in captured.err
    assert "[Dry Run] Scheduler start is skipped" in captured.err


def test_scheduler_service_start_and_shutdown(mock_config):
    """Test the start and shutdown methods of the scheduler."""
    service = SchedulerService(mock_config)
    service.setup_jobs()

    service.scheduler.start(paused=True)
    assert service.scheduler.running

    service.shutdown()
    assert not service.scheduler.running