from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from loguru import logger

from papersys.scheduler.service import SchedulerService


def create_app(scheduler_service: SchedulerService) -> FastAPI:
    """Creates and configures a FastAPI application."""
    app = FastAPI(
        title="PaperDigestMono API",
        description="API for managing and monitoring the paper processing pipeline.",
        version="0.1.0",
    )

    @app.get("/health", summary="Health Check", tags=["Monitoring"])
    async def health_check() -> dict[str, str]:
        """Check if the API is running."""
        return {"status": "ok"}

    @app.get("/jobs", summary="List All Scheduled Jobs", tags=["Scheduler"])
    async def list_jobs() -> list[dict[str, Any]]:
        """Returns a list of all configured jobs in the scheduler."""
        return scheduler_service.list_jobs()

    @app.post("/scheduler/run/{job_id}", summary="Manually Run a Job", tags=["Scheduler"])
    async def run_job(job_id: str) -> dict[str, str]:
        """
        Triggers a specific scheduled job to run immediately.
        """
        logger.info(f"Manual trigger for job '{job_id}' received.")
        if not scheduler_service.trigger_job(job_id):
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

        return {"status": "success", "message": f"Job '{job_id}' has been scheduled to run."}

    @app.get("/metrics", summary="Prometheus Metrics", tags=["Monitoring"], response_class=PlainTextResponse)
    async def metrics() -> PlainTextResponse:
        """Expose scheduler metrics in Prometheus text format."""

        payload = scheduler_service.export_metrics()
        return PlainTextResponse(content=payload, media_type="text/plain; version=0.0.4")

    return app