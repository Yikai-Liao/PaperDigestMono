"""HTTP-level tests for the FastAPI web console and APIs."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from papersys.config import AppConfig, SchedulerConfig, SchedulerJobConfig
from papersys.config.web import WebAuthConfig, WebUIConfig
from papersys.scheduler import SchedulerService
from papersys.web import create_app


def _build_app_config(web: WebUIConfig | None) -> AppConfig:
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
                enabled=True, name="test-summary", cron="* * * * *"
            ),
        ),
        web=web,
    )


@pytest.fixture
def config_without_auth() -> AppConfig:
    """Configuration with the console enabled but auth disabled."""
    web = WebUIConfig(enabled=True, title="Test Console", auth=None)
    return _build_app_config(web)


@pytest.fixture
def config_with_auth() -> AppConfig:
    """Configuration with header token authentication enabled."""
    web = WebUIConfig(
        enabled=True,
        title="Secured Console",
        auth=WebAuthConfig(enabled=True, header_name="X-Test-Token", token="secret-token"),
    )
    return _build_app_config(web)


def _build_client(config: AppConfig) -> TestClient:
    service = SchedulerService(config)
    service.setup_jobs()
    app = create_app(service, config)
    return TestClient(app)


@pytest.fixture
def client(config_without_auth: AppConfig) -> TestClient:
    return _build_client(config_without_auth)


@pytest.fixture
def client_with_auth(config_with_auth: AppConfig) -> TestClient:
    return _build_client(config_with_auth)


def test_health_check(client: TestClient) -> None:
    """The health endpoint should remain publicly accessible."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_jobs_without_auth(client: TestClient) -> None:
    """When auth is disabled the jobs endpoint responds without headers."""
    response = client.get("/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert [job["id"] for job in jobs] == ["recommend", "summary"]


def test_console_page_renders_html(client: TestClient) -> None:
    """The HTML console should render when enabled."""
    response = client.get("/console")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "Scheduled jobs" in body
    assert "Save token" not in body  # Token UI hidden when auth disabled


def test_jobs_endpoint_requires_token(client_with_auth: TestClient) -> None:
    """Missing authentication headers should be rejected."""
    response = client_with_auth.get("/jobs")
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing authentication token."


def test_jobs_endpoint_accepts_token(client_with_auth: TestClient) -> None:
    """Providing the correct token allows the request."""
    response = client_with_auth.get("/jobs", headers={"X-Test-Token": "secret-token"})
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 2


def test_run_job_requires_valid_token(client_with_auth: TestClient) -> None:
    """An incorrect token should not trigger jobs."""
    response = client_with_auth.post(
        "/scheduler/run/recommend",
        headers={"X-Test-Token": "wrong"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid authentication token."


def test_run_job_with_valid_token(client_with_auth: TestClient) -> None:
    """The manual trigger works when a valid token is supplied."""
    response = client_with_auth.post(
        "/scheduler/run/recommend",
        headers={"X-Test-Token": "secret-token"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_run_unknown_job_returns_404(client_with_auth: TestClient) -> None:
    """Unknown jobs should still report 404 after auth succeeds."""
    response = client_with_auth.post(
        "/scheduler/run/unknown",
        headers={"X-Test-Token": "secret-token"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Job 'unknown' not found."


def test_console_with_auth_shows_token_inputs(client_with_auth: TestClient) -> None:
    """The UI should expose token controls when auth is enabled."""
    response = client_with_auth.get("/console")
    assert response.status_code == 200
    assert "Access token" in response.text
