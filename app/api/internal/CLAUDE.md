# CLAUDE.md — app/api/internal/

Spring Boot ↔ FastAPI 내부 통신 전용 라우터. Base URL: `/internal`
외부 사용자가 접근하지 않으며, X-Internal-Key 인증이 필수다.

---

## 현재 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/internal/health` | AI 서버 내부 헬스체크 |
| POST | `/internal/summaries` | 4레벨 동시 요약 생성 (DP-300) — DynamoDB ai_summaries 저장 + RAG 임베딩. Backend DynamoDB miss 시 fallback 호출 |
| POST | `/internal/quiz` | 4레벨 퀴즈 생성 (DP-265) — DynamoDB ai_quizzes 저장. Backend DynamoDB miss 시 fallback 호출 |
| POST | `/internal/refine` | 질문 AI 개선 생성 (DP-231) — content_id 있으면 DynamoDB 청크 컨텍스트 |
| POST | `/internal/answer` | 질문 AI 1차 답변 생성 (DP-234) — 아티클+RAG 컨텍스트, related_contents 주입, 질문 임베딩 저장 |
| POST | `/internal/similar-questions` | 유사 질문 검색 (DP-235) — FAISS questions 인덱스 검색, 자기 자신 제외 |
| POST | `/internal/similar-contents` | 유사 콘텐츠 검색 (DP-288) — FAISS devpick 인덱스 검색, content_id 기준 MAX 점수 집계 |
| POST | `/internal/report` | 주간 리포트 AI 인사이트 생성 (DP-259) — Backend 주간 리포트 생성 후 호출 |
| POST | `/internal/trends` | 트렌드 수동 생성 (DP-385) — 디버그·장애 복구용. 0건→400, 5건미만→422 |
| GET | `/internal/trends/latest` | unit+scope 기준 최신 트렌드 스냅샷 조회 (DP-385) — 없으면 404 |
| GET | `/internal/trends/{period_start}` | 특정 기간 트렌드 스냅샷 조회 (DP-385) — 없으면 404 |

---

## 요약·퀴즈 생성 흐름 (배치 vs fallback)

```
[배치] run_backfill_batch.py
  → ContentPipeline.process_content()
      → AllLevelsSummaryService + QuizService 자동 실행
      → DynamoDB ai_summaries + ai_quizzes 저장

[fallback] Backend DynamoDB miss 시
  → POST /internal/summaries  — 요약 생성 + DynamoDB 저장 + RAG 임베딩
  → POST /internal/quiz       — 퀴즈 생성 + DynamoDB 저장
```

---

## POST /internal/summaries 처리 흐름 (DP-300)

```
1. PreprocessService.preprocess(body.text) → preprocessed
2. AllLevelsSummaryService.summarize_all(content_id, preprocessed, thumbnail_url)
3. SummaryRepository.save_all_levels(content_id, result) → DynamoDB [fire-and-forget]
4. EmbeddingOrchestrator.embed_and_store(content_id, preprocessed, result) → DynamoDB + FAISS [fire-and-forget]
5. AllLevelsSummaryResponse 반환
```

---

## POST /internal/quiz 처리 흐름 (DP-265)

```
1. PreprocessService.preprocess(body.text) → preprocessed
2. QuizService.generate_all(content_id, preprocessed) → AllLevelsQuizResponse
3. QuizRepository.save(result) → DynamoDB ai_quizzes [fire-and-forget]
4. EventRepository.save_event(QUIZ_GENERATED) [fire-and-forget, user_id 있을 때만]
5. AllLevelsQuizResponse 반환
```

---

## POST /internal/report 처리 흐름 (DP-259, DP-254)

```
0. UserRepository.find_keywords_by_user_id() → user_keywords (PostgreSQL user_tags JOIN tags)
   → unmatched_keywords = user_keywords - 이번 주 tag_activities
   → UserRepository.find_contents_by_tag_names(unmatched_keywords) → recommended_contents
   [DATABASE_URL 없으면 전체 step 0 skip, 빈 리스트로 fallback]
1. EventRepository.find_by_user() → 주간 AI 이벤트 카운트 (refine/answer/similar)
2. SummaryRepository.find_by_content_ids() → 읽은 글/스크랩한 글 one_line_summary
3. QuestionVectorRepository.find_texts_by_ids() → 작성한 질문 텍스트
4. InsightService.generate(..., user_keywords, unmatched_keywords, recommended_contents)
   → InsightResponse (report_id="" 초기값)
5. result.report_id = body.report_id 주입
6. InsightRepository.save(report_id, user_id, result) [fire-and-forget]
7. EventRepository.save_event(INSIGHT_GENERATED) [fire-and-forget]
```

---

## POST /internal/answer 처리 흐름 (DP-234)

```
1. content_id 있으면 → VectorRepository.find_by_content_id() → article_chunks
2. RAG 유사 검색 (항상) → RAGRetriever.search(top_k=5), content_id 동일 청크 필터 → rag_chunks
3. AnswerService.answer() → (AnswerResponse, references)
4. SummaryRepository.find_by_content_ids(references) → result.related_contents 주입
5. AnswerRepository.save(result, question_id, content_id) [fire-and-forget]
6. QuestionEmbeddingOrchestrator.embed_and_store(...) [fire-and-forget, question_id 있을 때만]
7. EventRepository.save_event(ANSWER_GENERATED) [fire-and-forget]
```

---

## POST /internal/trends 처리 흐름 (DP-385)

```
1. period_start 없으면 compute_period(unit) 자동 계산
   period_start 있으면 compute_period_end(unit, period_start) 로 period_end 계산
2. ContentRepository.count_by_published_range(start_dt, end_dt)
   → 0건: 400 / < 5건: 422
3. TrendOrchestrator.run(unit, period_start, period_end, force=force_refresh)
   → TrendResponse 반환
```

자동 트리거는 `run_trend_scheduler.py`(DP-386)가 담당. 이 엔드포인트는 수동 재생성·디버그용.

---

## 작성 원칙

- 모든 핸들러에 `dependencies=[Depends(verify_internal_key)]` 필수.
- 핸들러는 얇게 유지. 실제 처리는 `app/services/`에 위임.
- 응답은 JSON만 반환. HTTP 상태코드로 에러 표현.
- fire-and-forget 단계는 `try/except`로 감싸고 실패해도 메인 응답에 영향 없음.
