# CLAUDE.md — app/repositories/

DynamoDB + PostgreSQL 접근 레이어. 각 도메인별 저장/조회 로직을 서비스와 분리하여 관리한다.
모든 DynamoDB 레포지토리는 AWS IAM 기반 인증 (키 불필요), `aws_region` 파라미터로 초기화한다.

---

## 현재 구조

| 파일 | 클래스 | DB | 테이블/컬렉션 | 역할 |
|------|--------|-----|--------------|------|
| `content_repository.py` | `ContentRepository` | PostgreSQL | `contents` | 정규화된 콘텐츠 저장 (DP-199) |
| `summary_repository.py` | `SummaryRepository` | DynamoDB | `ai_summaries` | AI 요약 결과 upsert/조회 (DP-220, DP-300) |
| `quiz_repository.py` | `QuizRepository` | DynamoDB | `ai_quizzes` | AI 퀴즈 결과 upsert/조회 (DP-265) |
| `vector_repository.py` | `VectorRepository` | DynamoDB | `rag_documents` | RAG 청크 + 임베딩 저장 (DP-218) |
| `answer_repository.py` | `AnswerRepository` | DynamoDB | `ai_answers` | AI 답변 결과 저장 (DP-234) |
| `question_vector_repository.py` | `QuestionVectorRepository` | DynamoDB | `rag_questions` | 질문 임베딩 upsert 저장 (DP-234) |
| `event_repository.py` | `EventRepository` | DynamoDB | `event_logs` | AI 처리 이벤트 로그 + 일별 dedup (DP-252) |
| `insight_repository.py` | `InsightRepository` | DynamoDB | `weekly_report_insights` | 주간 인사이트 upsert 저장 (DP-259) |

---

## ContentRepository 상세

```python
ContentRepository(database_url: str)
save_contents(items: list[NormalizedContent]) -> SaveResult
close() -> None
```

- PostgreSQL 직접 저장 (Backend push 불필요)
- `SaveResult.inserted`: 신규 저장된 `(content_id, NormalizedContent)` 목록 — ContentPipeline 입력
- `SaveResult.saved` / `SaveResult.skipped`: 저장/중복 스킵 카운트

---

## SummaryRepository 상세 (DP-220, DP-300)

```python
SummaryRepository(aws_region: str)
save_all_levels(content_id, response: AllLevelsSummaryResponse) -> None
find_by_content_ids(content_ids: list[str]) -> list[dict]
find_all_levels(content_id: str) -> list[dict]
```

- DynamoDB `ai_summaries` 테이블
- `(content_id, level)` 복합 기준 4개 아이템 upsert
- `find_by_content_ids`: content_id당 첫 번째 결과 반환 (related_contents 생성용)

---

## QuizRepository 상세 (DP-265)

```python
QuizRepository(aws_region: str)
save(response: AllLevelsQuizResponse) -> None
find_by_content_id(content_id: str) -> dict | None
```

- DynamoDB `ai_quizzes` 테이블
- PK: `content_id` — content_id당 1개 아이템 (4레벨 중첩 저장)
- 저장 구조: `{ content_id, quiz_id, beginner: {questions}, junior: {questions}, mid: {questions}, senior: {questions}, generated_at, updated_at, created_at }`
- upsert — 재생성 시 덮어씌워짐 (`created_at` 제외)

---

## VectorRepository 상세 (DP-218)

```python
VectorRepository(aws_region: str)
save_chunks(chunks: list[dict]) -> None
find_by_content_id(content_id: str) -> list[dict]
find_all() -> Iterator[dict]
delete_by_content_id(content_id: str) -> int
```

- DynamoDB `rag_documents` 테이블
- `(content_id, chunk_index)` 기준 upsert
- `find_all()`: FAISS 재빌드용 (`scripts/reindex_vectors.py`)

---

## AnswerRepository 상세 (DP-234)

```python
AnswerRepository(aws_region: str)
save(answer: AnswerResponse, question_id: str | None, content_id: str | None) -> None
```

- DynamoDB `ai_answers` 테이블
- question_id 있으면 upsert, 없으면 insert

---

## QuestionVectorRepository 상세 (DP-234)

```python
QuestionVectorRepository(aws_region: str)
save_question(question_id, text, embedding, suggested_tags=None, content_id=None) -> None
find_all() -> Iterator[dict]
find_texts_by_ids(question_ids: list[str]) -> list[str]
```

- DynamoDB `rag_questions` 테이블
- question_id 기준 upsert
- `find_texts_by_ids`: 주간 인사이트 생성 시 질문 텍스트 조회

---

## EventRepository 상세 (DP-252)

```python
EventRepository(aws_region: str)
save_event(user_id, event_type, content_id=None, question_id=None, metadata=None) -> None
find_by_user(user_id, start=None, end=None, event_type=None) -> list[dict]
```

- DynamoDB `event_logs` 테이블
- 저장 전 오늘 UTC 기준 `(user_id, event_type, content_id, question_id)` 중복 확인 → 있으면 스킵

---

## InsightRepository 상세 (DP-259)

```python
InsightRepository(aws_region: str)
save(report_id: str, user_id: str, response: InsightResponse) -> None
find_by_report_id(report_id: str) -> dict | None
```

- DynamoDB `weekly_report_insights` 테이블
- report_id 기준 upsert

---

## 작성 원칙

- Repository는 DB 접근만 담당. 비즈니스 로직은 `app/services/`에 위치
- 생성자에서 `aws_region` 주입 (DynamoDB), `database_url` 주입 (PostgreSQL)
- 예외는 삼키지 않는다. 호출부(라우터, 파이프라인)에서 처리
