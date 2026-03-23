# CLAUDE.md — app/api/internal/

Spring Boot ↔ FastAPI 내부 통신 전용 라우터. Base URL: `/internal`
외부 사용자가 접근하지 않으며, X-Internal-Key 인증이 필수다.

---

## 현재 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/internal/health` | AI 서버 내부 헬스체크 |
| POST | `/internal/summary` | 콘텐츠 AI 요약 생성 + MongoDB 저장 (DP-217, DP-220) |
| POST | `/internal/refine` | 질문 AI 개선 생성 (DP-231) — content_id 있으면 MongoDB 청크 컨텍스트 |
| POST | `/internal/answer` | 질문 AI 1차 답변 생성 (DP-234) — 아티클+RAG 컨텍스트, related_contents 주입, 질문 임베딩 저장 |
| POST | `/internal/similar-questions` | 유사 질문 검색 (DP-235) — FAISS questions 인덱스 검색, 자기 자신 제외, 유사도 임계값 필터 |
| POST | `/internal/summaries` | 4레벨 동시 요약 생성 (DP-300) — Backend 콘텐츠 저장 후 자동 호출, Claude 1회 호출, MongoDB + RAG 임베딩 |

---

## POST /internal/answer 처리 흐름 (DP-234)

```
1. content_id 있으면 → VectorRepository.find_by_content_id() → article_chunks
2. RAG 유사 검색 (항상) → RAGRetriever.search(top_k=5), content_id 동일 청크 필터 → rag_chunks
3. AnswerService.answer() → (AnswerResponse, references)
4. SummaryRepository.find_by_content_ids(references) → result.related_contents 주입
5. AnswerRepository.save(result, question_id, content_id) [fire-and-forget]
6. QuestionEmbeddingOrchestrator.embed_and_store(...) [fire-and-forget, question_id 있을 때만]
```

---

## 향후 추가 예정

| 메서드 | 경로 | 설명 | Epic |
|--------|------|------|------|
| POST | `/internal/report` | 주간 리포트 인사이트 생성 | F |

---

## 작성 원칙

- 모든 핸들러에 `dependencies=[Depends(verify_internal_key)]` 필수.
- 핸들러는 얇게 유지. 실제 처리는 `app/services/`에 위임.
- 응답은 JSON만 반환. HTTP 상태코드로 에러 표현.
