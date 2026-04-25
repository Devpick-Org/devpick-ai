#!/usr/bin/env python3
"""랠릿 채용 공고를 크롤링해 Spring `POST /internal/jobs/ingest` 로 넣습니다.

필수 환경 변수 (실제 ingest 시):
  BACKEND_URL   예: https://api.example.com/v1
  INTERNAL_KEY  Spring `ai.server.internal-key` 와 동일 (X-Internal-Key)

선택:
  RALLIT_HUB_URL  기본: 개발자 직군 목록 1페이지
  MAX_JOBS        기본 5

예:
  python scripts/collect_rallit_jobs.py --dry-run --max 3
  python scripts/collect_rallit_jobs.py --url 'https://www.rallit.com/?jobGroup=DEVELOPER&pageNumber=1' --max 5

사이트 마크업·Next 데이터 구조가 바뀌면 URL/메타 추출 로직을 수정해야 합니다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

DEFAULT_LIST_URL = "https://www.rallit.com/?jobGroup=DEVELOPER&pageNumber=1"
DEFAULT_MAX_JOBS = 5

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">([^<]+)</script>'
)

# 공고 상세로 이어지는 경로 (목록·히드레이션 JSON 어디에든 등장 가능)
JOB_PATH_PATTERN = re.compile(
    r"/(?:hub/)?(?:positions?|position)(?:/[^/?#]+)?",
    re.IGNORECASE,
)


def _session():
    return curl_requests.Session(impersonate="chrome")


def _normalize_job_url(raw: str, base_url: str) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if s.startswith("//"):
        s = "https:" + s
    full = urljoin(base_url, s)
    parsed = urlparse(full)
    if "rallit.com" not in (parsed.netloc or "").lower():
        return None
    path = parsed.path or ""
    if not JOB_PATH_PATTERN.search(path):
        return None
    # 쿼리 제거·슬래시 정리
    out = f"{parsed.scheme}://{parsed.netloc}{path.rstrip('/')}"
    return out


def _walk_json(obj, visitor) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            _walk_json(v, visitor)
    elif isinstance(obj, list):
        for item in obj:
            _walk_json(item, visitor)
    else:
        visitor(obj)


def urls_from_next_data(data: dict | None, hub_url: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    def visitor(x) -> None:
        if not isinstance(x, str):
            return
        nu = _normalize_job_url(x, hub_url)
        if nu and nu not in seen:
            seen.add(nu)
            out.append(nu)

    if data:
        _walk_json(data, visitor)
    return out


def discover_job_urls(hub_html: str, hub_url: str, max_jobs: int) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    def add(u: str) -> None:
        if u not in seen:
            seen.add(u)
            ordered.append(u)

    nxt = parse_next_props(hub_html)
    for u in urls_from_next_data(nxt, hub_url):
        add(u)
        if len(ordered) >= max_jobs:
            return ordered[:max_jobs]

    soup = BeautifulSoup(hub_html, "lxml")
    for a in soup.find_all("a", href=True):
        nu = _normalize_job_url(a["href"], hub_url)
        if nu:
            add(nu)
            if len(ordered) >= max_jobs:
                break

    return ordered[:max_jobs]


def extract_text_fallback(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    main = soup.find("main") or soup.body
    if not main:
        return ""
    return re.sub(r"\s+", " ", main.get_text(" ", strip=True))[:80_000]


def parse_next_props(html: str) -> dict | None:
    m = NEXT_DATA_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _first_str(d: dict | None, *paths: tuple[str, ...]) -> str:
    if not d:
        return ""
    for path in paths:
        cur: object = d
        ok = True
        for key in path:
            if not isinstance(cur, dict):
                ok = False
                break
            cur = cur.get(key)  # type: ignore[assignment]
        if ok and isinstance(cur, str) and cur.strip():
            return cur.strip()
    return ""


def meta_from_next(data: dict | None) -> dict:
    """__NEXT_DATA__ pageProps 에서 회사·제목·로고·스킬 등 추출 (구조 변경 시 수정)."""
    out: dict = {
        "title": "",
        "companyName": "",
        "companyLogoUrl": None,
        "applyUrl": "",
        "techHints": [],
        "location": "",
        "experienceLevel": "",
        "salaryDisplay": None,
        "deadline": None,
    }
    if not data:
        return out
    try:
        props = data.get("props", {}).get("pageProps", {})
        job = (
            props.get("job")
            or props.get("position")
            or props.get("jobDetail")
            or props.get("data")
            or {}
        )
        if not isinstance(job, dict):
            job = {}

        out["title"] = _first_str(job, ("title",), ("name",), ("jobTitle",))

        company = job.get("company") or job.get("team") or job.get("employer") or {}
        if isinstance(company, dict):
            out["companyName"] = _first_str(
                company, ("name",), ("title",), ("companyName",)
            )
            logo = (
                company.get("logoUrl")
                or company.get("logo")
                or company.get("imageUrl")
            )
            if isinstance(logo, str) and logo.strip():
                out["companyLogoUrl"] = logo.strip()
            elif isinstance(logo, dict):
                url = logo.get("url") or logo.get("src")
                if isinstance(url, str) and url.strip():
                    out["companyLogoUrl"] = url.strip()

        out["applyUrl"] = _first_str(
            job, ("applyUrl",), ("applicationUrl",), ("externalApplyUrl",)
        )
        if not out["applyUrl"]:
            out["applyUrl"] = _first_str(job, ("url",))

        loc = job.get("location") or job.get("region") or job.get("workPlace")
        if isinstance(loc, str) and loc.strip():
            out["location"] = loc.strip()
        elif isinstance(loc, dict):
            out["location"] = _first_str(loc, ("name",), ("label",))

        exp = job.get("experience") or job.get("career") or job.get("grade")
        if isinstance(exp, str) and exp.strip():
            out["experienceLevel"] = map_experience_hint(exp)
        elif isinstance(exp, dict):
            label = _first_str(exp, ("name",), ("label",), ("type",))
            out["experienceLevel"] = map_experience_hint(label)

        sal = job.get("salary") or job.get("salaryDescription")
        if isinstance(sal, str) and sal.strip():
            out["salaryDisplay"] = sal.strip()

        dl = job.get("deadline") or job.get("endDate") or job.get("closeDate")
        if isinstance(dl, str) and re.match(r"\d{4}-\d{2}-\d{2}", dl.strip()):
            out["deadline"] = dl.strip()[:10]

        skills = (
            job.get("skills")
            or job.get("techStack")
            or job.get("stacks")
            or job.get("tags")
            or []
        )
        if isinstance(skills, list):
            hints: list[str] = []
            for s in skills:
                if isinstance(s, str) and s.strip():
                    hints.append(s.strip())
                elif isinstance(s, dict):
                    name = s.get("name") or s.get("label") or s.get("skill")
                    if isinstance(name, str) and name.strip():
                        hints.append(name.strip())
            out["techHints"] = hints
    except (TypeError, AttributeError):
        pass
    return out


def tech_hints_from_jd_text(text: str, max_hints: int = 80) -> list[str]:
    """본문에 있는 `# 기술명` 태그 등을 추출해 AI 실패 시 백엔드 폴백용 힌트로 씁니다."""
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    _cuts = (" 주요업무", " 자격요건", " 우대사항", " 혜택", " 채용", " 근무 지역")
    for m in re.finditer(r"#\s*([^\#\n]+)", text):
        s = m.group(1).strip()
        for cut in _cuts:
            if cut in s:
                s = s.split(cut)[0].strip()
        s = s.rstrip(" ,，.")
        if len(s) < 2 or len(s) > 60:
            continue
        key = s.casefold()
        if key not in seen:
            seen.add(key)
            out.append(s)
        if len(out) >= max_hints:
            break
    return out


def map_experience_hint(text: str) -> str:
    """랠릿/한글 경력 표기를 PostingExperienceLevel 이름으로 대략 매핑."""
    t = text.lower()
    if "무관" in text or "경력무관" in text:
        return "ANY"
    if "인턴" in text:
        return "NEW"
    if "신입" in text or "1년이하" in text or "1년 이하" in text:
        return "NEW"
    if "주니어" in text or "1~3" in text or "1-3" in t:
        return "JUNIOR"
    if "미들" in text or "4~8" in text or "4-8" in t:
        return "MIDDLE"
    if "시니어" in text or "9년" in text or "lead" in t:
        return "SENIOR"
    return ""


def default_job_category_from_list_url(list_url: str) -> str:
    q = parse_qs(urlparse(list_url).query)
    jg = (q.get("jobGroup") or [""])[0].upper()
    if jg == "DEVELOPER":
        return "FULLSTACK"
    return "BACKEND"


def build_payload(
    detail_url: str,
    meta: dict,
    jd_text: str,
    list_url: str,
) -> dict:
    exp = meta.get("experienceLevel") or "ANY"
    if not exp:
        exp = "ANY"
    meta_hints = meta.get("techHints") or []
    jd_hints = tech_hints_from_jd_text(jd_text)
    merged: list[str] = []
    seen_m: set[str] = set()
    for h in list(meta_hints) + jd_hints:
        if not isinstance(h, str):
            continue
        t = h.strip()
        if not t:
            continue
        k = t.casefold()
        if k in seen_m:
            continue
        seen_m.add(k)
        merged.append(t)
    return {
        "sourceUrl": detail_url,
        "companyName": meta.get("companyName") or "unknown",
        "companyLogoUrl": meta.get("companyLogoUrl"),
        "title": meta.get("title") or "제목 미상",
        "employmentType": "FULL_TIME",
        "jobCategory": default_job_category_from_list_url(list_url),
        "experienceLevel": exp,
        "location": meta.get("location") or "",
        "salaryDisplay": meta.get("salaryDisplay"),
        "deadline": meta.get("deadline"),
        "applyUrl": meta.get("applyUrl") or detail_url,
        "rawJdText": jd_text,
        "imageOnlyJd": False,
        "requiredSkills": [],
        "preferredSkills": merged,
    }


def post_ingest(base: str, key: str, payload: dict) -> None:
    url = f"{base.rstrip('/')}/internal/jobs/ingest"
    r = requests.post(
        url,
        headers={"X-Internal-Key": key, "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    r.raise_for_status()


def main() -> int:
    parser = argparse.ArgumentParser(description="Rallit → DevPick job ingest")
    parser.add_argument(
        "--url",
        default=os.environ.get("RALLIT_HUB_URL", DEFAULT_LIST_URL),
        help="랠릿 목록(허브) URL",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=int(os.environ.get("MAX_JOBS", str(DEFAULT_MAX_JOBS))),
        help="최대 수집 공고 수",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="ingest 없이 페이로드만 stdout JSON으로 출력",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="발견 URL·메타 요약을 stderr에 출력",
    )
    args = parser.parse_args()

    base = os.environ.get("BACKEND_URL", "").rstrip("/")
    key = os.environ.get("INTERNAL_KEY", "")
    if not args.dry_run:
        if not base or not key:
            print(
                "BACKEND_URL and INTERNAL_KEY are required (or use --dry-run)",
                file=sys.stderr,
            )
            return 1

    sess = _session()
    try:
        hub_resp = sess.get(args.url, timeout=60)
        hub_resp.raise_for_status()
    except Exception as exc:
        print("list fetch failed:", exc, file=sys.stderr)
        return 2

    urls = discover_job_urls(hub_resp.text, args.url, args.max)
    if args.debug:
        print(f"[debug] discovered {len(urls)} urls:", file=sys.stderr)
        for u in urls:
            print(" ", u, file=sys.stderr)

    if not urls:
        print(
            "no job urls found — rallit markup may have changed",
            file=sys.stderr,
        )
        return 3

    for u in urls:
        try:
            resp = sess.get(u, timeout=60)
            resp.raise_for_status()
        except Exception as exc:
            print("skip", u, exc, file=sys.stderr)
            continue
        html = resp.text
        nxt = parse_next_props(html)
        meta = meta_from_next(nxt)
        jd_text = extract_text_fallback(html)
        payload = build_payload(u, meta, jd_text, args.url)

        if args.debug:
            print(
                f"[debug] {u} title={payload['title']!r} "
                f"company={payload['companyName']!r} "
                f"skills={payload['preferredSkills']!r}",
                file=sys.stderr,
            )

        if args.dry_run:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            try:
                post_ingest(base, key, payload)
                print("ingested", u)
            except Exception as exc:
                print("ingest failed", u, exc, file=sys.stderr)
        time.sleep(1.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
