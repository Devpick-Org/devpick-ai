# CLAUDE.md — tests/

이 폴더는 devpick-ai 서버의 pytest 기반 테스트 코드를 보관한다.

---

## 폴더 목적

- 엔드포인트 동작, AI 출력 검증, 유틸 함수의 정확성을 자동으로 확인한다
- CI(`pytest -q`)에서 자동 실행되며, 실패 시 머지가 차단된다

---

## 현재 테스트

| 파일 | 테스트 대상 | 내용 |
|------|-------------|------|
| `test_health.py` | `health_check()` | `{"status": "ok"}` 반환 확인 |
| `test_rss_collector.py` | `RSSCollector` | RSS/Atom 수집 기본 동작 확인 |
| `test_rss_crawl_collector.py` | `RSSCrawlCollector` | Kakao RSS + HTML 본문 보강 수집 확인 |
| `test_normalize_service.py` | `NormalizeService` | `RawEntry` → `NormalizedContent` 변환 검증 |
| `test_push_service.py` | `PushService` | Backend ingest HTTP 전송 동작 확인 (mock) |
| `test_sent_id_store.py` | `SentIdStore` | cross-run dedup 저장/로드 동작 확인 |
| `test_preprocess_service.py` | `PreprocessService` | HTML→텍스트 변환, 노이즈 제거, 구조 보존 검증 |

### `test_push_service.py` 케이스 (DP-199)

| 테스트 함수 | 검증 내용 |
|-------------|----------|
| `test_push_success_returns_backend_response` | 정상 응답 시 backend JSON 반환 확인 |
| `test_push_empty_list_skips_http_call` | 빈 리스트 입력 시 HTTP 호출 없이 `{saved:0}` 반환 |
| `test_push_raises_on_http_error` | 4xx 응답 시 `HTTPError` raise |
| `test_push_raises_on_server_error` | 5xx 응답 시 `HTTPError` raise |
| `test_push_raises_on_timeout` | 타임아웃 시 `Timeout` raise |
| `test_push_sends_all_items_as_json_payload` | 다중 아이템 전송 시 전체 payload 전달 확인 |

### `test_preprocess_service.py` 케이스 (DP-216)

| 테스트 함수 | 검증 내용 |
|-------------|----------|
| `test_script_style_removed` | script/style 태그 완전 제거 |
| `test_nav_footer_removed` | nav/footer 노이즈 섹션 제거 |
| `test_pre_code_preserved` | 코드블록 구조 보존 |
| `test_heading_conversion` | h1~h6 → 마크다운 heading 변환 |
| `test_img_alt_preserved` | img alt → [이미지: ...] 인라인 변환 |
| `test_img_without_alt_ignored` | alt 없는 이미지 무시 |
| 그 외 11개 | blockquote, br, hr, boilerplate 제거 등 |

### `test_sent_id_store.py` 케이스

| 테스트 함수 | 검증 내용 |
|-------------|----------|
| `test_load_returns_empty_set_when_no_file` | 파일 없을 때 빈 집합 반환 |
| `test_add_creates_file_and_stores_ids` | ID 추가 시 파일 생성 및 내용 저장 |
| `test_add_merges_with_existing_ids` | 기존 ID와 새 ID 병합 저장 |
| `test_load_after_add_returns_stored_ids` | add 후 load 시 저장된 ID 반환 |
| `test_add_is_idempotent` | 동일 ID 중복 추가 시 중복 없이 저장 |

---

## 테스트 작성 원칙

- 테스트 파일명은 `test_*.py` 형식을 따른다
- 테스트 함수명은 `test_` 접두사를 붙이고 의도가 드러나게 작성한다
  - 예: `test_summary_returns_valid_schema`, `test_invalid_input_returns_422`
- 외부 의존성(LLM API, DB)은 Mock 또는 Fixture로 격리한다
- 테스트는 서버가 실행 중이지 않아도 동작해야 한다 (`TestClient` 또는 직접 함수 호출)
- 하나의 테스트 함수는 하나의 동작만 검증한다

---

## 앞으로 추가할 테스트 방향

기능이 추가될 때 함께 작성한다. 아래 순서로 우선 추가한다.

| 파일 (예시) | 테스트 내용 |
|-------------|------------|
| `test_summary.py` | summary 응답이 Pydantic 스키마를 만족하는지 검증 (schema validation) |
| `test_refine.py` | refine 출력 JSON 파싱 정상 동작 확인 (output parsing) |
| `test_answer.py` | AI 1차 답변 실패 시 fallback 응답 반환 확인 (fallback) |
| `test_cache.py` | 캐시 hit/miss 동작 확인, 중복 호출 시 캐시 적중 여부 |
| `test_schemas.py` | Pydantic 스키마 유효성 — 필수 필드 누락 시 ValidationError 발생 확인 |

---

## 로컬 실행

```bash
# 가상환경 활성화 후
pytest -q

# 특정 파일만
pytest tests/test_health.py -v
```

---

## 주의사항

- 실제 Claude API를 호출하는 테스트를 CI에 포함하지 않는다. 비용과 속도 문제가 있다
- API 호출이 필요한 테스트는 Mock을 사용하거나 별도 `integration/` 폴더로 분리한다
- 테스트에 시크릿 값을 하드코딩하지 않는다
