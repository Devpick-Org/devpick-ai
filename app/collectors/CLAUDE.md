# CLAUDE.md — app/collectors/

수집기 레이어. 외부 소스에서 원시 데이터를 가져와 `RawEntry` 목록을 반환한다.

RSS 파이프라인을 제거하고 **통합 수집기(백필 + incremental)** 단일 방식으로 운영한다.
소스당 하나의 수집기만 사용하므로 URL 형식 불일치로 인한 중복 수집이 발생하지 않는다.

---

## 현재 수집기

| 파일 | 클래스 | 수집 방식 |
|------|--------|----------|
| `backfill/base.py` | `BackfillCollector` | 커서 기반 배치 수집 ABC + `_resolve_phase()` 헬퍼 |
| `backfill/kakao.py` | `KakaoBackfillCollector` | 순차 post ID 열거 (675~) |
| `backfill/naver_d2.py` | `NaverD2BackfillCollector` | REST API 리스팅 + 개별 글 fetch |
| `backfill/toss.py` | `TossBackfillCollector` | 리스팅 페이지네이션 + article body 추출 |
| `backfill/medium_direct.py` | `MediumDirectBackfillCollector` | Medium 내부 JSON API + curl_cffi |
| `backfill/oliveyoung.py` | `OliveYoungBackfillCollector` | RSS 피드 파싱 (본문 전체 포함) |

---

## 수집기 인터페이스

```python
class BackfillCollector(ABC):
    @abstractmethod
    def collect_batch(
        self, source: SourceConfig, cursor: dict, batch_size: int = 20
    ) -> tuple[list[RawEntry], dict]:
        """커서 위치에서 batch_size만큼 수집, (entries, 갱신된 커서) 반환."""

    @staticmethod
    def _resolve_phase(cursor: dict) -> str:
        """현재 phase 반환 (legacy 커서 하위호환 처리 포함)."""
```

---

## 두 가지 수집 Phase

| Phase | 동작 | 커서 상태 |
|-------|------|---------|
| `backfill` | 2026-01-01 이후 과거 글 전량 수집 (신규→구형 방향) | `{"phase": "backfill", ...}` |
| `incremental` | 신규 글만 체크 (6시간마다 최신 페이지 스캔) | `{"phase": "incremental", ...}` |

- backfill 소진 시 자동으로 incremental로 전환 (`done: true` 설정 안 함)
- incremental phase에서 `is_done()` 항상 `False` → 스케줄러가 계속 실행

## 소스별 커서 형식

| 소스 | backfill 커서 | incremental 커서 |
|------|-------------|----------------|
| `Kakao_Tech` | `{"phase": "backfill", "next_id": 683}` | `{"phase": "incremental", "next_id": 900}` |
| `NAVER_D2` | `{"phase": "backfill", "next_page": 0, "pending_ids": [...], "latest_seen_ts": 0}` | `{"phase": "incremental", "latest_seen_ts": 1735689600000}` |
| `Toss_Tech` | `{"phase": "backfill", "next_page": 5, "pending_slugs": [...], "seen_slugs": [...]}` | `{"phase": "incremental", "seen_slugs": [...]}` |
| `Medium_*` | `{"phase": "backfill", "collection_id": "...", "next_to": null, "discovery_done": false, "pending": [...], "seen_urls": [...]}` | `{"phase": "incremental", "collection_id": "...", "seen_urls": [...]}` |
| `OliveYoung_Tech` | `{"phase": "backfill", "seen_ids": [...]}` | `{"phase": "incremental", "seen_ids": [...]}` |

---

## 수집기 작성 원칙

- 수집기는 외부 I/O만 담당한다. 저장/정규화 로직은 포함하지 않는다.
- 재시도 횟수(`max_retries`)와 타임아웃(`timeout`)은 생성자에서 주입한다.
- 개별 항목 파싱 실패는 해당 항목만 건너뛰고 계속 진행한다.
- HTML 파싱은 `app/utils/html_helpers.py` 공통 함수를 사용한다 (regex 직접 작성 금지).
- `entry_external_id`는 소스별로 일관된 URL 형식을 유지해야 한다 (dedup 핵심).
