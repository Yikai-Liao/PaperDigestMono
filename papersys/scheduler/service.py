from typing import Dict, Any

from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger

from papersys.config import AppConfig, SchedulerJobConfig


class SchedulerService:
    """Manages scheduled jobs for the paper processing pipeline."""

    def __init__(self, config: AppConfig, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        self.scheduler = BackgroundScheduler(timezone="UTC")
        self._jobs: Dict[str, Any] = {}

    def setup_jobs(self):
        """Registers jobs based on the application configuration."""
        if not self.config.scheduler or not self.config.scheduler.enabled:
            logger.warning("Scheduler is disabled in the configuration. No jobs will be scheduled.")
            return

        logger.info("Setting up scheduled jobs...")
        if self.config.scheduler.recommend_job:
            self._register_job(
                job_id="recommend",
                job_config=self.config.scheduler.recommend_job,
                func=self._run_recommend_pipeline,
            )

        if self.config.scheduler.summary_job:
            self._register_job(
                job_id="summary",
                job_config=self.config.scheduler.summary_job,
                func=self._run_summary_pipeline,
            )

        if self.dry_run:
            logger.info("[Dry Run] Jobs have been validated and registered. Scheduler will not be started.")
            for job in self.scheduler.get_jobs():
                logger.info(f"[Dry Run] Job '{job.id}' with trigger: {job.trigger}")
            return

    def _register_job(self, job_id: str, job_config: SchedulerJobConfig, func):
        """Helper to register a single job."""
        if not job_config.enabled:
            logger.info(f"Job '{job_id}' is disabled, skipping.")
            return

        logger.info(f"Registering job '{job_id}' with cron schedule: '{job_config.cron_schedule}'")
        self.scheduler.add_job(
            func,
            "cron",
            id=job_id,
            name=job_id,
            day_of_week=job_config.cron_schedule.split(" ")[4],
            hour=job_config.cron_schedule.split(" ")[2],
            minute=job_config.cron_schedule.split(" ")[1],
            # second=job_config.cron_schedule.split(" ")[0], # APScheduler cron doesn't support seconds
            kwargs={"job_config": job_config},
        )

    def _run_recommend_pipeline(self, job_config: SchedulerJobConfig):
        """Placeholder for the actual recommendation pipeline execution."""
        logger.info(f"Executing recommendation pipeline for job '{job_config.name}'...")
        # In a real implementation, this would trigger the recommendation pipeline
        # from papersys.recommend.pipeline
        logger.info("Recommendation pipeline job finished.")

    def _run_summary_pipeline(self, job_config: SchedulerJobConfig):
        """Placeholder for the actual summary pipeline execution."""
        logger.info(f"Executing summary pipeline for job '{job_config.name}'...")
        # In a real implementation, this would trigger the summary pipeline
        # from papersys.summary.pipeline
        logger.info("Summary pipeline job finished.")

    def start(self):
        """Starts the scheduler if not in dry run mode."""
        if self.dry_run:
            logger.info("[Dry Run] Scheduler start is skipped.")
            return
        if not self.scheduler.get_jobs():
            logger.warning("No jobs are scheduled. The scheduler will not start.")
            return

        logger.info("Starting scheduler...")
        self.scheduler.start()

    def shutdown(self):
        """Shuts down the scheduler gracefully."""
        if self.scheduler.running:
            logger.info("Shutting down scheduler...")
            self.scheduler.shutdown()
            logger.info("Scheduler has been shut down.")
        else:
            logger.info("Scheduler is not running.")