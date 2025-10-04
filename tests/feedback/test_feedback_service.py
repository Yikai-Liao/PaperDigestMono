"""Tests for feedback service."""
import os
import requests
import pytest
from unittest.mock import patch, MagicMock
import polars as pl
from pathlib import Path

from papersys.feedback.service import FeedbackService, FeedbackConfig
from papersys.config.publishing import PublishingConfig


@pytest.fixture
def config(tmp_path):
    prefs_dir = tmp_path / "preferences"
    prefs_dir.mkdir()
    return FeedbackConfig(
        github_token="fake_token",
        owner="test_owner",
        repo="test_repo",
        preferences_dir=prefs_dir
    )


@pytest.fixture
def service(config):
    return FeedbackService(config)


@pytest.fixture(scope="function")
def isolated_data_path(tmp_path):
    p = tmp_path / "data"
    p.mkdir(exist_ok=True)
    return p

def test_fetch_giscus_feedback_success(service):
    """Test successful giscus feedback fetch."""
    mock_response = {
        "data": {
            "repository": {
                "discussions": {
                    "nodes": [
                        {
                            "id": "disc1",
                            "title": "Discussion on arXiv:2310.12345",
                            "updatedAt": "2025-01-01T00:00:00Z",
                            "url": "https://github.com/discussions/1",
                            "number": 1,
                            "reactions": {
                                "nodes": [
                                    {"content": "THUMBS_UP", "user": {"login": "user1"}},
                                    {"content": "THUMBS_UP", "user": {"login": "user2"}}
                                ]
                            }
                        }
                    ]
                }
            }
        }
    }

    with patch("papersys.feedback.service.requests.post") as mock_post:
        mock_post.return_value.json.return_value = mock_response
        mock_post.return_value.status_code = 200

        df = service.fetch_giscus_feedback()

    assert len(df) == 1
    assert df["arxiv_id"][0] == "2310.12345"
    assert df["preference"][0] == "like"
    assert df["discussion_id"][0] == 1


def test_fetch_giscus_feedback_failure(service):
    """Test giscus fetch failure."""
    with patch("papersys.feedback.service.requests.post") as mock_post:
        mock_post.return_value.status_code = 401
        mock_post.return_value.text = "Unauthorized"

        with pytest.raises(requests.RequestException):
            service.fetch_giscus_feedback()


def test_extract_arxiv_id():
    service = FeedbackService(FeedbackConfig(github_token="token"))
    assert service._extract_arxiv_id("Discussion on arXiv:2310.12345") == "2310.12345"
    assert service._extract_arxiv_id("No arXiv") is None


def test_update_preferences_csv(tmp_path, service):
    """Test updating preferences CSV."""
    prefs_dir = tmp_path / "preferences"
    prefs_dir.mkdir()
    csv_path = prefs_dir / "2025-01.csv"
    existing_df = pl.DataFrame({"arxiv_id": ["2310.12345"], "preference": ["neutral"]})
    existing_df.write_csv(csv_path)

    feedback_df = pl.DataFrame({
        "arxiv_id": ["2310.12345"],
        "preference": ["like"],
        "discussion_id": [1],
        "updated_at": ["2025-01-01"],
        "url": ["url"]
    })

    # Create a new service with updated config
    new_config = FeedbackConfig(
        github_token="fake_token",
        owner="test_owner",
        repo="test_repo",
        preferences_dir=prefs_dir
    )
    new_service = FeedbackService(new_config)
    new_service._update_preferences_csv(feedback_df)

    updated_df = pl.read_csv(csv_path)
    assert updated_df["preference"][0] == "like"


def test_fetch_notion_feedback_no_token(service):
    """Test Notion fetch with no token."""
    df = service.fetch_notion_feedback()
    assert df.height == 0


def test_publishing_config():
    """Test PublishingConfig loads correctly."""
    config = PublishingConfig()
    assert config.content_dir == Path("data/publishing/content")
    assert config.template_path == Path("config/template.j2")


# ASSERTION (for reviewer): tests must not write to repository data/ dir
# Example runtime check (do NOT execute now): assert not any(p.exists() for p in Path(".").rglob("data/*")), "tests wrote to production data/"