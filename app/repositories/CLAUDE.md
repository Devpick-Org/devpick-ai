# CLAUDE.md — app/repositories/

MongoDB 접근 레이어. 각 도메인별 저장/조회 로직을 서비스와 분리하여 관리한다.

---

## 현재 구조

| 파일 | 클래스 | 역할 |
|------|--------|------|
| `summary_repository.py` | `SummaryRepository` | AI 요약 결과를 `ai_summaries` 컬렉션에 upsert 저장. `find_by_content_ids()` 제공 (DP-220, DP-234) |
| `vector_repository.py` | `VectorRepository` | RAG 청크 + 임베딩 벡터를 `rag_documents` 컬렉션에 저장 (DP-218) |
| `answer_repository.py` | `AnswerRepository` | AI 답변 결과를 `ai_answers` 컬렉션에 저장 (DP-234) |
| `question_vector_repository.py` | `QuestionVectorRepository` | 질문 임베딩을 `rag_questions` 컬렉션에 upsert 저장 (DP-234) |

---

## 사용 패턴

```python
SummaryRepository(mongo_uri=MONGO_URI, db_name="devpick")
save(summary: SummaryResponse) -> None
```

- `(content_id, level)` 복합 unique index 기준 upsert
- `updated_at`: 매 저장 시 갱신
- `created_at`: 최초 삽입 시에만 설정 (`$setOnInsert`)

---

## 작성 원칙

- Repository는 DB 접근만 담당. 비즈니스 로직은 `app/services/`에 위치
- 생성자에서 `mongo_uri`, `db_name` 주입 (서비스 레이어 패턴과 동일)
- 예외는 삼키지 않는다. 호출부(라우터)에서 처리

---

---

## VectorRepository 상세 (DP-218)

```python
VectorRepository(mongo_uri: str, db_name: str = "devpick")
save_chunks(chunks: list[dict]) -> None      # bulk upsert — (content_id, chunk_index) 기준
find_by_content_id(content_id: str) -> list[dict]
find_all() -> Iterator[dict]                 # FAISS 재빌드용
delete_by_content_id(content_id: str) -> int
```

- `(content_id, chunk_index)` unique index 기준 upsert
- `updated_at` 매 저장 시 갱신, `created_at` 최초 삽입 시만 설정
- FAISS 인덱스 유실 시 `find_all()`로 재빌드 (`scripts/reindex_vectors.py`)

---

---

## SummaryRepository 확장 (DP-234)

```python
find_by_content_ids(content_ids: list[str]) -> list[dict]
# 반환: [{"content_id": ..., "one_line_summary": ...}, ...]
# content_id당 첫 번째 결과만 반환 (level이 여러 개일 수 있으므로)
```

related_contents 생성 시 LLM이 references로 반환한 content_id 리스트를 조회한다.

---

## SummaryRepository 확장 (DP-300)

```python
save_all_levels(content_id: str, response: AllLevelsSummaryResponse) -> None
# common 필드 + level 필드 merge → 기존 ai_summaries 스키마 호환 4개 문서 bulk upsert

find_all_levels(content_id: str) -> list[dict]
# content_id에 대한 4개 레벨 문서 전부 조회
```

---

## AnswerRepository 상세 (DP-234)

```python
AnswerRepository(mongo_uri: str, db_name: str = "devpick")
save(answer: AnswerResponse, question_id: str | None, content_id: str | None) -> None
```

- 컬렉션: `ai_answers`
- question_id 있으면 upsert (질문 기준 단일 답변 관리), 없으면 insert
- 인덱스: `(question_id, 1)` unique sparse, `(content_id, 1)`, `(updated_at, -1)`

---

## QuestionVectorRepository 상세 (DP-234)

```python
QuestionVectorRepository(mongo_uri: str, db_name: str = "devpick")
save_question(question_id, text, embedding, suggested_tags=None, content_id=None) -> None
find_all() -> Iterator[dict]  # FAISS 재빌드용
```

- 컬렉션: `rag_questions`
- question_id 기준 upsert
- 인덱스: `(question_id, 1)` unique, `(content_id, 1)`, `(updated_at, -1)`

---

## 향후 추가 예정

| 파일 | 역할 |
|------|------|
| `report_repository.py` | 주간 리포트 저장 (Epic F) |
