from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from papersys.config import AppConfig, SchedulerConfig, SchedulerJobConfig
from papersys.scheduler import SchedulerService
from papersys.web import create_app


@pytest.fixture()
def mock_scheduler_service() -> SchedulerService:
    config = AppConfig(
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
                enabled=True, name="test-summary", cron="* * * * *"
            ),
        ),
    )
    service = SchedulerService(config)
    service.setup_jobs()
    return service


@pytest.fixture()
def client(mock_scheduler_service: SchedulerService) -> TestClient:
    app = create_app(mock_scheduler_service)
    return TestClient(app)


def test_health_check(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_jobs(client: TestClient) -> None:
    response = client.get("/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 2
    assert {job["id"] for job in jobs} == {"recommend", "summary"}
    assert all("next_run_time" in job for job in jobs)


def test_run_job_successfully(client: TestClient) -> None:
    response = client.post("/scheduler/run/recommend")
    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "message": "Job 'recommend' has been scheduled to run.",
    }


def test_run_nonexistent_job(client: TestClient) -> None:
    response = client.post("/scheduler/run/nonexistent")
    assert response.status_code == 404
    assert response.json() == {"detail": "Job 'nonexistent' not found."}


def test_metrics_endpoint(client: TestClient, mock_scheduler_service: SchedulerService) -> None:
    runner = mock_scheduler_service._job_runners["recommend"]
    try:
        runner()
    except Exception:
        pass  # Expected in test environment due to incomplete config/data

    response = client.get("/metrics")
    assert response.status_code == 200
    assert "scheduler_job_runs_total" in response.text
    assert response.headers["content-type"].startswith("text/plain")
