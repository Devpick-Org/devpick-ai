# CLAUDE.md — app/services/

이 폴더는 비즈니스 로직과 외부 통신을 담당하는 서비스 레이어다.
라우터는 얇게, 로직은 여기에 모은다.

---

## 현재 서비스

| 파일 | 클래스 | 역할 |
|------|--------|------|
| `ingest_service.py` | `IngestService` | Collector 실행 + FileRawStore 저장 오케스트레이션 |
| `normalize_service.py` | `NormalizeService` | `RawEntry` → `NormalizedContent` 변환 |
| `push_service.py` | `PushService` | 정규화된 콘텐츠를 Backend ingest API로 HTTP POST |
| `preprocess_service.py` | `PreprocessService` | HTML → 구조 보존 텍스트 변환 (LLM 입력 전처리) |
| `summary_service.py` | `SummaryService` | Claude Tool Use 기반 레벨별 AI 요약 생성 (DP-219) |
| `refine_service.py` | `RefineService` | Claude Tool Use 기반 레벨별 질문 개선 (DP-231) |
| `embedding_service.py` | `EmbeddingOrchestrator` | 청킹 → 임베딩 → MongoDB+FAISS 저장 오케스트레이션 (DP-218) |
| `answer_service.py` | `AnswerService` | Claude Tool Use 기반 AI 1차 답변 생성 (DP-234) |
| `question_embedding_service.py` | `QuestionEmbeddingOrchestrator` | 질문 임베딩 → MongoDB rag_questions + FAISS questions 저장 (DP-234) |

---

## 데이터 흐름

### run_collect_and_push.py 기준 실제 파이프라인

```
Collector.collect(source)
    → FileRawStore (data/raw/ JSONL 저장)
    → SentIdStore.load(source.name) → 이미 전송된 ID 필터 (RawEntry 기준)
    → NormalizeService.normalize_entry() → list[NormalizedContent]
    → PushService.push(new_items) → POST /internal/contents
    → SentIdStore.add(source.name, pushed_ids)
```

새 항목이 없으면 PushService 호출 없이 skip한다.

### 전처리 흐름 (DP-216)

```
NormalizedContent.body_candidate (HTML)
    → PreprocessService.preprocess() → 구조 보존 텍스트
    → SummaryService.summarize(content_id, level, text) → SummaryResponse
```

### IngestService (독립 사용 가능)

```
IngestService.run_source(source)
    → Collector.collect()
    → FileRawStore.save_feed() + save_entries()
    → {"source": ..., "saved_entries": ..., "status": "ok"}
```

`IngestService`는 수집+저장만 담당한다. 정규화/dedup/push는 포함하지 않는다.

---

## PushService 상세 (DP-199)

```python
PushService(backend_url: str, timeout: int = 30)
push(items: list[NormalizedContent]) -> dict
# 반환 예: {"saved": 5, "skipped": 1}
```

- `BACKEND_URL` 환경변수로 URL 주입 (기본값 `http://localhost:8080`)
- 빈 리스트 입력 시 HTTP 호출 없이 `{"saved": 0, "skipped": 0}` 반환
- `requests.HTTPError` (4xx/5xx) / `requests.Timeout` 그대로 raise — 호출부에서 처리

### 설계 결정 (DP-199)

- AI 레포는 **저장하지 않는다**. 수집 + 정규화 + push만 담당
- PostgreSQL 저장 책임은 Backend (Spring Boot)
- 인터페이스: `POST /internal/contents` — `list[NormalizedContent]` JSON 배열

---

## 작성 원칙

- 서비스 클래스는 생성자에서 의존성(URL, timeout 등)을 주입받는다
- 외부 I/O(HTTP, 파일, DB)는 서비스 레이어에서만 발생하게 한다
- 예외는 삼키지 않는다. 로깅 후 raise하거나 호출부에서 명시적으로 처리
- 프롬프트 문자열은 `app/core/prompts/`에 분리한다. 서비스에 직접 쓰지 않는다

---

## SummaryService 상세 (DP-219, DP-223)

```python
SummaryService(api_key: str, model: str = "claude-sonnet-4-6")
summarize(content_id, level, text, thumbnail_url=None) -> SummaryResponse
```

- **Tool Use**: `tool_choice={"type": "tool", "name": "save_summary"}` — JSON 파싱 실패 0%
- **Prompt Caching**: system 블록에 `cache_control: ephemeral` — 비용 90% 절감
- **Temperature 0**: 일관성 + 속도
- 프롬프트/스키마: `app/core/prompts/summary.py` (SYSTEM_PROMPT, SUMMARY_TOOL, build_user_prompt)
- `core_summary`는 `list[SectionSummary]` (소제목별 요약)
- 요약 완료 후 `SummaryRepository.save()`로 MongoDB `ai_summaries` 저장 (DP-220, 라우터에서 호출)

### 에러 처리 패턴 (DP-223)

`summarize()`는 모든 예외를 `app/core/exceptions.py`의 커스텀 예외로 변환한다.
전역 핸들러(`main.py`)가 `AIServiceError`를 HTTP 응답으로 변환한다.

| 상황 | 발생 예외 | HTTP |
|------|-----------|------|
| 잘못된 level / 빈 text | `AIBadRequestError` | 400 |
| LLM 타임아웃 | `AITimeoutError` | 504 |
| Rate Limit / 연결 실패 / API 에러 | `AIUpstreamError` | 502 |
| 인증 실패 / 파싱 실패 / tool_use 없음 | `AIInternalError` | 500 |

```python
# 서비스에서 예외 발생 → 전역 핸들러가 HTTP 변환
# 라우터는 try/except 없이 SummaryService 호출만 담당
raise AITimeoutError()          # → 504
raise AIUpstreamError("...")    # → 502
raise AIInternalError("...")    # → 500
raise AIBadRequestError("...")  # → 400
```

---

---

## EmbeddingOrchestrator 상세 (DP-218)

```python
EmbeddingOrchestrator(
    openai_api_key: str,
    mongo_uri: str,
    mongo_db: str = "devpick",
    index_path: str = "data/vectors/devpick",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
)
embed_and_store(content_id, preprocessed_text, summary: SummaryResponse) -> None
```

- `DocumentChunker` → body 청킹 (RecursiveCharacterTextSplitter)
- `EmbeddingService` → OpenAI text-embedding-3-small 호출 (1536차원)
- `VectorRepository` → MongoDB `rag_documents` 컬렉션 bulk upsert
- `VectorStoreManager` → FAISS 인덱스 추가 + 파일 저장
- 청킹 결과 없으면 경고 로그 후 조기 반환
- router.py에서 fire-and-forget 패턴으로 호출 (실패해도 요약 응답 정상 반환)

---

## RefineService 상세 (DP-231)

```python
RefineService(api_key: str, model: str = "claude-sonnet-4-6")
refine(title, content, level, context_chunks=None) -> RefineResponse
```

- **Tool Use**: `tool_choice={"type": "tool", "name": "save_refined_question"}` — JSON 파싱 실패 0%
- **Prompt Caching**: system 블록에 `cache_control: ephemeral` — 비용 90% 절감
- **Temperature 0**: 일관성
- 프롬프트/스키마: `app/core/prompts/refine.py` (SYSTEM_PROMPT, REFINE_TOOL, build_user_prompt)
- 컨텍스트 조회: content_id가 있으면 `VectorRepository.find_by_content_id()`로 MongoDB 직접 조회 (라우터에서 호출)
- content_id 없으면 컨텍스트 없이 Claude 기본 지식만으로 질문 개선
- 에러 처리 패턴은 SummaryService와 동일 (DP-223)

---

---

## AnswerService 상세 (DP-234)

```python
AnswerService(api_key: str, model: str = "claude-sonnet-4-6")
answer(
    refined_title, refined_content,
    original_title=None, original_content=None,
    suggested_tags=None, article_chunks=None, rag_chunks=None
) -> tuple[AnswerResponse, list[str]]
```

- **반환**: `(AnswerResponse, references)` 튜플 — references는 LLM이 활용한 content_id 리스트 (내부용)
- **Tool Use**: `tool_choice={"type": "tool", "name": "save_answer"}` — JSON 파싱 실패 0%
- **Prompt Caching**: system 블록에 `cache_control: ephemeral`
- **Temperature 0**, **max_tokens=4096** (코드 예시 포함 가능)
- 프롬프트/스키마: `app/core/prompts/answer.py` (SYSTEM_PROMPT, ANSWER_TOOL, build_user_prompt)
- `references`는 `raw_input.pop("references", [])` 로 먼저 분리 후 AnswerResponse 검증
- `related_contents=[]` 초기값 — 라우터가 MongoDB 조회 후 채움
- 에러 처리 패턴은 SummaryService/RefineService와 동일 (DP-223)

---

## QuestionEmbeddingOrchestrator 상세 (DP-234)

```python
QuestionEmbeddingOrchestrator(
    openai_api_key: str,
    mongo_uri: str,
    mongo_db: str = "devpick",
    index_path: str = "data/vectors/questions",
)
embed_and_store(question_id, text, suggested_tags=None, content_id=None) -> None
```

- **청킹 없음**: 질문은 짧으므로 전체 텍스트를 단일 문서로 임베딩
- `EmbeddingService` 재사용 (OpenAI text-embedding-3-small, 1536차원)
- `VectorStoreManager` 재사용 (다른 `index_path`: `data/vectors/questions`)
- `QuestionVectorRepository` — MongoDB `rag_questions` upsert (question_id 기준)
- FAISS `ChunkMetadata.content_id` = `question_id`, `chunk_index=0`
- 빈/공백 텍스트 → 즉시 return (임베딩/저장 스킵)
- router.py에서 fire-and-forget 패턴으로 호출

---

## 향후 추가 예정

| 파일 | 역할 |
|------|------|
| `report_service.py` | 주간 리포트 인사이트 생성 (Epic F) |

