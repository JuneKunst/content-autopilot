"""Data models for configuration schemas."""

from pydantic import BaseModel


class PersonaConfig(BaseModel):
    """Configuration for a content persona."""

    name: str
    tone: str
    language: str = "ko"
    style_rules: list[str] = []
    example_openings: list[str] = []
    example_transitions: list[str] = []
    forbidden_patterns: list[str] = []


class SourceConfig(BaseModel):
    """Configuration for a content source."""

    type: str  # hn, reddit, github, rss, youtube
    endpoint: str = ""
    params: dict = {}
    schedule: str = "0 7,12,18 * * *"  # cron
    enabled: bool = True
