# CLAUDE.md — app/rag/

RAG(Retrieval-Augmented Generation) 파이프라인 모듈. DP-218에서 구현.

---

## 모듈 목적

AI 요약 완료 후 전처리된 원문을 벡터화하여 저장하고, 이후 질문 답변(DP-233) 및 질문 개선(DP-231)에서 유사 콘텐츠를 검색할 수 있게 한다.

---

## 구조

| 파일 | 클래스 | 역할 |
|------|--------|------|
| `schemas.py` | `RAGDocument`, `ChunkMetadata` | 청크 문서 + 메타데이터 Pydantic 모델 |
| `chunker.py` | `DocumentChunker` | `RecursiveCharacterTextSplitter` 기반 body 청킹 |
| `embeddings.py` | `EmbeddingService`, `BedrockEmbeddingsAdapter` | Bedrock Titan Embeddings v2 래퍼 (1024차원) |
| `vector_store.py` | `VectorStoreManager` | FAISS 인덱스 생성/추가/검색/저장 (threading.Lock) |
| `store_manager.py` | `get_store()` | VectorStoreManager 싱글턴 관리 — 매 요청 파일 로드 방지 |
| `retriever.py` | `RAGRetriever` | 검색 인터페이스 (DP-233 등 후속 티켓 사용) |

---

## 청킹 전략 (MVP)

**Body-only**: `PreprocessService` 출력 원문만 청킹.

- 청킹 방식: `RecursiveCharacterTextSplitter` (chunk_size=1000, overlap=200)
- 분할 기준: `["\n\n", "\n", ". ", " ", ""]` 순서
- 메타데이터: `content_id`, `chunk_index`, `keywords`, `tags` (검색 필터링용, 임베딩 안 함)

추후 section chunk 추가 시 `DocumentChunker.chunk()`를 확장한다.

---

## 저장 전략 (하이브리드)

| 저장소 | 역할 |
|--------|------|
| **DynamoDB `rag_documents`** | 아티클 청크 영구 저장 — 텍스트 + 임베딩 벡터 + 메타데이터 |
| **FAISS** (`data/vectors/devpick`) | 아티클 검색 인덱스 (캐시) — DynamoDB에서 언제든 재빌드 가능 |
| **DynamoDB `rag_questions`** | 질문 임베딩 영구 저장 — question_id + 텍스트 + 임베딩 (DP-234) |
| **FAISS** (`data/vectors/questions`) | 질문 검색 인덱스 (캐시) — 유사 질문 추천용 (DP-234) |

FAISS 유실 시: `python scripts/reindex_vectors.py`로 완전 복구 (아티클 인덱스).

---

## 사용 흐름

### 임베딩 저장 (router.py → EmbeddingOrchestrator)

```python
# app/services/embedding_service.py 경유
EmbeddingOrchestrator.embed_and_store(content_id, preprocessed_text, summary)
  ├─ DocumentChunker.chunk() → list[RAGDocument]
  ├─ EmbeddingService.embed(texts) → list[list[float]]
  ├─ VectorRepository.save_chunks() → DynamoDB rag_documents
  ├─ VectorStoreManager.add_documents() → FAISS 추가
  └─ VectorStoreManager.save() → FAISS 파일 저장
```

### 아티클 검색 (DP-234 — /internal/answer 에서 사용)

```python
from app.rag.retriever import RAGRetriever

retriever = RAGRetriever(aws_region="ap-northeast-2")
results = retriever.search("Redis TTL이란?", top_k=5)
context = "\n\n".join(doc.text for doc, _ in results)
```

### 질문 임베딩 저장 (DP-234 — fire-and-forget)

```python
from app.services.question_embedding_service import QuestionEmbeddingOrchestrator

QuestionEmbeddingOrchestrator(
    aws_region="ap-northeast-2",
    index_path="data/vectors/questions",  # 아티클과 분리된 별도 인덱스
).embed_and_store(
    question_id="q_001",
    text="useEffect 무한 렌더링\ndependency array를 비워두면",
    suggested_tags=["React", "useEffect"],
    content_id="article_001",
)
```

- 청킹 없음 — 질문 전체를 단일 문서로 임베딩
- `ChunkMetadata.content_id` = `question_id`, `chunk_index=0`
- 유사 질문 추천 기능(향후)에서 `questions` 인덱스 활용

---

## 설계 결정

- **LangChain 최소 사용**: `RecursiveCharacterTextSplitter`, `FAISS` wrapper만 사용. Chain/Prompt Template은 사용하지 않음 (기존 Anthropic SDK 직접 호출 패턴 유지)
- **임베딩 모델**: Bedrock Titan Embeddings v2 (`amazon.titan-embed-text-v2:0`, 1024차원). EC2 IAM Role 인증 — API 키 불필요
- **싱글턴 관리**: `store_manager.get_store()`로 VectorStoreManager를 프로세스당 1회만 초기화. 매 요청 파일 I/O 방지
- **동시 쓰기 안전**: `VectorStoreManager`의 add/save에 `threading.Lock` 적용
- **Fire-and-forget**: 임베딩 실패해도 요약 응답은 정상 반환 (router.py 패턴 동일)
