from typing import Dict, List, Optional
import requests
import json
from pathlib import Path
import os
import polars as pl
from loguru import logger

from papersys.config.base import BaseConfig


class FeedbackConfig(BaseConfig):
    """Publishing and Feedback configuration."""
    github_token: str = os.getenv("GITHUB_TOKEN", "")
    notion_token: Optional[str] = os.getenv("NOTION_TOKEN", None)
    notion_database_id: Optional[str] = None
    owner: str = "your-org"  # Default, override in config
    repo: str = "your-repo"
    preferences_dir: Path = Path("data/preferences")


class FeedbackService:
    """Service for fetching and processing feedback from giscus (GitHub Discussions) and Notion."""

    def __init__(self, config: FeedbackConfig):
        self.config = config
        self.headers = {"Authorization": f"Bearer {config.github_token}"}
        logger.info("FeedbackService initialized")

    def fetch_giscus_feedback(self, out_path: Optional[Path] = None) -> pl.DataFrame:
        """
        Fetch feedback from GitHub Discussions (giscus) using GraphQL.
        Parses reactions to update preferences (e.g., 👍 -> like, 👎 -> dislike).
        Returns a Polars DataFrame with updated preferences.
        """
        if not self.config.github_token:
            raise ValueError("GITHUB_TOKEN is required for giscus feedback")

        query = """
        query($repoOwner: String!, $repoName: String!) {
          repository(owner: $repoOwner, name: $repoName) {
            discussions(last: 100, orderBy: {field: UPDATED_AT, direction: DESC}) {
              nodes {
                id
                title
                updatedAt
                url
                number
                reactions(first: 100) {
                  nodes {
                    content
                    user {
                      login
                    }
                  }
                }
              }
            }
          }
        }
        """
        variables = {"repoOwner": self.config.owner, "repoName": self.config.repo}

        logger.info(f"Fetching giscus feedback from {self.config.owner}/{self.config.repo}")

        resp = requests.post(
            "https://api.github.com/graphql",
            json={"query": query, "variables": variables},
            headers=self.headers,
        )

        if resp.status_code != 200:
            logger.error(f"GitHub API error: {resp.status_code} - {resp.text}")
            raise requests.RequestException(f"Failed to fetch discussions: {resp.text}")

        data = resp.json()
        if "errors" in data:
            logger.error(f"GraphQL errors: {data['errors']}")
            raise ValueError(f"GraphQL errors: {data['errors']}")

        discussions = data["data"]["repository"]["discussions"]["nodes"]
        feedback_rows = []

        for discussion in discussions:
            arxiv_id = self._extract_arxiv_id(discussion["title"])  # Assume title contains arxiv id
            if not arxiv_id:
                continue

            reactions = discussion["reactions"]["nodes"]
            likes = sum(1 for r in reactions if r["content"] == "THUMBS_UP")
            dislikes = sum(1 for r in reactions if r["content"] == "THUMBS_DOWN")

            preference = "like" if likes > dislikes else "dislike" if dislikes > 0 else "neutral"
            feedback_rows.append({
                "arxiv_id": arxiv_id,
                "discussion_id": discussion["number"],
                "preference": preference,
                "updated_at": discussion["updatedAt"],
                "url": discussion["url"]
            })

        df = pl.DataFrame(feedback_rows)
        if out_path:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            df.write_csv(out_path)
            logger.info(f"Feedback saved to {out_path}")

        # Update preferences CSV (append or merge)
        self._update_preferences_csv(df)

        return df

    def _extract_arxiv_id(self, title: str) -> Optional[str]:
        """Extract arXiv ID from discussion title (e.g., 'Discussion on arXiv:2310.12345')."""
        import re
        match = re.search(r'arXiv:(\d+\.\d+)', title)
        return match.group(1) if match else None

    def _update_preferences_csv(self, feedback_df: pl.DataFrame):
        """Update the latest preferences CSV with new feedback."""
        latest_csv = self._get_latest_preferences_csv()
        if latest_csv.exists():
            existing_df = pl.read_csv(latest_csv)
            # Merge on arxiv_id, update preference
            merged_df = existing_df.join(feedback_df.select(["arxiv_id", "preference"]), on="arxiv_id", how="left", suffix="_new")
            merged_df = merged_df.with_columns(
                pl.when(pl.col("preference_new").is_not_null()).then(pl.col("preference_new")).otherwise(pl.col("preference")).alias("preference")
            ).drop("preference_new")
            merged_df.write_csv(latest_csv)
            logger.info(f"Updated preferences in {latest_csv}")
        else:
            feedback_df.write_csv(latest_csv)
            logger.info(f"Created new preferences file {latest_csv}")

    def _get_latest_preferences_csv(self) -> Path:
        """Get path to latest monthly preferences CSV."""
        from datetime import datetime
        now = datetime.now()
        month_year = now.strftime("%Y-%m")
        return self.config.preferences_dir / f"{month_year}.csv"

    def fetch_notion_feedback(self, database_id: Optional[str] = None) -> pl.DataFrame:
        """
        Fetch feedback from Notion (TODO: Implement with notion-client).
        Requires NOTION_TOKEN and database_id.
        """
        if not self.config.notion_token:
            logger.warning("NOTION_TOKEN not configured, skipping Notion feedback")
            return pl.DataFrame()

        if not database_id:
            database_id = self.config.notion_database_id
        if not database_id:
            raise ValueError("Notion database_id required")

        # TODO: Implement using notion-client library
        # Query database for pages with properties (arxiv_id, preference, comments)
        # Parse comments for sentiment or explicit feedback
        logger.info(f"Fetching Notion feedback from database {database_id} (TODO)")
        # Placeholder return
        return pl.DataFrame({
            "arxiv_id": [],
            "preference": [],
            "comment": [],
            "updated_at": []
        })


if __name__ == "__main__":
    # Example usage
    config = FeedbackConfig()
    service = FeedbackService(config)
    df = service.fetch_giscus_feedback(Path("data/feedback/discussions.csv"))
    print(df)