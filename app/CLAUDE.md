# CLAUDE.md — app/

이 디렉토리는 devpick-ai의 핵심 애플리케이션 코드다.

---

## 현재 구조

```text
app/
├── api/            # FastAPI 라우터 + 인증 (DP-215)
│   ├── deps.py     # X-Internal-Key 인증 dependency
│   └── internal/   # /internal/* 라우터
├── collectors/     # 통합 수집기 (backfill/ — 백필+incremental 단일 파이프라인)
├── configs/        # 수집 대상 소스 목록
├── core/           # 프롬프트 템플릿 + 설정 (DP-219~)
│   └── prompts/    # 요약/질문/퀴즈/리포트 프롬프트 + Tool Use 스키마
├── rag/            # RAG 파이프라인 (청킹 → 임베딩 → FAISS, DP-218)
├── schemas/        # Pydantic 스키마
├── services/       # 비즈니스 로직 (수집, 정규화, 요약, 퀴즈, 임베딩, 답변 등)
├── stores/         # SentIdStore (cross-run dedup) + BackfillCursor
├── utils/          # XML/HTML 파싱 헬퍼
└── repositories/   # DynamoDB + PostgreSQL 접근 레이어
```

---

## 수집 파이프라인 전체 흐름

```
SourceConfig (app/configs/sources.py)
    ↓
Collector.collect_batch() → list[RawEntry]  (또는 NormalizedContent 직접 반환)
    ↓
SentIdStore.load() → 이미 처리된 ID 필터링
    ↓
NormalizeService.normalize_entry() → list[NormalizedContent]
    ↓
ContentRepository.save_contents() → PostgreSQL 직접 저장
    ↓ result.inserted — 신규 저장된 (content_id, NormalizedContent) 목록
    ↓
SentIdStore.add() + BackfillCursor.save() → 상태 갱신
    ↓
ContentPipeline.process_content(content_id, body_html, thumbnail_url)
    ↓ Step 1: PreprocessService → HTML → 구조 보존 텍스트
    ↓ Step 2: AllLevelsSummaryService → 4레벨 요약 생성 (Bedrock 1회 호출)
    ↓ Step 3: SummaryRepository → DynamoDB ai_summaries 저장
    ↓ Step 3-1: ContentRepository.save_ai_metadata() → PostgreSQL contents (tags·category UPDATE)
    ↓ Step 4: QuizService → 4레벨 퀴즈 생성 (Bedrock 1회 호출)
              QuizRepository → DynamoDB ai_quizzes 저장
    ↓ Step 5: EmbeddingOrchestrator → RAG 임베딩 → DynamoDB + FAISS
```

- Steps 2~3(요약)과 Step 4(퀴즈)는 독립적으로 실행 — 요약 실패해도 퀴즈 생성 시도
- Step 3-1(PostgreSQL tags·category)은 요약 성공 + ContentRepository 주입 시에만 실행
- Step 5(임베딩)는 요약 성공 시에만 실행 (summary 객체 필요)
- 전체 파이프라인 실행 진입점: `scripts/run_backfill_batch.py`

### 백필 소스별 수집 방식

| 소스 | 크롤러 | 수집 전략 |
|------|--------|----------|
| Kakao Tech | `KakaoBackfillCollector` | 순차 post ID 열거 (675~) |
| NAVER D2 | `NaverD2BackfillCollector` | REST API 리스팅 + 개별 글 fetch |
| Toss Tech | `TossBackfillCollector` | 리스팅 페이지네이션 + article body 추출 |
| OliveYoung Tech | `OliveYoungBackfillCollector` | 리스팅 페이지네이션 + article body 추출 |
| Medium (각 publication) | `MediumDirectBackfillCollector` | Medium API 직접 fetch |
| Stack Overflow | `StackOverflowBackfillCollector` | SO API (NormalizedContent 직접 반환) |
| Velog | `VelogBackfillCollector` | GraphQL API (NormalizedContent 직접 반환) |

---

## AI 요약 흐름 (DP-300)

```
ContentPipeline 또는 POST /internal/summaries (fallback)
    ↓
PreprocessService.preprocess(html) → 구조 보존 텍스트
    ↓
AllLevelsSummaryService.summarize_all(content_id, text, thumbnail_url)
    ↓ build_user_prompt_all_levels(text) — 4레벨 동시 지시문 + 본문
    ↓ Bedrock Converse API (Tool Use + Prompt Caching, temperature=0)
    ↓ tool_use 블록에서 input dict 추출
    ↓ AllLevelsSummaryResponse.model_validate(payload)
    ↓
SummaryRepository.save_all_levels(content_id, response)
    → DynamoDB ai_summaries 테이블, (content_id, level) 기준 4개 아이템 upsert
```

---

## AI 퀴즈 흐름 (DP-265)

```
ContentPipeline 또는 POST /internal/quiz (fallback)
    ↓
PreprocessService.preprocess(html) → 구조 보존 텍스트  (ContentPipeline은 Step 1 결과 재사용)
    ↓
QuizService.generate_all(content_id, text)
    ↓ build_user_prompt(text) — 4레벨 동시 퀴즈 지시문 + 본문
    ↓ Bedrock Converse API (Tool Use + Prompt Caching, temperature=0, maxTokens=4096)
    ↓ tool_use 블록에서 beginner/junior/mid/senior 각 3문제 추출
    ↓ AllLevelsQuizResponse.model_validate(payload)
    ↓
QuizRepository.save(response)
    → DynamoDB ai_quizzes 테이블, content_id 기준 1개 아이템 upsert (4레벨 중첩)
```

**레벨별 표현 기준:**
- `beginner`: 기술 용어 첫 등장 시 괄호 설명 추가, 쉬운 표현
- `junior`: 기본 용어 + 생소한 개념 부연, 원리 위주 해설
- `mid`: 표준 기술 용어, 간결한 핵심 설명
- `senior`: 전문 용어·약어, 트레이드오프·심화 포함

---

## AI 질문 개선 흐름 (DP-231)

```
RefineRequest(title, content, level, content_id?)
    ↓
content_id 있으면:
    VectorRepository.find_by_content_id(content_id) → context_chunks
content_id 없으면:
    context_chunks = None
    ↓
RefineService.refine(title, content, level, context_chunks)
    ↓ Bedrock Converse API (Tool Use + Prompt Caching, temperature=0)
    ↓ RefineResponse.model_validate(payload)
```

---

## AI 1차 답변 흐름 (DP-234)

```
AnswerRequest(refined_title, refined_content, original?, suggested_tags?, content_id?, question_id?)
    ↓
[Step 1] content_id 있으면 VectorRepository.find_by_content_id() → article_chunks
[Step 2] RAGRetriever.search(top_k=5), content_id 동일 청크 제외 → rag_chunks
[Step 3] AnswerService.answer() → (AnswerResponse, references)
[Step 4] SummaryRepository.find_by_content_ids(references) → related_contents 주입
[Step 5] AnswerRepository.save(result, question_id, content_id) [fire-and-forget]
[Step 6] QuestionEmbeddingOrchestrator.embed_and_store(...) [fire-and-forget]
[Step 7] EventRepository.save_event(ANSWER_GENERATED) [fire-and-forget]
```

---

## 폴더별 CLAUDE.md 링크

- [api/CLAUDE.md](api/CLAUDE.md)
- [api/internal/CLAUDE.md](api/internal/CLAUDE.md)
- [collectors/CLAUDE.md](collectors/CLAUDE.md)
- [core/CLAUDE.md](core/CLAUDE.md)
- [schemas/CLAUDE.md](schemas/CLAUDE.md)
- [stores/CLAUDE.md](stores/CLAUDE.md)
- [configs/CLAUDE.md](configs/CLAUDE.md)
- [utils/CLAUDE.md](utils/CLAUDE.md)
- [rag/CLAUDE.md](rag/CLAUDE.md)
- [services/CLAUDE.md](services/CLAUDE.md)
- [repositories/CLAUDE.md](repositories/CLAUDE.md)
