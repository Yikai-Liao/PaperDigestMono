#!/usr/bin/env python
"""Build static site from summary documents."""
import argparse
from pathlib import Path
import polars as pl
from loguru import logger

from papersys.config import load_config
from papersys.summary.renderer import SummaryRenderer
from papersys.summary.models import SummaryDocument
from papersys.feedback.service import FeedbackConfig  # For preferences


def main(args):
    config = load_config()
    publishing_config = config.publishing  # Assume config has publishing section

    # Load summary data (assume from data/summarized/YYYY.jsonl or parquet)
    summaries_path = Path("data/summarized") / f"{args.year}.jsonl"
    if not summaries_path.exists():
        logger.error(f"Summaries not found at {summaries_path}")
        return 1

    # Load summaries (placeholder: parse JSONL to SummaryDocument list)
    documents = []
    with open(summaries_path, "r") as f:
        for line in f:
            data = json.loads(line.strip())
            doc = SummaryDocument(
                paper_id=data["id"],
                title=data["title"],
                language=data.get("language", "en"),
                sections={
                    "Background Problem": data.get("problem_background", ""),
                    "Method": data.get("method", ""),
                    "Experiment": data.get("experiment", ""),
                    "Further Thoughts": data.get("further_thoughts", "")
                }
            )
            # Add additional fields if available
            doc.authors = data.get("authors", [])
            doc.abstract = data.get("abstract", "")
            doc.updated_at = data.get("summary_time", "")
            documents.append(doc)

    # Load preferences for draft status
    feedback_config = FeedbackConfig()  # Or from publishing_config
    preferences_df = pl.read_csv(feedback_config.preferences_dir / f"{args.year}.csv") if (feedback_config.preferences_dir / f"{args.year}.csv").exists() else None

    # Render and build site
    renderer = SummaryRenderer(template_path=publishing_config.template_path)
    output_dir = publishing_config.content_dir / f"{args.year}"
    renderer.build_site(documents, output_dir, preferences_df)

    logger.info(f"Site built in {output_dir}")

    # Optional: Push to content_repo (HF or Git)
    if publishing_config.content_repo:
        # TODO: Implement push to HF dataset or Git repo
        logger.info(f"Push to {publishing_config.content_repo} (TODO)")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build static site from summaries")
    parser.add_argument("--year", type=str, default="2025", help="Year for summaries")
    args = parser.parse_args()
    exit(main(args))