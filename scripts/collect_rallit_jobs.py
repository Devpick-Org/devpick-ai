#!/usr/bin/env python3
"""랠릿 채용 공고를 크롤링해 Spring `POST /internal/jobs/ingest` 로 넣습니다.

필수 환경 변수 (실제 ingest 시):
  BACKEND_URL   예: https://3-39-96-126.sslip.io/v1 (Nginx에서 /v1 로 스프링에 프록시되는 경우)
  INTERNAL_KEY 또는 INTERNAL_API_KEY  Spring `ai.server.internal-key` 와 동일 (X-Internal-Key)

선택:
  RALLIT_HUB_URL  기본: 개발자 직군 목록 1페이지
  MAX_JOBS         기본 200
  MAX_HUB_PAGES    목록 페이지 수( pageNumber ), 기본 15 (페이지당 ~20건 가정)

예:
  python scripts/collect_rallit_jobs.py --dry-run --max 10 --pages 1
  python scripts/collect_rallit_jobs.py --url '...DEVELOPER&pageNumber=1' --max 200 --pages 15

재수집(jdImageUrls·메타 갱신, sourceUrl 동일하면 같은 행 업데이트):
  export BACKEND_URL='https://배포-API-루트'   # 예: https://xxx.sslip.io 또는 /v1 포함 시 그대로
  export INTERNAL_KEY='Spring ai.server.internal-key 와 동일'
  python scripts/collect_rallit_jobs.py --urls-file job_urls.txt --max 500

  job_urls.txt 는 한 줄에 하나씩 랠릿 상세 URL (DB job_postings.source_url 과 같을 것)

사이트 마크업·Next 데이터 구조가 바뀌면 URL/메타 추출 로직을 수정해야 합니다.

ingest 페이로드:
  jdImageUrls — 텍스트 JD가 부족할 때만 전송 (주요 업무·우대·복지 등이 비었을 때).
    랠릿은 position.content 의 <img> 만 jdImageUrls 후보로 쓴다.
    companyRepresentativeImages·og:image 등 회사 대표/랜딩 이미지는 절대 넣지 않는다
    (content 에 이미지가 없으면 빈 배열을 보내 DB 의 잘못된 jdImageUrls 도 비움).
    본문 텍스트가 충분하면 빈 배열을 보내 옛 이미지 URL 도 비움.
  imageOnlyJd — 위와 같이 이미지가 필요한데 URL이 있으면 True (AI 파싱 생략)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

DEFAULT_LIST_URL = "https://www.rallit.com/?jobGroup=DEVELOPER&pageNumber=1"
DEFAULT_MAX_JOBS = 200
DEFAULT_MAX_HUB_PAGES = 15

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">([^<]+)</script>'
)

# 실제 공고 상세만 (/positions/숫자/…). /client/api/v1/position 등은 제외
POSITION_ID_IN_PATH = re.compile(
    r"/(?:hub/)?positions?/(\d+)(?:/[^/?#]*)?", re.IGNORECASE
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
    if "/api/" in path.lower():
        return None
    m = POSITION_ID_IN_PATH.search(path)
    if not m:
        return None
    # 슬러그만 다른 동일 공고는 /positions/{id} 로 통일
    return f"{parsed.scheme}://{parsed.netloc}/positions/{m.group(1)}"


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


def hub_url_with_page(hub_url: str, page: int) -> str:
    u = urlparse(hub_url)
    q = parse_qs(u.query, keep_blank_values=True)
    q["pageNumber"] = [str(page)]
    pairs = [(k, v) for k in sorted(q.keys()) for v in q[k]]
    return urlunparse((u.scheme, u.netloc, u.path or "/", "", urlencode(pairs), ""))


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


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def html_to_text(html: str | None) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return _clean_text(soup.get_text(" ", strip=True))


def lines_from_html(html: str | None, max_lines: int = 20) -> list[str]:
    """랠릿 상세의 HTML 섹션을 ingest/AI가 읽기 쉬운 문장 목록으로 변환합니다."""
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    lines: list[str] = []
    for node in soup.find_all(["li", "p"]):
        txt = _clean_text(node.get_text(" ", strip=True))
        if not txt:
            continue
        # <li><p>...</p></li> 구조에서 부모/자식 텍스트가 중복되는 것을 방지
        if any(txt == prev or txt in prev for prev in lines[-3:]):
            continue
        lines.append(txt)
        if len(lines) >= max_lines:
            break
    if not lines:
        txt = html_to_text(html)
        if txt:
            lines.append(txt)
    return lines[:max_lines]


def _absolute_image_url(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None
    if s.startswith("//"):
        return "https:" + s
    return urljoin("https://www.rallit.com", s)


def _img_urls_from_html_fragment(html: str) -> list[str]:
    """랠릿 position.content 등 HTML 조각에서 <img src> 를 순서대로 수집."""
    if not html or not isinstance(html, str):
        return []
    soup = BeautifulSoup(html, "lxml")
    out: list[str] = []
    for img in soup.find_all("img"):
        src = _absolute_image_url(str(img.get("src") or ""))
        if src:
            out.append(src)
    return out


def _meta_content(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        if tag and tag.get("content"):
            return str(tag["content"]).strip()
    return ""


def meta_from_html(html: str) -> dict:
    """__NEXT_DATA__가 바뀌었을 때를 대비한 HTML fallback."""
    soup = BeautifulSoup(html, "lxml")
    out = {
        "title": "",
        "companyName": "",
        "companyLogoUrl": None,
        "representativeImageUrl": None,
        "canonicalUrl": "",
    }
    og_title = _meta_content(soup, "og:title", "title")
    if og_title:
        # "(주)비바리퍼블리카 [토스인슈어런스] Server Developer 채용 - 랠릿"
        out["title"] = re.sub(r"\s*채용\s*-\s*랠릿\s*$", "", og_title).strip()
    out["representativeImageUrl"] = _absolute_image_url(
        _meta_content(soup, "og:image", "twitter:image", "thumbnail")
    )
    out["canonicalUrl"] = _meta_content(soup, "og:url", "twitter:url")

    for img in soup.find_all("img"):
        alt = str(img.get("alt") or "")
        src = _absolute_image_url(str(img.get("src") or ""))
        if not src:
            continue
        if "로고" in alt:
            out["companyLogoUrl"] = src
            out["companyName"] = (
                alt.replace("로고 이미지", "").replace("로고", "").strip()
            )
            break
    return out


def pick_position_object(data: dict | None) -> dict:
    """랠릿 상세의 position 객체를 구조 변경에 견고하게 찾습니다."""
    if not data:
        return {}
    props = data.get("props", {}).get("pageProps", {})
    direct = props.get("position")
    if isinstance(direct, dict):
        return direct

    found: dict = {}

    def visitor(obj) -> None:
        nonlocal found
        if found or not isinstance(obj, dict):
            return
        if (
            isinstance(obj.get("title"), str)
            and isinstance(obj.get("companyName"), str)
            and ("jobSkillKeywords" in obj or "companyLogo" in obj)
        ):
            found = obj

    def walk(obj) -> None:
        if found:
            return
        if isinstance(obj, dict):
            visitor(obj)
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(props)
    return found


def map_job_category_from_position(job: dict, list_url: str) -> str:
    jobs = job.get("jobs") or []
    labels: list[str] = []
    if isinstance(jobs, list):
        for item in jobs:
            if isinstance(item, dict):
                labels.extend(
                    str(item.get(k) or "") for k in ("code", "name") if item.get(k)
                )
            elif isinstance(item, str):
                labels.append(item)
    hay = " ".join(labels + [str(job.get("title") or "")]).lower()
    if any(x in hay for x in ("frontend", "front-end", "프론트")):
        return "FRONTEND"
    if any(x in hay for x in ("backend", "back-end", "server", "서버", "백엔드")):
        return "BACKEND"
    if any(x in hay for x in ("fullstack", "full-stack", "풀스택")):
        return "FULLSTACK"
    if any(x in hay for x in ("devops", "infra", "sre", "인프라", "mlops")):
        return "DEVOPS"
    if any(x in hay for x in ("ai", "ml", "machine", "data scientist", "데이터")):
        return "AI_ML"
    if any(x in hay for x in ("android", "ios", "mobile", "모바일", "aos")):
        return "MOBILE"
    return default_job_category_from_list_url(list_url)


def map_experience_from_position(job: dict) -> str:
    levels = job.get("jobLevels")
    if isinstance(levels, list) and levels:
        order = ["SENIOR", "MIDDLE", "JUNIOR", "NEW"]
        upper = {str(x).upper() for x in levels}
        for item in order:
            if item in upper:
                return item
    raw = str(job.get("jobLevel") or job.get("experience") or "")
    if raw.upper() == "IRRELEVANT":
        return "ANY"
    if raw:
        return map_experience_hint(raw)
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
        "jobCategory": "",
        "salaryDisplay": None,
        "deadline": None,
        "representativeImageUrl": None,
        "canonicalUrl": "",
        "responsibilities": [],
        "requirements": [],
        "preferredQualifications": [],
        "benefits": [],
        "hiringProcess": [],
        "allRepresentativeImageUrls": [],
        "contentHtmlImageUrls": [],
    }
    if not data:
        return out
    try:
        props = data.get("props", {}).get("pageProps", {})
        job = (
            pick_position_object(data)
            or props.get("job")
            or props.get("jobDetail")
            or props.get("data")
            or {}
        )
        if not isinstance(job, dict):
            job = {}

        out["title"] = _first_str(job, ("title",), ("name",), ("jobTitle",))
        out["companyName"] = _first_str(job, ("companyName",))

        company = job.get("company") or job.get("team") or job.get("employer") or {}
        if isinstance(company, dict):
            out["companyName"] = out["companyName"] or _first_str(
                company, ("name",), ("title",), ("companyName",)
            )
            logo = (
                company.get("logoUrl") or company.get("logo") or company.get("imageUrl")
            )
            if isinstance(logo, str) and logo.strip():
                out["companyLogoUrl"] = _absolute_image_url(logo.strip())
            elif isinstance(logo, dict):
                url = logo.get("url") or logo.get("src")
                if isinstance(url, str) and url.strip():
                    out["companyLogoUrl"] = _absolute_image_url(url.strip())
        if not out["companyLogoUrl"]:
            out["companyLogoUrl"] = _absolute_image_url(
                job.get("companyLogo") or job.get("partnerLogo")
            )
        images = job.get("companyRepresentativeImages")
        if isinstance(images, list) and images:
            rep_urls: list[str] = []
            for x in images[:12]:
                au = _absolute_image_url(str(x))
                if au:
                    rep_urls.append(au)
            out["allRepresentativeImageUrls"] = rep_urls
            if rep_urls:
                out["representativeImageUrl"] = rep_urls[0]

        out["applyUrl"] = _first_str(
            job, ("applyUrl",), ("applicationUrl",), ("externalApplyUrl",)
        )
        if not out["applyUrl"]:
            out["applyUrl"] = _first_str(job, ("url",))

        loc = (
            job.get("location")
            or job.get("region")
            or job.get("workPlace")
            or job.get("addressMain")
        )
        if isinstance(loc, str) and loc.strip():
            detail = str(job.get("addressDetail") or "").strip()
            out["location"] = _clean_text(f"{loc.strip()} {detail}".strip())
        elif isinstance(loc, dict):
            out["location"] = _first_str(loc, ("name",), ("label",))

        exp = job.get("experience") or job.get("career") or job.get("grade")
        if isinstance(exp, str) and exp.strip():
            out["experienceLevel"] = map_experience_hint(exp)
        elif isinstance(exp, dict):
            label = _first_str(exp, ("name",), ("label",), ("type",))
            out["experienceLevel"] = map_experience_hint(label)
        if not out["experienceLevel"]:
            out["experienceLevel"] = map_experience_from_position(job)
        out["jobCategory"] = map_job_category_from_position(job, DEFAULT_LIST_URL)

        sal = (
            job.get("salary")
            or job.get("salaryDescription")
            or job.get("minimumSalary")
        )
        if isinstance(sal, str) and sal.strip():
            out["salaryDisplay"] = sal.strip()
        elif sal is not None:
            out["salaryDisplay"] = str(sal)

        dl = (
            job.get("deadline")
            or job.get("endDate")
            or job.get("closeDate")
            or job.get("endedAt")
        )
        if (
            isinstance(dl, str)
            and re.match(r"\d{4}-\d{2}-\d{2}", dl.strip())
            and not dl.startswith("9999")
        ):
            out["deadline"] = dl.strip()[:10]

        skills = (
            job.get("skills")
            or job.get("techStack")
            or job.get("stacks")
            or job.get("tags")
            or job.get("jobSkillKeywords")
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
        out["responsibilities"] = lines_from_html(job.get("responsibilities"))
        out["requirements"] = lines_from_html(job.get("basicQualifications"))
        out["preferredQualifications"] = lines_from_html(
            job.get("preferredQualifications")
        )
        out["benefits"] = lines_from_html(job.get("benefits"))
        content_html = job.get("content")
        if isinstance(content_html, str) and content_html.strip():
            out["contentHtmlImageUrls"] = _img_urls_from_html_fragment(content_html)
        steps = job.get("positionSteps")
        if isinstance(steps, list):
            middle_steps = [str(s).strip() for s in steps if str(s).strip()]
            out["hiringProcess"] = ["서류 접수", *middle_steps, "최종 합격"]
        out["canonicalUrl"] = _first_str(job, ("url",))
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


# 자격 요건 한 줄이 이보다 길면 문장형 JD로 보고 이미지 수집 생략 (스킬 키워드만 있는 경우 구분)
MIN_REQUIREMENT_LINE_FOR_PROSE = 45
# 주요업무·우대·복지·긴 자격 줄이 없을 때: main 전체 평문이 이 길이 이상이면 텍스트 JD로 인정.
# 120자 같은 낮은 기준은 푸터·유사공고·내비 잡음만으로도 True 가 되어 이미지 JD를 놓침 (예: rawLen ~2k).
MIN_FALLBACK_PLAIN_TEXT_WHEN_UNSTRUCTURED = 4200


def _has_substantive_jd(meta: dict, jd_plain: str) -> bool:
    """HTML에서 뽑은 텍스트·구조화 필드만으로 공고 본문이 충분한지."""
    for key in ("responsibilities", "preferredQualifications", "benefits"):
        lst = meta.get(key)
        if isinstance(lst, list) and any(isinstance(x, str) and x.strip() for x in lst):
            return True
    req = meta.get("requirements") or []
    if isinstance(req, list):
        for x in req:
            if isinstance(x, str) and len(x.strip()) >= MIN_REQUIREMENT_LINE_FOR_PROSE:
                return True
    jd_len = len((jd_plain or "").strip())
    return jd_len >= MIN_FALLBACK_PLAIN_TEXT_WHEN_UNSTRUCTURED


def _needs_jd_images(meta: dict, jd_plain: str) -> bool:
    """본문 텍스트 JD가 부족할 때만 jdImageUrls(본문 이미지)를 채운다."""
    return not _has_substantive_jd(meta, jd_plain)


def merge_jd_image_urls(meta: dict) -> list[str]:
    """ingest용 JD 이미지 URL: 랠릿 `position.content` 의 <img> 만 사용.

    회사 대표·og:image·랜딩 캡처는 공고 본문이 아니므로 폴백으로 넣지 않는다.
    content 에 이미지가 없으면 빈 리스트(재수집 시 DB jdImageUrls 클리어).
    """
    seen: set[str] = set()
    out: list[str] = []
    for u in meta.get("contentHtmlImageUrls") or []:
        if not isinstance(u, str):
            continue
        t = u.strip()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out[:10]


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
    # 랠릿 position.jobSkillKeywords가 있으면 그것이 정본입니다.
    # 본문 fallback은 유사 공고 영역까지 포함될 수 있어 정본이 없을 때만 사용합니다.
    jd_hints = [] if meta_hints else tech_hints_from_jd_text(jd_text)
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
    need_imgs = _needs_jd_images(meta, jd_text)
    jd_urls = merge_jd_image_urls(meta) if need_imgs else []
    image_only_jd = bool(need_imgs and jd_urls)
    return {
        "sourceUrl": detail_url,
        "companyName": meta.get("companyName") or "unknown",
        "companyLogoUrl": meta.get("companyLogoUrl"),
        "title": meta.get("title") or "제목 미상",
        "employmentType": "FULL_TIME",
        "jobCategory": meta.get("jobCategory")
        or default_job_category_from_list_url(list_url),
        "experienceLevel": exp,
        "location": meta.get("location") or "",
        "salaryDisplay": meta.get("salaryDisplay"),
        "deadline": meta.get("deadline"),
        "applyUrl": meta.get("applyUrl") or detail_url,
        "rawJdText": jd_text,
        "imageOnlyJd": image_only_jd,
        "requiredSkills": merged,
        "preferredSkills": [],
        # 백엔드가 확장되면 아래 구조화 필드를 그대로 저장할 수 있습니다.
        "responsibilities": meta.get("responsibilities") or [],
        "requirements": meta.get("requirements") or [],
        "preferredQualifications": meta.get("preferredQualifications") or [],
        "benefits": meta.get("benefits") or [],
        "hiringProcess": meta.get("hiringProcess") or [],
        "jdImageUrls": jd_urls,
    }


def load_urls_from_file(path: str) -> list[str]:
    """한 줄에 공고 URL 하나. 빈 줄·# 로 시작하는 줄은 무시."""
    out: list[str] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            out.append(s)
    return out


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
        "--pages",
        type=int,
        default=int(os.environ.get("MAX_HUB_PAGES", str(DEFAULT_MAX_HUB_PAGES))),
        help="랠릿 목록 pageNumber 1…N 까지 순회 (공고 URL 합산 후 --max 로 자름)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="ingest 없이 페이로드만 stdout JSON으로 출력",
    )
    parser.add_argument(
        "--urls-file",
        default=None,
        metavar="PATH",
        help="한 줄에 랠릿 상세 URL 하나. 지정 시 허브 목록(--url/--pages)은 사용하지 않음 (백필·재수집용)",
    )
    parser.add_argument(
        "--list-urls-only",
        action="store_true",
        help="공고 상세 URL만 stdout에 한 줄씩 출력하고 종료 (ingest 없음, BACKEND 불필요). "
        "허브(--url/--pages/--max) 또는 --urls-file(정규화·출력)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="발견 URL·메타 요약을 stderr에 출력",
    )
    args = parser.parse_args()

    base = os.environ.get("BACKEND_URL", "").rstrip("/")
    key = os.environ.get("INTERNAL_KEY") or os.environ.get("INTERNAL_API_KEY", "")
    if not args.dry_run and not args.list_urls_only:
        if not base or not key:
            print(
                "BACKEND_URL and INTERNAL_KEY (or INTERNAL_API_KEY) are required (or use --dry-run)",
                file=sys.stderr,
            )
            return 1

    sess = _session()

    if args.urls_file:
        try:
            collected = load_urls_from_file(args.urls_file)
        except OSError as exc:
            print("--urls-file read failed:", exc, file=sys.stderr)
            return 2
        norm_base = args.url or DEFAULT_LIST_URL
        seen_nf: set[str] = set()
        normalized: list[str] = []
        for raw in collected:
            nu = _normalize_job_url(raw, norm_base) or raw.strip()
            if nu and nu not in seen_nf:
                seen_nf.add(nu)
                normalized.append(nu)
        urls = normalized[: max(1, args.max)]
    else:
        per_page_cap = max(args.max * 2, 120)
        collected: list[str] = []
        seen_urls: set[str] = set()
        for page in range(1, max(1, args.pages) + 1):
            hub_page_url = hub_url_with_page(args.url, page)
            try:
                hub_resp = sess.get(hub_page_url, timeout=60)
                hub_resp.raise_for_status()
            except Exception as exc:
                print(f"list fetch failed (page {page}):", exc, file=sys.stderr)
                if page == 1:
                    return 2
                break
            batch = discover_job_urls(hub_resp.text, hub_page_url, per_page_cap)
            if not batch:
                break
            for u in batch:
                if u not in seen_urls:
                    seen_urls.add(u)
                    collected.append(u)
                    if len(collected) >= args.max:
                        break
            if len(collected) >= args.max:
                break

        urls = collected[: args.max]
    if args.debug:
        print(f"[debug] discovered {len(urls)} urls:", file=sys.stderr)
        for u in urls:
            print(" ", u, file=sys.stderr)

    if args.list_urls_only:
        if not urls:
            print(
                "no job urls found — rallit markup may have changed",
                file=sys.stderr,
            )
            return 3
        for u in urls:
            print(u)
        return 0

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
            skills_for_debug = (payload.get("requiredSkills") or []) + (
                payload.get("preferredSkills") or []
            )
            print(
                f"[debug] {u} title={payload['title']!r} "
                f"company={payload['companyName']!r} "
                f"skills={skills_for_debug!r}",
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
