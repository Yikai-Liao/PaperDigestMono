"""Publishing configuration models."""
from typing import Optional
from pathlib import Path

from pydantic import BaseModel, Field

from .base import BaseConfig


class PublishingConfig(BaseConfig):
    """Configuration for publishing and feedback modules."""
    # GitHub giscus config
    github_token: str = Field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    owner: str = "your-org"  # Repository owner for giscus
    repo: str = "your-repo"  # Repository name for giscus
    
    # Notion config
    notion_token: Optional[str] = Field(default_factory=lambda: os.getenv("NOTION_TOKEN", None))
    notion_database_id: Optional[str] = None  # Notion database for feedback
    
    # Publishing paths
    content_dir: Path = Path("data/publishing/content")
    template_path: Path = Path("config/template.j2")
    preferences_dir: Path = Path("data/preferences")
    
    # Content repo (for push, e.g., HF or GitHub)
    content_repo: Optional[str] = None  # e.g., "user/content-repo"
    
    # Model for summaries
    model_name: str = "gemini"  # or openai, etc.