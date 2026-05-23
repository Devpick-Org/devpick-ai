#!/usr/bin/env python3
"""DB에 이미 넣어둔 랠릿 공고 소스 URL 목록만 다시 fetch → 동일 ingest API로 재수집합니다.

목적:
  jdImageUrls 초기화, 메타/HTML 갱신, 백엔드 JobIngest 변경(예: 우대 불릿 → preferredSkills) 반영 등.

환경 변수 (실행 시 필수):
  BACKEND_URL        Spring API 베이스 (예: https://호스트/v1)
  INTERNAL_KEY 또는 INTERNAL_API_KEY   X-Internal-Key 로 전달

예:
  export BACKEND_URL='https://...'
  export INTERNAL_KEY='...'
  python scripts/reingest_job_urls.py --urls-file job_urls.txt

  한 줄당 상세 페이지 URL 하나. # 로 시작하는 줄과 빈 줄은 무시.
  --dry-run 인 경우 ingest 대신 빌드된 페이로드 JSON 한 건만 stdout.

구현은 `collect_rallit_jobs.py`의 파서·페이로드 빌드를 그대로 씁니다.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path


def load_urls(path: Path) -> list[str]:
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


def load_collect_module():
    scripts_dir = Path(__file__).resolve().parent
    target = scripts_dir / "collect_rallit_jobs.py"
    spec = importlib.util.spec_from_file_location("collect_rallit_jobs", target)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {target}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["collect_rallit_jobs"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    parser = argparse.ArgumentParser(
        description="재수집: URL 목록 → 랠릿 fetch → /internal/jobs/ingest"
    )
    parser.add_argument(
        "--urls-file",
        required=True,
        metavar="PATH",
        help="상세 페이지 URL 목록 (한 줄에 하나)",
    )
    parser.add_argument(
        "--list-url",
        default=os.environ.get("RALLIT_HUB_URL", ""),
        help="카테고리 기본값용 목록 페이지 URL (--max 없음; collect 기본 카테고리와 동일)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="첫 URL만 처리해 ingest 페이로드 JSON 출력 (POST 안 함)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=float(os.environ.get("REINGEST_SLEEP", "1.0")),
        help="요청 사이 초 대기 (기본 1.0)",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="ingest 에러 나면 종료 코드 1",
    )
    args = parser.parse_args()

    rallit = load_collect_module()

    urls_path = Path(args.urls_file)
    if not urls_path.is_file():
        print("urls-file not found:", urls_path, file=sys.stderr)
        return 2

    base = os.environ.get("BACKEND_URL", "").rstrip("/")
    key = (
        os.environ.get("INTERNAL_KEY")
        or os.environ.get("INTERNAL_API_KEY")
        or os.environ.get("AI_SERVER_INTERNAL_KEY")
        or ""
    )

    if not args.dry_run and (not base or not key):
        print(
            "BACKEND_URL and INTERNAL_KEY required (unless --dry-run)", file=sys.stderr
        )
        return 1

    list_url = args.list_url.strip() or rallit.DEFAULT_LIST_URL
    urls = load_urls(urls_path)
    if not urls:
        print("no URLs after filtering", file=sys.stderr)
        return 3

    sess = rallit._session()
    errs = 0

    for i, u in enumerate(urls):
        try:
            resp = sess.get(u, timeout=60)
            resp.raise_for_status()
        except Exception as exc:
            print("skip fetch", u, exc, file=sys.stderr)
            errs += 1
            if args.fail_fast:
                return 10
            continue

        html = resp.text
        nxt = rallit.parse_next_props(html)
        meta = rallit.meta_from_next(nxt)
        html_meta = rallit.meta_from_html(html)
        for key_hint in ("title", "companyName", "companyLogoUrl", "canonicalUrl"):
            if not meta.get(key_hint) and html_meta.get(key_hint):
                meta[key_hint] = html_meta[key_hint]
        if not meta.get("deadline") and html_meta.get("deadline"):
            meta["deadline"] = html_meta["deadline"]
        if not meta.get("rollingDeadline") and html_meta.get("rollingDeadline"):
            meta["rollingDeadline"] = True

        jd_text = rallit.extract_text_fallback(html)
        payload = rallit.build_payload(u, meta, jd_text, list_url)

        if args.dry_run and i == 0:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        try:
            rallit.post_ingest(base, key, payload)
            print("reingested", u)
        except Exception as exc:
            print("ingest failed", u, exc, file=sys.stderr)
            errs += 1
            if args.fail_fast:
                return 11

        if i < len(urls) - 1 and args.sleep > 0:
            time.sleep(args.sleep)

    return 0 if errs == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
