import pytest
from fastapi.testclient import TestClient

from papersys.config import AppConfig, SchedulerConfig, SchedulerJobConfig
from papersys.scheduler import SchedulerService
from papersys.web import create_app


@pytest.fixture
def mock_scheduler_service() -> SchedulerService:
    """Provides a SchedulerService with a mock config."""
    config = AppConfig(
        scheduler=SchedulerConfig(
            enabled=True,
            recommend_job=SchedulerJobConfig(
                enabled=True, name="test-recommend", cron_schedule="* * * * *"
            ),
            summary_job=SchedulerJobConfig(
                enabled=True, name="test-summary", cron_schedule="* * * * *"
            ),
        )
    )
    service = SchedulerService(config)
    service.setup_jobs()
    return service


@pytest.fixture
def client(mock_scheduler_service: SchedulerService) -> TestClient:
    """Provides a TestClient for the FastAPI app."""
    app = create_app(mock_scheduler_service)
    return TestClient(app)


def test_health_check(client: TestClient):
    """Test the /health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_jobs(client: TestClient):
    """Test the /jobs endpoint."""
    response = client.get("/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 2
    assert jobs[0]["id"] == "recommend"
    assert jobs[1]["id"] == "summary"


def test_run_job_successfully(client: TestClient):
    """Test the /scheduler/run/{job_id} endpoint for a valid job."""
    response = client.post("/scheduler/run/recommend")
    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "message": "Job 'recommend' has been triggered to run.",
    }


def test_run_nonexistent_job(client: TestClient):
    """Test running a job that does not exist."""
    response = client.post("/scheduler/run/nonexistent")
    assert response.status_code == 404
    assert response.json() == {"detail": "Job 'nonexistent' not found."}