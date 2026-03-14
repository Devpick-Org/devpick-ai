"""PreprocessService 실 출력 확인 스크립트 (DP-216 검증)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Windows 터미널 인코딩 대응
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services.preprocess_service import PreprocessService

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def fetch_html(url: str) -> str:
    """URL에서 HTML을 가져온다."""
    try:
        resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=15)
        resp.raise_for_status()
    except requests.HTTPError as e:
        print(f"HTTP 오류: {e}")
        sys.exit(1)
    except requests.Timeout:
        print(f"타임아웃: {url}")
        sys.exit(1)
    except requests.RequestException as e:
        print(f"요청 실패: {e}")
        sys.exit(1)
    return resp.text


def _run_single(
    html: str,
    hostname: str,
    chars: int,
    full: bool,
    suffix: str = "",
    show_preview: bool = True,
) -> None:
    """전처리 실행 → 저장 → 출력 공통 로직."""
    original_len = len(html)

    service = PreprocessService()
    try:
        result = service.preprocess(html)
    except ValueError as e:
        print(f"전처리 실패: {e}")
        sys.exit(1)

    result_len = len(result)

    out_dir = PROJECT_ROOT / "data" / "preprocessed"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{ts}_{hostname}{suffix}.txt"
    out_path.write_text(result, encoding="utf-8")
    print(f"저장: data/preprocessed/{out_path.name}")

    print(f"  원본 길이   : {original_len:,} chars")
    print(f"  전처리 후   : {result_len:,} chars")
    print(f"  압축률      : {result_len / original_len * 100:.1f}%")

    has_heading = "##" in result or "# " in result
    has_code = "```" in result
    print(f"  ## 헤딩 마커 : {'있음' if has_heading else '없음'} / ``` 코드블록 : {'있음' if has_code else '없음'}")

    if show_preview:
        print("\n" + "=" * 60)
        if full:
            print(result)
        else:
            print(result[:chars])
            if result_len > chars:
                print(f"\n... (이후 {result_len - chars:,} chars 생략, --full 로 전체 출력)")


def run_url(url: str, chars: int, full: bool) -> None:
    """HTML 가져오기 → PreprocessService 실행 → 결과 출력."""
    print(f"URL: {url}")
    html = fetch_html(url)
    hostname = urlparse(url).hostname or "unknown"
    _run_single(html, hostname, chars, full, show_preview=True)


def run_from_raw(json_path: Path, chars: int, full: bool, max_entries: int) -> None:
    """피드 JSON → 엔트리별 PreprocessService 실행."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    raw_xml = data["raw_xml"]
    hostname = urlparse(data["meta"]["feed_url"]).hostname or "unknown"

    soup = BeautifulSoup(raw_xml, "xml")
    entries = soup.find_all("entry") or soup.find_all("item")

    if not entries:
        print("엔트리를 찾을 수 없습니다.")
        sys.exit(1)

    total = min(len(entries), max_entries)
    print(f"피드: {json_path.name}  |  호스트: {hostname}  |  엔트리: {len(entries)}개 중 {total}개 처리\n")

    for i, entry in enumerate(entries[:total]):
        html_node = entry.find("content") or entry.find("description")
        if not html_node:
            print(f"[entry {i}] <content>/<description> 없음, 건너뜀")
            continue
        html_text = html_node.get_text()
        print(f"[entry {i}]", end=" ")
        _run_single(html_text, hostname, chars, full, suffix=f"_entry{i}", show_preview=False)
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PreprocessService 실 출력 확인 (DP-216 검증)"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="확인할 페이지 URL (SSR/정적 사이트 전용)")
    group.add_argument(
        "--raw",
        metavar="JSON_FILE",
        help="피드 JSON 파일 경로 (data/raw/feeds/.../*.json)",
    )
    parser.add_argument(
        "--chars", type=int, default=2000, help="미리보기 글자 수 (기본 2000, --url 모드)"
    )
    parser.add_argument("--full", action="store_true", help="전체 출력 (--url 모드)")
    parser.add_argument(
        "--max-entries",
        type=int,
        default=3,
        metavar="N",
        help="--raw 모드에서 처리할 최대 엔트리 수 (기본 3)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.url:
        run_url(args.url, args.chars, args.full)
    else:
        run_from_raw(Path(args.raw), args.chars, args.full, args.max_entries)
