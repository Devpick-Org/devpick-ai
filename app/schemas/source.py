"""Source configuration schema for RSS/Atom raw collection."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SourceConfig(BaseModel):
    """Config for one feed source in ingestion pipeline."""

    name: str
    feed_url: str
    site_url: str
    parser_type: Literal["rss", "atom", "auto"] = "auto"
    content_level: int = Field(default=2, ge=1)
    active: bool = True
    note: str = ""
