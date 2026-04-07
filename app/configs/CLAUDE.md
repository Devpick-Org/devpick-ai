# CLAUDE.md — app/configs/

수집 대상 소스 목록을 관리한다.

---

## 현재 파일

| 파일 | 내용 |
|------|------|
| `sources.py` | `get_all_sources()` 함수 및 소스 목록 정의 |

---

## 소스 목록 구조

```python
SourceConfig(
    name: str,                    # 소스 식별자 (SentIdStore/BackfillCursor 키로도 사용)
    feed_url: str,                # 피드 URL 또는 사이트 URL
    site_url: str,                # 사이트 홈 URL
    content_level: int,           # 1 (모든 소스 통일)
    active: bool,                 # False면 수집 건너뜀
    parser_type: str,             # "backfill" (모든 소스 통일)
    url_include_pattern: str | None,  # 이 패턴 포함 URL만 허용
    title_blocklist: list[str],   # 제목에 포함 시 제외
)
```

- `get_all_sources()` → 전체 소스 목록 (통합 수집기 사용)
- `get_backfill_sources()` → `get_all_sources()` 별칭 (하위호환)

---

## 현재 소스 목록

| 소스명 | 수집기 | 수집 전략 | 비고 |
|--------|--------|----------|------|
| `Kakao_Tech` | `KakaoBackfillCollector` | 순차 post ID 열거 (675~) | title_blocklist 설정 |
| `NAVER_D2` | `NaverD2BackfillCollector` | REST API 리스팅 + 개별 글 fetch | url_include_pattern=/helloworld/ |
| `Toss_Tech` | `TossBackfillCollector` | 리스팅 페이지네이션 + article body | |
| `OliveYoung_Tech` | `OliveYoungBackfillCollector` | RSS 피드 파싱 (본문 전체 포함) | |
| `Medium_daangn` | `MediumDirectBackfillCollector` | Medium 내부 JSON API + curl_cffi | |
| `Medium_musinsa-tech` | `MediumDirectBackfillCollector` | Medium 내부 JSON API + curl_cffi | |
| `Medium_myrealtrip-product` | `MediumDirectBackfillCollector` | Medium 내부 JSON API + curl_cffi | |
| `Medium_netflix-techblog` | `MediumDirectBackfillCollector` | Medium 내부 JSON API + curl_cffi | netflixtechblog.com으로 redirect |

---

## 소스 추가 원칙

- 소스를 추가할 때 `active=False`로 시작해 동작을 확인한 후 `active=True`로 전환한다.
- `name`은 파일시스템 경로에 사용되므로 영문/숫자/하이픈만 사용한다.
- URL은 코드에 직접 적는다. 환경변수로 관리하지 않는다 (공개 피드이므로 시크릿 아님).
- 소스 추가 시 `run_backfill_batch.py`와 `run_collect_and_save.py`의 `_COLLECTOR_FACTORIES`에도 등록해야 한다.
