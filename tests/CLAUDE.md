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
| `test_normalize_service.py` | `NormalizeService` | `RawEntry` → `NormalizedContent` 변환 검증 |
| `test_preprocess_service.py` | `PreprocessService` | HTML→텍스트 변환, 노이즈 제거, 구조 보존 검증 |
| `test_html_helpers.py` | `html_helpers` | Kakao 본문 추출, 셀렉터 폴백 등 HTML 파싱 유틸 |
| `test_extract_first_image.py` | `extract_first_image` | 썸네일 이미지 추출 (data URI 스킵, 상대 경로 해석 등) |
| `test_sent_id_store.py` | `SentIdStore` | cross-run dedup 저장/로드 동작 확인 |
| `test_stackoverflow_collector.py` | `StackOverflowCollector` | SO 수집·스크래핑, score/view_count 매핑, NormalizedContent 변환 |
| `test_velog_collector.py` | `VelogCollector` | Velog GraphQL 수집, trending/posts 폴백, 날짜 필터 |
| `test_velog_backfill_collector.py` | `VelogBackfillCollector` | 백필 GraphQL 수집, 커서 전환, body 보강, score=None 확인 |
| `test_content_repository.py` | `ContentRepository` | PostgreSQL 저장, score 매핑, 소스 캐시, 중복 스킵 |
| `test_content_pipeline.py` | `ContentPipeline` | 5단계 오케스트레이션, 단계별 실패 격리, thumbnail 전달 |
| `test_all_levels_summary_service.py` | `AllLevelsSummaryService` | Tool Use 기반 4레벨 동시 요약 mock 테스트 (DP-300) |
| `test_all_levels_summary_endpoint.py` | `POST /internal/summaries` | 4레벨 요약 엔드포인트 통합 테스트 (DP-300) |
| `test_summary_repository.py` | `SummaryRepository` | DynamoDB ai_summaries upsert mock 테스트 |
| `test_chunker.py` | `DocumentChunker` | 문서 청킹, 메타데이터, 빈 입력 처리 |
| `test_embedding_service.py` | `EmbeddingOrchestrator` | 청킹→임베딩→저장 오케스트레이션 mock 테스트 |
| `test_vector_repository.py` | `VectorRepository` | DynamoDB rag_documents upsert/조회 mock 테스트 |
| `test_vector_store.py` | `VectorStoreManager` | FAISS 로드/생성/추가/검색 mock 테스트 |
| `test_retriever.py` | `RAGRetriever` | FAISS 유사 검색 mock 테스트 |
| `test_question_embedding.py` | `QuestionEmbeddingOrchestrator` | 질문 임베딩 저장 (DynamoDB + FAISS) mock 테스트 |
| `test_refine_service.py` | `RefineService` | Tool Use 기반 질문 개선 mock 테스트 (DP-231) |
| `test_refine_endpoint.py` | `POST /internal/refine` | 질문 개선 엔드포인트 통합 테스트 (DP-231) |
| `test_answer_service.py` | `AnswerService` | Tool Use 기반 AI 1차 답변 mock 테스트 (DP-234) |
| `test_answer_prompt.py` | `build_user_prompt()` | 답변 프롬프트 빌더 단위 테스트 (DP-234) |
| `test_similar_question_service.py` | `SimilarQuestionService` | FAISS 유사 질문 검색, 자기 자신 제외, threshold 필터 |
| `test_similar_question_endpoint.py` | `POST /internal/similar-questions` | 유사 질문 엔드포인트 통합 테스트 (DP-235) |
| `test_insight_service.py` | `InsightService` | Tool Use 기반 주간 인사이트 mock 테스트 (DP-259) |
| `test_insight_endpoint.py` | `POST /internal/report` | 주간 리포트 엔드포인트 통합 테스트 (DP-259) |
| `test_insight_prompt.py` | `build_user_prompt()` | 인사이트 프롬프트 빌더 단위 테스트 |
| `test_rss_collector.py` | `xml_helpers` | xml_helpers 유틸 함수 테스트 (`compute_entry_hash`, `sha256_text`, `normalize_date` 등) — 파일명은 레거시 |
| `test_trend_data_loader.py` | `TrendDataLoader` | cur/prev 기간 병렬 로드, prev_contents 포함 확인 (DP-379, DP-386) |
| `test_trend_collection_summary.py` | `CollectionSummaryGenerator` | 수집 동향 LLM 서사 요약 mock 테스트 (DP-384) |
| `test_trend_top_posts_summary.py` | `TopPostsSummaryGenerator` | Top 5 콘텐츠 LLM 서사 요약 mock 테스트 (DP-404) |
| `test_trend_orchestrator.py` | `TrendOrchestrator` | 배치 오케스트레이터 통합 흐름, skip/force/LLM 실패 격리 (DP-386) |

---

## 주요 테스트 케이스 요약

### `test_content_pipeline.py`

| 테스트 함수 | 검증 내용 |
|-------------|----------|
| `test_process_content_calls_all_four_steps` | 5단계 전체 호출 확인 |
| `test_process_content_passes_thumbnail_url_to_summarize` | thumbnail_url이 요약 서비스에 전달 |
| `test_process_content_skips_when_body_is_none` | body=None 시 파이프라인 skip |
| `test_preprocess_failure_stops_pipeline_without_propagating` | 전처리 실패 시 파이프라인 중단 (예외 미전파) |
| `test_summary_failure_does_not_propagate` | 요약 실패해도 다음 단계 진행 |
| `test_dynamo_save_failure_does_not_stop_embedding` | DynamoDB 저장 실패해도 임베딩 계속 |
| `test_embedding_failure_does_not_propagate` | 임베딩 실패 시 예외 미전파 |

### `test_all_levels_summary_service.py` (DP-300)

| 테스트 함수 | 검증 내용 |
|-------------|----------|
| `test_summarize_all_success` | AllLevelsSummaryResponse 반환, 필드 타입 확인 |
| `test_summarize_all_four_levels_present` | beginner/junior/mid/senior 4레벨 모두 존재 |
| `test_summarize_all_generated_at_is_set` | `generated_at` 필드 설정 확인 |
| `test_empty_text_raises` | text="" → `AIBadRequestError` |
| `test_no_tool_use_block_raises` | tool_use 블록 없는 응답 → `AIInternalError` |
| `test_validation_error_raises_ai_internal_error` | 필수 필드 누락 → `AIInternalError` |
| `test_api_timeout_raises_ai_timeout_error` | LLM 타임아웃 → `AITimeoutError` |
| `test_rate_limit_raises_ai_upstream_error` | Rate Limit → `AIUpstreamError` |

### `test_content_repository.py`

| 테스트 함수 | 검증 내용 |
|-------------|----------|
| `test_save_contents_maps_score_field_to_db_score` | `item.score` → DB `score` 컬럼 매핑 |
| `test_save_contents_conflict_counted_as_skipped` | 중복 URL 충돌 시 skipped 카운트 증가 |
| `test_save_contents_inserted_contains_content_id_and_item` | 신규 저장 시 SaveResult.inserted에 (id, item) 포함 |
| `test_source_cache_avoids_duplicate_select` | 소스 캐시로 중복 SELECT 방지 |

### `test_stackoverflow_collector.py`

| 테스트 함수 | 검증 내용 |
|-------------|----------|
| `test_to_normalized_content_score_from_api` | SO score → `NormalizedContent.score`, `likes=None` |
| `test_scrape_trending_page_extracts_score_and_view_count` | 스크래핑에서 score/view_count 추출 |
| `test_to_normalized_content_basic_fields` | 기본 필드 매핑 확인 |

### `test_velog_backfill_collector.py`

| 테스트 함수 | 검증 내용 |
|-------------|----------|
| `test_normalized_content_likes_and_score` | Velog likes 매핑, `score=None` 확인 |
| `test_backfill_cursor_transitions_to_incremental` | 커서 phase 자동 전환 |

---

## 테스트 작성 원칙

- 테스트 파일명은 `test_*.py` 형식을 따른다
- 테스트 함수명은 `test_` 접두사를 붙이고 의도가 드러나게 작성한다
  - 예: `test_summary_returns_valid_schema`, `test_invalid_input_returns_422`
- 외부 의존성(LLM API, DB)은 Mock 또는 Fixture로 격리한다
- 테스트는 서버가 실행 중이지 않아도 동작해야 한다 (`TestClient` 또는 직접 함수 호출)
- 하나의 테스트 함수는 하나의 동작만 검증한다

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
