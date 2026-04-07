# CLAUDE.md — app/

이 디렉토리는 devpick-ai의 핵심 애플리케이션 코드다.

---

## 현재 구조

```text
app/
├── api/            # FastAPI 라우터 + 인증 (DP-215)
│   ├── deps.py     # X-Internal-Key 인증 dependency
│   └── internal/   # /internal/* 라우터
├── collectors/     # 수집기 — RSS, RSS+크롤링, 백필(backfill/)
├── configs/        # 수집 대상 소스 목록
├── core/           # 프롬프트 템플릿 + 설정 (DP-219~)
│   └── prompts/    # 요약/질문/리포트 프롬프트 + Tool Use 스키마
├── rag/            # RAG 파이프라인 (청킹 → 임베딩 → FAISS, DP-218)
├── schemas/        # Pydantic 스키마 (RawEntry, NormalizedContent, SourceConfig, SummaryResponse)
├── services/       # 비즈니스 로직 (IngestService, NormalizeService, PushService, SummaryService, EmbeddingOrchestrator)
├── stores/         # raw JSONL 저장 + SentIdStore (cross-run dedup) + BackfillCursor
├── utils/          # XML/HTML 파싱 헬퍼
└── repositories/   # MongoDB 접근 레이어 (SummaryRepository, VectorRepository, DP-220~)
```

---

## 수집 파이프라인 전체 흐름

```
SourceConfig (app/configs/sources.py)
    ↓
Collector.collect() → (_, list[RawEntry], _)
    ↓
NormalizeService.normalize_entry() → list[NormalizedContent]
    ↓
SentIdStore.load() → 이미 처리된 ID 필터링
    ↓
[로컬 저장] data/raw/normalized/{source}.jsonl  (run_collect_and_save.py)
[백서버 push] POST /internal/contents → Backend  (run_collect_and_push.py)
    ↓
SentIdStore.add() → 처리 완료 ID 기록
```

전체 파이프라인 실행 진입점: `scripts/run_collect_and_push.py`

### 백필 파이프라인 흐름 (DP-199)

```
BackfillCursor.load(source.name) → cursor
    ↓
BackfillCollector.collect_batch(source, cursor, 20) → (list[RawEntry], new_cursor)
    ↓
SentIdStore.load(source.name) → 이미 처리된 ID 필터링
    ↓
NormalizeService.normalize_entry() → list[NormalizedContent]
    ↓
PushService.push(new_items) → Backend
    ↓
SentIdStore.add() + BackfillCursor.save() → 상태 갱신
```

- 6시간마다 RSS 수집 후 백필 배치 실행 (소스당 20개)
- 커서 `"done": true` → 해당 소스 skip, 전체 done → 백필 단계 자동 skip
- 실행 진입점: `scripts/run_backfill_batch.py`

#### 백필 소스별 수집 방식

| 소스 | 크롤러 | 수집 전략 |
|------|--------|----------|
| Kakao Tech | `KakaoBackfillCollector` | 순차 post ID 열거 (675~) |
| NAVER D2 | `NaverD2BackfillCollector` | REST API 리스팅 + 개별 글 fetch |
| Toss Tech | `TossBackfillCollector` | 리스팅 페이지네이션 + article body 추출 |
| Medium daangn | `MediumWaybackBackfillCollector` | Wayback Machine CDX API + 캐시 페이지 fetch |
| Medium coupang-engineering | `MediumWaybackBackfillCollector` | Wayback Machine CDX API + 캐시 페이지 fetch |
| Medium musinsa-tech | `MediumWaybackBackfillCollector` | Wayback Machine CDX API + 캐시 페이지 fetch |
| Medium watcha | `MediumWaybackBackfillCollector` | Wayback Machine CDX API + 캐시 페이지 fetch |
| LY Corp | `LYCorpBackfillCollector` | 리스팅 페이지네이션 (`/ko/page/{n}/`) + article body 추출 |
| 우아한형제들 | `WoowahanBackfillCollector` | Wayback Machine CDX API + 캐시 페이지 fetch (Cloudflare 우회) |

---

## AI 요약 + 임베딩 흐름 (DP-219, DP-220, DP-218)

```
PreprocessService.preprocess(html) → 구조 보존 텍스트
    ↓
SummaryService.summarize(content_id, level, text)
    ↓ build_user_prompt(level, text) — 레벨별 지시문 + 본문
    ↓ Claude API (Tool Use + Prompt Caching, temperature=0)
    ↓ tool_use 블록에서 input dict 추출
    ↓ SummaryResponse.model_validate(payload)
    ↓
SummaryRepository.save(summary) → MongoDB ai_summaries 컬렉션 upsert (fire-and-forget)
    ↓
EmbeddingOrchestrator.embed_and_store(content_id, preprocessed_text, summary)
    ↓ DocumentChunker.chunk() → list[RAGDocument]
    ↓ EmbeddingService.embed() → list[list[float]]
    ↓ VectorRepository.save_chunks() → MongoDB rag_documents 컬렉션 upsert
    ↓ VectorStoreManager.add_documents() + save() → FAISS 인덱스 파일 (fire-and-forget)
```

---

## AI 질문 개선 흐름 (DP-231)

```
RefineRequest(title, content, level, content_id?)
    ↓
content_id 있으면:
    VectorRepository.find_by_content_id(content_id)
    → MongoDB rag_documents에서 해당 아티클 청크 text 조회 → context_chunks
content_id 없으면:
    context_chunks = None (Claude 기본 지식으로 개선)
    ↓
RefineService.refine(title, content, level, context_chunks)
    ↓ build_user_prompt(level, title, content, context_chunks) — 레벨별 지시문 + 컨텍스트 + 원본 질문
    ↓ Claude API (Tool Use + Prompt Caching, temperature=0)
    ↓ tool_use 블록에서 input dict 추출
    ↓ RefineResponse.model_validate(payload)
```

---

## AI 1차 답변 흐름 (DP-234)

```
AnswerRequest(refined_title, refined_content, original_title?, original_content?,
              suggested_tags?, content_id?, question_id?)
    ↓
[Step 1] content_id 있으면:
    VectorRepository.find_by_content_id(content_id) → article_chunks
[Step 2] RAG 유사 검색 (content_id 유무와 무관하게 항상):
    RAGRetriever.search(refined_title + " " + refined_content, top_k=5)
    → content_id와 동일한 문서 제외 → rag_chunks ([출처: content_id] 라벨 포함)
    ↓
[Step 3] AnswerService.answer(refined_title, refined_content, original_title, original_content,
                              suggested_tags, article_chunks, rag_chunks)
    ↓ build_user_prompt() — 관련 아티클 → 참고 문서 → 원본 질문 → 관련 기술 태그 → 질문
    ↓ Claude API (Tool Use + Prompt Caching, temperature=0, max_tokens=4096)
    ↓ tool_use 블록에서 input dict 추출, references 분리
    ↓ AnswerResponse.model_validate(payload)  (related_contents=[] 초기값)
    ↓
[Step 4] references 기반 related_contents 조회:
    SummaryRepository.find_by_content_ids(references)
    → result.related_contents에 RelatedContent 리스트 주입
    ↓
[Step 5] AnswerRepository.save(result, question_id, content_id) (fire-and-forget)
    → MongoDB ai_answers 컬렉션 upsert
[Step 6] QuestionEmbeddingOrchestrator.embed_and_store(question_id, text, ...) (fire-and-forget)
    → MongoDB rag_questions + FAISS data/vectors/questions 인덱스
```

---

## 향후 추가될 구조

```text
app/
└── core/
    ├── config.py
    └── logging.py
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
