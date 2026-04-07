#!/usr/bin/env python3
"""사이트별 연도별 글 개수 조회."""

import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from xml.etree import ElementTree

import feedparser
import requests

UA = "DevPickAI-Counter/1.0"
SESS = requests.Session()
SESS.headers["User-Agent"] = UA


def _get(url, **kwargs):
    try:
        r = SESS.get(url, timeout=15, **kwargs)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return None


def _print_counts(counts: dict, note: str = ""):
    if not counts:
        print("  데이터 없음")
        return
    total = sum(counts.values())
    for year in sorted(counts):
        print(f"  {year}: {counts[year]}개")
    suffix = f" ({note})" if note else ""
    print(f"  합계: {total}개{suffix}")


def count_rss(name, feed_url, note="RSS 최신 글만"):
    print(f"\n[{name}]")
    counts = defaultdict(int)
    r = _get(feed_url)
    if not r:
        return
    parsed = feedparser.parse(r.text)
    for entry in parsed.entries:
        pub = entry.get("published") or entry.get("updated") or ""
        m = re.search(r"\b(202\d)\b", pub)
        if m:
            counts[m.group(1)] += 1
    _print_counts(counts, note)


def count_naver_d2():
    print("\n[NAVER D2] REST API 전체 페이지네이션")
    counts = defaultdict(int)
    page = 0
    while True:
        r = _get(
            "https://d2.naver.com/api/v1/contents",
            params={"page": page, "size": 20},
        )
        if not r:
            break
        data = r.json()
        items = data.get("content", [])
        if not items:
            break
        for item in items:
            ts = item.get("postPublishedAt", 0)
            if ts:
                year = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).year
                counts[year] += 1
        links = {link["rel"]: link for link in data.get("links", [])}
        if "next" not in links:
            break
        page += 1
        time.sleep(0.3)
    _print_counts(counts, "전체")


def count_lycorp():
    print("\n[LY Corp] 사이트맵 전체")
    counts = defaultdict(int)
    r = _get("https://techblog.lycorp.co.jp/sitemap-0.xml")
    if not r:
        return
    root = ElementTree.fromstring(r.content)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    for url_elem in root.findall("s:url", ns):
        loc = url_elem.findtext("s:loc", namespaces=ns) or ""
        lastmod = url_elem.findtext("s:lastmod", namespaces=ns) or ""
        if "/ko/" in loc and lastmod:
            m = re.match(r"(\d{4})", lastmod)
            if m:
                counts[m.group(1)] += 1
    _print_counts(counts, "전체")


def count_toss():
    """Toss Tech 리스팅 페이지 pagination — 날짜는 href slug에서 추출 불가, article 페이지에서만 확인 가능.
    대신 RSS로 확인하되, 전체 개수는 마지막 페이지 번호로 추정."""
    print("\n[Toss Tech]")
    # RSS로 연도 분포 확인
    counts = defaultdict(int)
    r = _get("https://toss.tech/rss.xml")
    if not r:
        return
    parsed = feedparser.parse(r.text)
    for entry in parsed.entries:
        pub = entry.get("published") or entry.get("updated") or ""
        m = re.search(r"\b(202\d)\b", pub)
        if m:
            counts[m.group(1)] += 1

    # 리스팅 마지막 페이지 번호 탐색 (전체 글 수 추정)
    total_articles = None
    for pg in range(1, 50):
        resp = _get("https://toss.tech", params={"page": pg})
        if not resp:
            break
        hrefs = re.findall(r'href="(/article/[^"]+)"', resp.text)
        if not hrefs:
            total_articles = (pg - 1) * 10  # 페이지당 약 10개
            break
        time.sleep(0.3)

    note = "RSS 최신 글만"
    if total_articles:
        note += f" / 전체 추정 ~{total_articles}개"
    _print_counts(counts, note)


def count_woowahan():
    print("\n[우아한형제들]")
    counts = defaultdict(int)
    # WordPress RSS — 최대 글 수 파라미터 시도
    r = _get("https://techblog.woowahan.com/feed", params={"posts_per_page": 100})
    if not r:
        return
    parsed = feedparser.parse(r.text)
    for entry in parsed.entries:
        pub = entry.get("published") or entry.get("updated") or ""
        m = re.search(r"\b(202\d)\b", pub)
        if m:
            counts[m.group(1)] += 1
    _print_counts(counts, "RSS 최신 글만")


def main():
    print("=" * 50)
    print("사이트별 연도별 글 개수")
    print("=" * 50)

    count_naver_d2()
    count_rss("Kakao Tech", "https://tech.kakao.com/feed/", "RSS 최신 글만")
    count_toss()
    count_rss(
        "OliveYoung Tech", "https://oliveyoung.tech/rss.xml", "RSS 전체 (182개 포함)"
    )
    count_lycorp()
    count_woowahan()
    count_rss("Medium_daangn", "https://medium.com/feed/daangn", "RSS 최신 글만")
    count_rss(
        "Medium_coupang", "https://medium.com/feed/coupang-engineering", "RSS 최신 글만"
    )
    count_rss("Medium_musinsa", "https://medium.com/feed/musinsa-tech", "RSS 최신 글만")
    count_rss("Medium_watcha", "https://medium.com/feed/watcha", "RSS 최신 글만")
    count_rss("Medium_zigbang", "https://medium.com/feed/zigbang", "RSS 최신 글만")

    print("\n" + "=" * 50)
    print("주의: RSS 기반 결과는 피드에 포함된 최신 글만 집계됨.")
    print("NAVER D2 / LY Corp 은 전체 글 기준.")


if __name__ == "__main__":
    main()
