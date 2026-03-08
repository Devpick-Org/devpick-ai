"""Ingestion configuration package."""

from .sources import DEFAULT_SOURCES, KAKAO_CRAWL_SOURCE, get_crawl_sources

__all__ = ["DEFAULT_SOURCES", "KAKAO_CRAWL_SOURCE", "get_crawl_sources"]
