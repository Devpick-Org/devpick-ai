"""Source configurations for unified backfill collection pipeline."""

from __future__ import annotations

from app.schemas.source import SourceConfig

# ---------------------------------------------------------------------------
# Unified source configs — single collector per source (backfill + incremental)
# ---------------------------------------------------------------------------

KAKAO = SourceConfig(
    name="Kakao_Tech",
    feed_url="https://tech.kakao.com/feed/",
    site_url="https://tech.kakao.com/",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="Sequential post ID enumeration (675~). Backfill + incremental.",
    title_blocklist=["코딩테스트", "공채", "채용", "신입크루", "인턴", "문제해설"],
)

NAVER_D2 = SourceConfig(
    name="NAVER_D2",
    feed_url="https://d2.naver.com/d2.atom",
    site_url="https://d2.naver.com",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="REST API listing + individual article fetch. Backfill + incremental.",
    title_blocklist=["FE News"],
)

TOSS = SourceConfig(
    name="Toss_Tech",
    feed_url="https://toss.tech/rss.xml",
    site_url="https://toss.tech",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="Listing page pagination + article body extraction. Backfill + incremental.",
)

OLIVEYOUNG = SourceConfig(
    name="OliveYoung_Tech",
    feed_url="https://oliveyoung.tech/rss.xml",
    site_url="https://oliveyoung.tech",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="RSS feed parsing (full body in feed). Backfill + incremental.",
)

MEDIUM_DAANGN = SourceConfig(
    name="Medium_daangn",
    feed_url="https://medium.com/feed/daangn",
    site_url="https://medium.com/daangn",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="Medium internal JSON API + curl_cffi direct fetch. Backfill + incremental.",
)

MEDIUM_MUSINSA = SourceConfig(
    name="Medium_musinsa-tech",
    feed_url="https://medium.com/feed/musinsa-tech",
    site_url="https://medium.com/musinsa-tech",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="Medium internal JSON API + curl_cffi direct fetch. Backfill + incremental.",
)

MEDIUM_MYREALTRIP = SourceConfig(
    name="Medium_myrealtrip-product",
    feed_url="https://medium.com/feed/myrealtrip-product",
    site_url="https://medium.com/myrealtrip-product",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="Medium internal JSON API + curl_cffi direct fetch. Backfill + incremental.",
)

MEDIUM_NETFLIX = SourceConfig(
    name="Medium_netflix-techblog",
    feed_url="https://medium.com/feed/netflix-techblog",
    site_url="https://netflixtechblog.com",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="Medium internal JSON API + curl_cffi direct fetch (redirects to netflixtechblog.com). Backfill + incremental.",
)


STACKOVERFLOW = SourceConfig(
    name="Stack_Overflow",
    feed_url="https://stackoverflow.com/questions?tab=trending",
    site_url="https://stackoverflow.com",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="Trending page crawl + API body/answers. Backfill: monthly sort=hot API.",
)

VELOG = SourceConfig(
    name="Velog",
    feed_url="https://velog.io/trending",
    site_url="https://velog.io",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="GraphQL trendingPosts with HTML crawl fallback. ADR-006: SUMMARY_ONLY.",
)


def get_all_sources() -> list[SourceConfig]:
    """Return all active source configs for the unified collection pipeline."""
    return [
        KAKAO,
        NAVER_D2,
        TOSS,
        OLIVEYOUNG,
        MEDIUM_DAANGN,
        MEDIUM_MUSINSA,
        MEDIUM_MYREALTRIP,
        MEDIUM_NETFLIX,
        STACKOVERFLOW,
        VELOG,
    ]


# ---------------------------------------------------------------------------
# Backward-compatibility aliases (used by existing scripts during migration)
# ---------------------------------------------------------------------------


def get_backfill_sources() -> list[SourceConfig]:
    """Alias for get_all_sources() — kept for backward compatibility."""
    return get_all_sources()
