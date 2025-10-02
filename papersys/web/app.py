"""FastAPI application factory and routing definitions."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any, Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from loguru import logger

from papersys.config.app import AppConfig
from papersys.config.web import WebAuthConfig
from papersys.scheduler.service import SchedulerService


def create_app(scheduler_service: SchedulerService, config: AppConfig | None = None) -> FastAPI:
    """Creates and configures a FastAPI application with optional UI and auth."""
    web_config = config.web if config and config.web else None
    auth_config = web_config.auth if web_config and web_config.auth else None
    auth_dependency = _build_auth_dependency(auth_config)

    app = FastAPI(
        title="PaperDigestMono API",
        description="API for managing and monitoring the paper processing pipeline.",
        version="0.1.0",
    )

    templates = Jinja2Templates(directory=str(_templates_dir()))

    @app.get("/health", summary="Health Check", tags=["Monitoring"])
    async def health_check() -> dict[str, str]:
        """Check if the API is running."""
        return {"status": "ok"}

    @app.get(
        "/jobs",
        summary="List All Scheduled Jobs",
        tags=["Scheduler"],
    )
    async def list_jobs(_: None = Depends(auth_dependency)) -> list[dict[str, Any]]:
        """Returns a list of all configured jobs in the scheduler."""
        return scheduler_service.list_jobs()

    @app.post(
        "/scheduler/run/{job_id}",
        summary="Manually Run a Job",
        tags=["Scheduler"],
    )
    async def run_job(job_id: str, _: None = Depends(auth_dependency)) -> dict[str, str]:
        """
        Triggers a specific scheduled job to run immediately.
        """
        logger.info(f"Manual trigger for job '{job_id}' received.")
        if not scheduler_service.trigger_job(job_id):
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

        return {"status": "success", "message": f"Job '{job_id}' has been scheduled to run."}

    @app.get("/console", response_class=HTMLResponse, include_in_schema=False)
    async def console(request: Request) -> HTMLResponse:
        """Render the lightweight scheduler console UI."""
        if web_config is None or not web_config.enabled:
            raise HTTPException(status_code=404, detail="Web console is disabled.")

        template_context = {
            "request": request,
            "title": web_config.title,
            "auth_enabled": bool(auth_config and auth_config.enabled),
            "header_name": auth_config.header_name if auth_config else "X-Console-Token",
        }
        return templates.TemplateResponse(request, "console.html", template_context)

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        """Redirect to the console when available."""
        if web_config and web_config.enabled:
            return RedirectResponse(url="/console")
        raise HTTPException(status_code=404, detail="Web console is disabled.")

    return app


def _templates_dir() -> Path:
    """Return the directory containing HTML templates."""
    return Path(__file__).resolve().parent / "templates"


def _build_auth_dependency(auth_config: WebAuthConfig | None) -> Callable[..., Any]:
    """Return a dependency that validates the configured auth token."""

    if not auth_config or not auth_config.enabled:
        async def _no_auth() -> None:  # pragma: no cover - trivial branch
            return None

        return _no_auth

    expected_token = auth_config.token or ""
    header_alias = auth_config.header_name

    async def _verify_token(
        provided_token: str | None = Header(default=None, alias=header_alias),
    ) -> None:
        if provided_token is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authentication token.",
            )

        if not secrets.compare_digest(provided_token, expected_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token.",
            )

    return _verify_token
