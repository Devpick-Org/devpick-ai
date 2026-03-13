# CLAUDE.md — app/collectors/

수집기 레이어. 외부 피드에서 원시 데이터를 가져와 `RawEntry` 목록을 반환한다.

---

## 현재 수집기

| 파일 | 클래스 | 수집 방식 |
|------|--------|----------|
| `rss.py` | `RSSCollector` | RSS/Atom 피드 HTTP 요청 → XML 파싱 |
| `rss_crawl.py` | `RSSCrawlCollector` | RSS 피드 요청 후 각 항목 URL을 HTML 크롤링해 본문 보강 |
| `base.py` | `BaseCollector` | 공통 HTTP 요청 로직 (retry, timeout) |

---

## 수집기 인터페이스

```python
def collect(self, source: SourceConfig) -> tuple[RawFeedMeta, list[RawEntry], str]:
    ...
```

- `RawFeedMeta`: 피드 메타 (제목, URL, 수집 시각 등)
- `list[RawEntry]`: 수집된 개별 항목 목록
- `str`: 원본 XML 문자열 (raw 저장용)

`IngestService`와 `SupportsRawCollect` 프로토콜로 연결된다.

---

## 소스 레벨

| content_level | 수집기 | 설명 |
|---------------|--------|------|
| `2` | `RSSCollector` | RSS/Atom XML 본문만 사용 |
| `1` | `RSSCrawlCollector` | RSS + HTML 크롤링으로 본문 보강 |

---

## 수집기 작성 원칙

- 수집기는 외부 I/O만 담당한다. 저장/정규화 로직은 포함하지 않는다.
- 재시도 횟수(`max_retries`)와 타임아웃(`timeout`)은 생성자에서 주입한다.
- 개별 항목 파싱 실패는 해당 항목만 건너뛰고 계속 진행한다.
- `collect()` 반환 타입은 항상 `(RawFeedMeta, list[RawEntry], str)`을 지킨다.
