# CLAUDE.md — app/utils/

수집/파싱 과정에서 사용하는 보조 유틸리티 함수 모음.

---

## 현재 파일

| 파일 | 역할 |
|------|------|
| `xml_helpers.py` | RSS/Atom XML 파싱 헬퍼 (feedparser 래핑, 필드 추출) |
| `html_helpers.py` | HTML 본문 추출 헬퍼 (BeautifulSoup 기반, 불필요 태그 제거) |

---

## html_helpers.py 주요 함수

| 함수 | 설명 |
|------|------|
| `html_to_text(html)` | HTML → 정규화 텍스트 |
| `extract_og_meta(html, prop)` | OG/meta 속성 추출 (og:title, og:image 등) |
| `extract_og_image(html)` | og:image / twitter:image 추출 (extract_og_meta 래핑) |
| `extract_article_body(html)` | `<article>` 태그 본문 추출 (noisy 태그 제거 포함) |
| `extract_jsonld_field(html, field)` | JSON-LD에서 필드 추출 (datePublished 등) |
| `extract_meta_author(html)` | `<meta name="author">` 추출 |
| `strip_wayback_prefix(url)` | Wayback Machine URL prefix 제거 |
| `extract_first_image(html)` | 본문 첫 번째 이미지 URL |
| `extract_kakao_article_body(html)` | 카카오 전용 본문 추출 (Nuxt payload fallback 포함) |

---

## 사용 위치

- `xml_helpers` → `RSSCollector`, `RSSCrawlCollector`
- `html_helpers` → `RSSCrawlCollector`, 모든 백필 크롤러 공통 사용

---

## 작성 원칙

- 순수 함수로 작성한다. 상태를 갖거나 외부 I/O를 직접 수행하지 않는다.
- 입력이 없거나 파싱 실패 시 예외 대신 `None` 또는 빈 값을 반환한다.
  (수집기가 항목 단위로 skip 여부를 결정)
- 함수명은 `extract_`, `parse_`, `clean_` 접두사로 의도를 명확히 한다.
