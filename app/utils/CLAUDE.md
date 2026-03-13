# CLAUDE.md — app/utils/

수집/파싱 과정에서 사용하는 보조 유틸리티 함수 모음.

---

## 현재 파일

| 파일 | 역할 |
|------|------|
| `xml_helpers.py` | RSS/Atom XML 파싱 헬퍼 (feedparser 래핑, 필드 추출) |
| `html_helpers.py` | HTML 본문 추출 헬퍼 (BeautifulSoup 기반, 불필요 태그 제거) |

---

## 사용 위치

- `xml_helpers` → `RSSCollector`, `RSSCrawlCollector`
- `html_helpers` → `RSSCrawlCollector` (HTML 크롤링 본문 정제)

---

## 작성 원칙

- 순수 함수로 작성한다. 상태를 갖거나 외부 I/O를 직접 수행하지 않는다.
- 입력이 없거나 파싱 실패 시 예외 대신 `None` 또는 빈 값을 반환한다.
  (수집기가 항목 단위로 skip 여부를 결정)
- 함수명은 `extract_`, `parse_`, `clean_` 접두사로 의도를 명확히 한다.
