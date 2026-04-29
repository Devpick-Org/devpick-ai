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
    title_blocklist=["코딩테스트", "공채", "채용", "신입크루", "인턴", "문제해설", "모집합니다"],
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

MEDIUM_AIRBNB = SourceConfig(
    name="Medium_airbnb-engineering",
    feed_url="https://medium.com/feed/airbnb-engineering",
    site_url="https://medium.com/airbnb-engineering",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="Medium internal JSON API + curl_cffi direct fetch. Backfill + incremental.",
    title_blocklist=["My Journey to"],
)

MEDIUM_PINTEREST = SourceConfig(
    name="Medium_pinterest-engineering",
    feed_url="https://medium.com/feed/pinterest-engineering",
    site_url="https://medium.com/pinterest-engineering",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="Medium internal JSON API + curl_cffi direct fetch. Backfill + incremental.",
)

MEDIUM_GCCOMPANY = SourceConfig(
    name="Medium_gccompany",
    feed_url="https://medium.com/feed/gccompany",
    site_url="https://techblog.gccompany.co.kr",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="여기어때 기술블로그. Medium internal JSON API + curl_cffi direct fetch. Backfill + incremental.",
    title_blocklist=["인터뷰 당일"],
)

MEDIUM_FLUTTER = SourceConfig(
    name="Medium_flutter",
    feed_url="https://medium.com/feed/flutter",
    site_url="https://medium.com/flutter",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="Flutter 공식 블로그. Medium internal JSON API + curl_cffi direct fetch. Backfill + incremental.",
    title_blocklist=["Come meet", "on tour"],
)


WOOWAHAN = SourceConfig(
    name="Woowahan_Tech",
    feed_url="https://techblog.woowahan.com/feed/",
    site_url="https://techblog.woowahan.com",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="우아한형제들 기술블로그. WordPress RSS, content:encoded 전체 본문. Backfill + incremental.",
    title_blocklist=["인턴", "채용", "공채"],
)

META_ENGINEERING = SourceConfig(
    name="Meta_Engineering",
    feed_url="https://engineering.fb.com/feed/",
    site_url="https://engineering.fb.com",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="Meta Engineering blog. WordPress RSS, content:encoded 전체 본문. Backfill + incremental.",
)

CLOUDFLARE = SourceConfig(
    name="Cloudflare_Blog",
    feed_url="https://blog.cloudflare.com/rss/",
    site_url="https://blog.cloudflare.com",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="Cloudflare Blog. Ghost RSS, content:encoded 전체 본문. Backfill + incremental.",
)

SOCAR = SourceConfig(
    name="Socar_Tech",
    feed_url="https://tech.socarcorp.kr/feed",
    site_url="https://tech.socarcorp.kr",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="쏘카 기술블로그. Jekyll Atom, content type=html 전체 본문. Backfill + incremental.",
)

GITHUB_BLOG = SourceConfig(
    name="GitHub_Blog",
    feed_url="https://github.blog/feed",
    site_url="https://github.blog",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="GitHub Blog. WordPress RSS, content:encoded 전체 본문. Backfill + incremental.",
)

AWS_KOREA = SourceConfig(
    name="AWS_Korea_Tech",
    feed_url="https://aws.amazon.com/ko/blogs/tech/feed/",
    site_url="https://aws.amazon.com/ko/blogs/tech/",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="AWS 한국 기술블로그. WordPress RSS, content:encoded 전체 본문. Backfill + incremental.",
)

SPRING_IO = SourceConfig(
    name="Spring_Blog",
    feed_url="https://spring.io/blog.atom",
    site_url="https://spring.io/blog",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="Spring.io 공식 블로그. Atom listing + 개별 페이지 fetch (div.markdown). Backfill + incremental.",
    title_blocklist=["This Week in Spring"],
)

SK_PLANET = SourceConfig(
    name="SKPlanet_Tech",
    feed_url="https://techtopic.skplanet.com/rss",
    site_url="https://techtopic.skplanet.com",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="SK Planet Tech Topic. RSS, content:encoded 전체 본문. Backfill + incremental.",
    title_blocklist=["[안내]", "세미나", "모집"],
)

NONGSHIM_CLOUD = SourceConfig(
    name="Nongshim_Cloud_Tech",
    feed_url="https://tech.cloud.nongshim.co.kr/feed/",
    site_url="https://tech.cloud.nongshim.co.kr",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="농심 클라우드 기술블로그. WordPress RSS, content:encoded 전체 본문. Backfill + incremental.",
    title_blocklist=["[세션 리뷰]", "현장 스케치"],
)

MS_DEVBLOGS = SourceConfig(
    name="MS_DevBlogs",
    feed_url="https://devblogs.microsoft.com/feed/",
    site_url="https://devblogs.microsoft.com",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="Microsoft Developer Blogs. WordPress RSS, content:encoded 전체 본문. Backfill + incremental.",
)

NVIDIA_DEV = SourceConfig(
    name="NVIDIA_Developer",
    feed_url="https://developer.nvidia.com/blog/feed/",
    site_url="https://developer.nvidia.com/blog",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="NVIDIA Developer Blog. RSS listing + 개별 페이지 fetch. Backfill + incremental.",
)

FLEX_TEAM = SourceConfig(
    name="Flex_Tech",
    feed_url="https://flex.team/blog/rss.xml",
    site_url="https://flex.team/blog",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="flex 기술블로그. RSS listing + 개별 페이지 fetch (curl_cffi). Backfill + incremental.",
    title_blocklist=["[flex update]", "[flex webinar]", "[flex iNSIGHT", "클라우드 바우처", "업데이트 노트"],
)

GRAB = SourceConfig(
    name="Grab_Engineering",
    feed_url="https://engineering.grab.com/feed.xml",
    site_url="https://engineering.grab.com",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="Grab Engineering Blog. RSS listing + 개별 페이지 fetch. Backfill + incremental.",
)

GOOGLE_DEVS = SourceConfig(
    name="Google_Developers",
    feed_url="https://developers.googleblog.com/feeds/posts/default",
    site_url="https://developers.googleblog.com",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="Google Developers Blog. Atom listing + 개별 페이지 fetch. Backfill + incremental.",
)

KAKAOPAY = SourceConfig(
    name="KakaoPay_Tech",
    feed_url="https://tech.kakaopay.com/rss",
    site_url="https://tech.kakaopay.com",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="카카오페이 기술블로그. RSS listing + 개별 페이지 fetch. Backfill + incremental.",
    title_blocklist=["모집", "채용", "공채", "인턴"],
)

NEXTJS_BLOG = SourceConfig(
    name="Nextjs_Blog",
    feed_url="https://nextjs.org/feed.xml",
    site_url="https://nextjs.org/blog",
    parser_type="backfill",
    content_level=1,
    active=True,
    note="Next.js 공식 블로그. RSS listing + 개별 페이지 fetch. Backfill + incremental.",
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
        MEDIUM_AIRBNB,
        MEDIUM_PINTEREST,
        MEDIUM_GCCOMPANY,
        MEDIUM_FLUTTER,
        WOOWAHAN,
        META_ENGINEERING,
        CLOUDFLARE,
        SOCAR,
        GITHUB_BLOG,
        AWS_KOREA,
        SPRING_IO,
        SK_PLANET,
        NONGSHIM_CLOUD,
        MS_DEVBLOGS,
        NVIDIA_DEV,
        FLEX_TEAM,
        GRAB,
        GOOGLE_DEVS,
        KAKAOPAY,
        NEXTJS_BLOG,
        STACKOVERFLOW,
        VELOG,
    ]


# ---------------------------------------------------------------------------
# Backward-compatibility aliases (used by existing scripts during migration)
# ---------------------------------------------------------------------------


def get_backfill_sources() -> list[SourceConfig]:
    """Alias for get_all_sources() — kept for backward compatibility."""
    return get_all_sources()
