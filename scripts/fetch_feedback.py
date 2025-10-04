#!/usr/bin/env python
"""Fetch feedback from giscus or Notion and update preferences."""
import argparse
from pathlib import Path
import json

from loguru import logger

from papersys.config import load_config
from papersys.feedback.service import FeedbackService, FeedbackConfig


def main(args):
    config = load_config()
    publishing_config = config.publishing  # Assume integrated in config

    feedback_config = FeedbackConfig(
        github_token=publishing_config.github_token,
        notion_token=publishing_config.notion_token,
        notion_database_id=publishing_config.notion_database_id,
        owner=publishing_config.owner,
        repo=publishing_config.repo,
        preferences_dir=publishing_config.preferences_dir
    )

    service = FeedbackService(feedback_config)

    if args.source == "giscus":
        out_path = Path("data/feedback") / f"{args.year}_discussions.csv"
        df = service.fetch_giscus_feedback(out_path)
        logger.info(f"Fetched giscus feedback: {len(df)} records")
        print(df)

    elif args.source == "notion":
        database_id = args.database_id or publishing_config.notion_database_id
        df = service.fetch_notion_feedback(database_id)
        logger.info(f"Fetched Notion feedback: {len(df)} records")
        print(df)

    else:
        logger.error("Source must be 'giscus' or 'notion'")
        return 1

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch feedback and update preferences")
    parser.add_argument("--source", choices=["giscus", "notion"], required=True, help="Feedback source")
    parser.add_argument("--year", type=str, default="2025", help="Year for preferences file")
    parser.add_argument("--database-id", help="Notion database ID (if source=notion)")
    args = parser.parse_args()
    exit(main(args))