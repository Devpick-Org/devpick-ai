# DevPick AI — 인수인계 문서

> **이 문서는 devpick-ai 레포에서 마지막으로 진행 중이던 작업의 컨텍스트를 담고 있다.**
> 중간에 작업을 넘겨받거나, 시간이 지나 다시 작업을 재개할 때 이 문서부터 읽으면 된다.
> 완료된 작업 현황, 다음 작업 명세, 주의사항, 이후 로드맵 순으로 정리되어 있다.

> 마지막 업데이트: 2026-03-19
> 담당: 수헌

---

## 현재 브랜치

`feature/DP-218-rag-pipeline`

> PR 대상 브랜치: `develop`

---

## 완료된 작업

| 티켓 | 내용 |
|------|------|
| DP-199 | RSS/크롤 수집 파이프라인 + SentIdStore dedup + PushService |
| DP-215 | /internal 라우터 + X-Internal-Key 인증 + 에러 핸들러 |
| DP-216 | PreprocessService (HTML→텍스트) + SummaryResponse 스키마 |
| DP-219 | SummaryService (Tool Use + Prompt Caching + 소제목별 요약) |
| DP-217 | POST /internal/summary 엔드포인트 |
| DP-220 | AI 요약 결과 MongoDB ai_summaries 저장 |
| DP-291 | NormalizedContent 썸네일 필드 추가 및 본문 이미지 fallback 추출 |
| DP-292 | NormalizedContent 스키마 정규화 문서 반영 |
| DP-223 | AI 요약 실패 시 에러 분류 + 재시도 가능 응답 |
| DP-218 | LangChain + FAISS RAG 파이프라인 구현 |

---

## 다음 작업: DP-235 — 유사 질문 탐색 API 개발

**브랜치**: `feature/DP-235-similar-question`

### 구현 방향

- 사용자 질문이 들어오면 임베딩하여 FAISS에서 유사 질문을 탐색
- DP-218에서 구현된 `RAGRetriever`를 활용
- 실제 사용자 질문을 MongoDB에 저장하고 FAISS에 인덱싱 (study_question과는 별개)
- Spring Boot에서 `POST /internal/similar-questions` 형태로 호출

---

## 이후 작업 순서

### Epic C — AI 요약

| 티켓 | 내용 | 상태 | 비고 |
|------|------|------|------|
| DP-218 | LangChain + FAISS RAG 파이프라인 구현 | ✅ 완료 | |

### Epic D — 질문/커뮤니티

| 티켓 | 내용 | 상태 | 비고 |
|------|------|------|------|
| DP-235 | 유사 질문 탐색 API 개발 (FAISS) | 해야 할 일 | DP-218 완료 → 시작 가능 |
| DP-231 | AI 질문 개선 프롬프트 작성 및 테스트 | 해야 할 일 | |
| DP-234 | AI 1차 답변 프롬프트 작성 및 테스트 | 해야 할 일 | DP-233 전에 선행 |
| DP-233 | AI 답변 자동 생성 API 개발 | 해야 할 일 | DP-234 완료 후 |
| DP-232 | 사용자가 AI 1차 답변을 받을 수 있다 (스토리) | 해야 할 일 | DP-233, DP-234 완료 후 |

### Epic E — 학습 히스토리

| 티켓 | 내용 | 상태 |
|------|------|------|
| DP-252 | 이벤트 로그 MongoDB 저장 | 해야 할 일 |

### Epic F — 주간 리포트

| 티켓 | 내용 | 상태 | 비고 |
|------|------|------|------|
| DP-260 | AI 인사이트 프롬프트 작성 및 테스트 | 해야 할 일 | DP-259 전에 선행 |
| DP-259 | AI 인사이트 생성 API 개발 (FastAPI) | 해야 할 일 | DP-260 완료 후 |

### MVP+

| 티켓 | 내용 | 상태 |
|------|------|------|
| DP-265 | AI 퀴즈 생성 API 개발 (FastAPI) | 해야 할 일 |
| DP-267 | 학습 자료 추천 API 개발 | 해야 할 일 |

---

## DP-218 구현 요약

### 새로 만든 파일

| 파일 | 역할 |
|------|------|
| `app/rag/__init__.py` | RAG 모듈 패키지 |
| `app/rag/schemas.py` | `RAGDocument`, `ChunkMetadata` Pydantic 모델 |
| `app/rag/chunker.py` | `DocumentChunker` — RecursiveCharacterTextSplitter body 청킹 |
| `app/rag/embeddings.py` | `EmbeddingService` — OpenAI text-embedding-3-small 래퍼 |
| `app/rag/vector_store.py` | `VectorStoreManager` — FAISS 인덱스 관리 (threading.Lock) |
| `app/rag/retriever.py` | `RAGRetriever` — 검색 인터페이스 (DP-233/231 에서 사용) |
| `app/repositories/vector_repository.py` | `VectorRepository` — MongoDB `rag_documents` CRUD |
| `app/services/embedding_service.py` | `EmbeddingOrchestrator` — 청킹→임베딩→저장 오케스트레이션 |
| `scripts/init_vectors.py` | FAISS 인덱스 초기화 |
| `scripts/reindex_vectors.py` | MongoDB에서 FAISS 재빌드 (인덱스 유실 복구) |
| `data/vectors/.gitkeep` | FAISS 인덱스 저장 디렉터리 |

### 수정한 파일

| 파일 | 변경 내용 |
|------|-----------|
| `app/api/internal/router.py` | fire-and-forget 임베딩 블록 추가 |
| `scripts/init_mongo.py` | `rag_documents` 컬렉션 + 인덱스 추가 |
| `requirements.txt` | langchain-core/openai/community, faiss-cpu 추가 |
| `.gitignore` | `data/vectors/` 추가 |

### RAGRetriever 사용법 (DP-233 이후)

```python
from app.rag.retriever import RAGRetriever

retriever = RAGRetriever(openai_api_key=OPENAI_API_KEY)
results = retriever.search("Redis TTL이란?", top_k=5)
context = "\n\n".join(doc.text for doc, _ in results)
```

---

## 로컬 실행 확인

```bash
# 의존성
pip install -r requirements.txt -r requirements-dev.txt

# Mongo 초기화 (rag_documents 인덱스 포함)
python scripts/init_mongo.py

# FAISS 재빌드 (인덱스 유실 시)
python scripts/reindex_vectors.py

# 테스트
pytest -q

# 린트/포맷
ruff check . && black --check .

# 개발 서버
uvicorn main:app --reload
```
