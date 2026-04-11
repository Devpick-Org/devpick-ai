# CLAUDE.md — app/services/

이 폴더는 비즈니스 로직과 외부 통신을 담당하는 서비스 레이어다.
라우터는 얇게, 로직은 여기에 모은다.

---

## 현재 서비스

| 파일 | 클래스 | 역할 |
|------|--------|------|
| `normalize_service.py` | `NormalizeService` | `RawEntry` → `NormalizedContent` 변환 |
| `preprocess_service.py` | `PreprocessService` | HTML → 구조 보존 텍스트 변환 (LLM 입력 전처리) |
| `content_pipeline.py` | `ContentPipeline` | 콘텐츠 저장 후 전처리 → 요약 → 퀴즈 → 임베딩 오케스트레이션 |
| `all_levels_summary_service.py` | `AllLevelsSummaryService` | Bedrock Tool Use 기반 4레벨 동시 AI 요약 생성 (DP-300) |
| `quiz_service.py` | `QuizService` | Bedrock Tool Use 기반 4레벨 동시 퀴즈 생성 (DP-265) |
| `embedding_service.py` | `EmbeddingOrchestrator` | 청킹 → 임베딩 → DynamoDB+FAISS 저장 오케스트레이션 (DP-218) |
| `refine_service.py` | `RefineService` | Bedrock Tool Use 기반 레벨별 질문 개선 (DP-231) |
| `answer_service.py` | `AnswerService` | Bedrock Tool Use 기반 AI 1차 답변 생성 (DP-234) |
| `question_embedding_service.py` | `QuestionEmbeddingOrchestrator` | 질문 임베딩 → DynamoDB rag_questions + FAISS questions 저장 (DP-234) |
| `similar_question_service.py` | `SimilarQuestionService` | FAISS questions 인덱스 유사 질문 검색 (DP-235) |
| `insight_service.py` | `InsightService` | Bedrock Tool Use 기반 주간 학습 인사이트 생성 (DP-259) |

---

## ContentPipeline 상세

```python
ContentPipeline(aws_region: str, bedrock_model: str)
process_content(content_id, body_html, thumbnail_url=None) -> None
```

PostgreSQL 저장 직후 신규 콘텐츠에 대해 순서대로 실행:

```
Step 1:   PreprocessService.preprocess(body_html) → preprocessed
Step 2:   AllLevelsSummaryService.summarize_all() → summary  [실패 시 None, 계속 진행]
Step 3:   SummaryRepository.save_all_levels() → DynamoDB ai_summaries  [summary 있을 때만]
Step 3-1: ContentRepository.save_ai_metadata() → PostgreSQL contents tags·category UPDATE  [summary + DB 주입 시]
Step 4:   QuizService.generate_all() + QuizRepository.save() → DynamoDB ai_quizzes  [항상 시도]
Step 5:   EmbeddingOrchestrator.embed_and_store() → DynamoDB + FAISS  [summary 있을 때만]
```

- **요약(Step 2)과 퀴즈(Step 4)는 독립** — 요약 실패해도 퀴즈 생성 시도
- **Step 3-1(PostgreSQL)은 요약 성공 + `database_url` 주입 시에만 실행**
- **임베딩(Step 5)은 요약 의존** — summary 객체가 없으면 skip
- 각 단계는 독립 try/except — 한 단계 실패해도 다음 단계 계속 시도
- `scripts/run_backfill_batch.py`에서 `result.inserted` 기준으로 호출

---

## AllLevelsSummaryService 상세 (DP-300)

```python
AllLevelsSummaryService(aws_region: str, model: str)
summarize_all(content_id, text, thumbnail_url=None) -> AllLevelsSummaryResponse
```

- **Tool Use**: `save_all_summaries` — JSON 파싱 실패 0%
- **Prompt Caching**: system 블록 `cachePoint` — 비용 절감
- **Temperature 0**, 4레벨(beginner/junior/mid/senior) 동시 생성
- 에러 처리: `AIBadRequestError` / `AITimeoutError` / `AIUpstreamError` / `AIInternalError`

---

## QuizService 상세 (DP-265)

```python
QuizService(aws_region: str, model: str)
generate_all(content_id, text) -> AllLevelsQuizResponse
```

- **Tool Use**: `save_quiz` — JSON 파싱 실패 0%
- **Prompt Caching**: system 블록 `cachePoint`
- **Temperature 0**, **maxTokens 4096** (4레벨 × 3문제 분량)
- 4레벨은 같은 핵심 개념, 용어·표현 방식만 레벨별로 조정
  - `beginner`: 괄호 안 용어 설명, 쉬운 표현
  - `junior`: 기본 용어 + 원리 위주 해설
  - `mid`: 표준 기술 용어, 간결
  - `senior`: 전문 용어·약어, 트레이드오프 포함
- 에러 처리: SummaryService와 동일 패턴 (DP-223)

---

## EmbeddingOrchestrator 상세 (DP-218)

```python
EmbeddingOrchestrator(aws_region: str)
embed_and_store(content_id, preprocessed_text, summary: AllLevelsSummaryResponse) -> None
```

- `DocumentChunker` → body 청킹
- `EmbeddingService` → 임베딩 생성
- `VectorRepository` → DynamoDB rag_documents upsert
- `VectorStoreManager` → FAISS 인덱스 추가 + 파일 저장

---

## RefineService 상세 (DP-231)

```python
RefineService(aws_region: str, model: str)
refine(title, content, level, context_chunks=None) -> RefineResponse
```

- **Tool Use + Prompt Caching**, temperature=0
- context_chunks: DynamoDB rag_documents에서 조회한 아티클 청크 (라우터가 주입)

---

## AnswerService 상세 (DP-234)

```python
AnswerService(aws_region: str, model: str)
answer(refined_title, refined_content, original_title=None, original_content=None,
       suggested_tags=None, article_chunks=None, rag_chunks=None
) -> tuple[AnswerResponse, list[str]]
```

- **반환**: `(AnswerResponse, references)` — references는 LLM이 활용한 content_id 리스트
- **Tool Use + Prompt Caching**, temperature=0, max_tokens=4096

---

## InsightService 상세 (DP-259)

```python
InsightService(aws_region: str, model: str)
generate(activities, ai_events, read_summaries, scrapped_summaries,
         question_texts, week_start, week_end) -> InsightResponse
```

- **Tool Use + Prompt Caching**, temperature=0.3, max_tokens=1024

---

## 작성 원칙

- 서비스 클래스는 생성자에서 의존성(`aws_region`, `model` 등)을 주입받는다
- 외부 I/O(HTTP, DB)는 서비스 레이어에서만 발생하게 한다
- 예외는 삼키지 않는다. `app/core/exceptions.py` 커스텀 예외로 변환 후 raise
- 프롬프트 문자열은 `app/core/prompts/`에 분리한다. 서비스에 직접 쓰지 않는다

### 에러 처리 패턴 (DP-223)

| 상황 | 발생 예외 | HTTP |
|------|-----------|------|
| 빈 text / 잘못된 입력 | `AIBadRequestError` | 400 |
| LLM 타임아웃 | `AITimeoutError` | 504 |
| Rate Limit / 연결 실패 | `AIUpstreamError` | 502 |
| 파싱 실패 / tool_use 없음 | `AIInternalError` | 500 |
