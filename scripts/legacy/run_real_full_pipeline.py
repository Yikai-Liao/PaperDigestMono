#!/usr/bin/env python
"""Run the full paper processing pipeline end-to-end with real data."""
import argparse
from pathlib import Path
from datetime import datetime
from loguru import logger

from papersys.config import load_config
from papersys.ingestion.service import IngestionService
from papersys.embedding.service import EmbeddingService
from papersys.recommend.pipeline import run_recommend_pipeline
from papersys.summary.pipeline import run_summary_pipeline
from papersys.feedback.service import FeedbackService, FeedbackConfig
from papersys.config.publishing import PublishingConfig
from scripts.build_site import main as build_site_main


def main(args):
    config = load_config()
    year = args.year or datetime.now().year

    logger.info(f"Starting full pipeline for year {year}")

    if not args.dry_run:
        # Step 1: Ingestion
        logger.info("Running ingestion...")
        ingestion_service = IngestionService(config)
        ingestion_service.run(year=year)

        # Step 2: Embedding
        logger.info("Running embedding...")
        embedding_service = EmbeddingService(config)
        embedding_service.run(year=year)

        # Step 3: Recommendation
        logger.info("Running recommendation...")
        run_recommend_pipeline(config, year=year)

        # Step 4: Summary
        logger.info("Running summary...")
        run_summary_pipeline(config, year=year)

        # Step 5: Publishing
        logger.info("Running publishing...")
        build_site_main(str(year))

        # Step 6: Feedback
        logger.info("Running feedback fetch...")
        publishing_config = config.publishing
        feedback_config = FeedbackConfig(
            github_token=publishing_config.github_token,
            notion_token=publishing_config.notion_token,
            notion_database_id=publishing_config.notion_database_id,
            owner=publishing_config.owner,
            repo=publishing_config.repo,
            preferences_dir=publishing_config.preferences_dir
        )
        feedback_service = FeedbackService(feedback_config)
        feedback_service.fetch_giscus_feedback()

        # Step 7: Backup
        logger.info("Running backup...")
        from papersys.backup.service import BackupService
        backup_service = BackupService(config)
        backup_service.run()

    else:
        logger.info("[DRY RUN] Skipping all pipeline steps")

    logger.info("Full pipeline completed successfully")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run full paper processing pipeline")
    parser.add_argument("--year", type=int, help="Year for processing")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without executing")
    args = parser.parse_args()
    main(args)