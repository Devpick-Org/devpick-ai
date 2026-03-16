"""Default source list for local ingestion runs."""

from __future__ import annotations

from app.schemas.source import SourceConfig

MEDIUM_PUBLICATIONS: list[str] = [
    "daangn",
    "zigbang",
    "watcha",
]


BASE_SOURCES: list[SourceConfig] = [
    SourceConfig(
        name="NAVER_D2",
        feed_url="https://d2.naver.com/d2.atom",
        site_url="https://d2.naver.com",
        parser_type="atom",
        content_level=2,
        active=True,
        note="Level 2 raw feed collection source",
    ),
    SourceConfig(
        name="Toss_Tech",
        feed_url="https://toss.tech/rss.xml",
        site_url="https://toss.tech",
        parser_type="rss",
        content_level=2,
        active=True,
        note="Level 2 raw feed collection source",
    ),
]


def build_medium_sources() -> list[SourceConfig]:
    """Build Medium publication RSS source configs."""
    return [
        SourceConfig(
            name=f"Medium_{publication}",
            feed_url=f"https://medium.com/feed/{publication}",
            site_url=f"https://medium.com/{publication}",
            parser_type="rss",
            content_level=2,
            active=True,
            note="Level 2 RSS - Medium publication",
        )
        for publication in MEDIUM_PUBLICATIONS
    ]


def get_default_sources() -> list[SourceConfig]:
    """Return default level-2 RSS/Atom sources including Medium publications."""
    return [*BASE_SOURCES, *build_medium_sources()]


KAKAO_CRAWL_SOURCE = SourceConfig(
    name="Kakao_Tech",
    feed_url="https://tech.kakao.com/feed/",
    site_url="https://tech.kakao.com/",
    parser_type="rss",
    content_level=1,
    active=True,
    note="Level 1 RSS + crawl",
)


def get_crawl_sources() -> list[SourceConfig]:
    """Return currently enabled RSS+crawl sources."""
    return [KAKAO_CRAWL_SOURCE]


DEFAULT_SOURCES: list[SourceConfig] = get_default_sources()
