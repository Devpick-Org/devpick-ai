# DevPick AI — Claude Code Context

> **읽는 순서**: 이 파일(전체 맥락) → `app/CLAUDE.md` (앱 구조) → 각 폴더별 CLAUDE.md

---

## 1. 프로젝트 개요

**DevPick** — 개발자 성장형 통합 플랫폼

> 개발 콘텐츠 탐색 → AI 요약/질문 → 커뮤니티 소통 → 성장 기록/리포트를 하나의 흐름으로 연결

이 레포는 **FastAPI 기반 AI 서버**다.

* 담당: **수헌** (AI 메인)
* MVP 데드라인: **2026-04-13**
* 현재 상태:
  - RSS/크롤 수집 파이프라인 + SentIdStore dedup 구현 완료 (DP-199)
  - /internal 라우터 + X-Internal-Key 인증 + 에러 핸들러 세팅 완료 (DP-215)
  - PreprocessService (HTML→텍스트) + SummaryResponse 스키마 구현 완료 (DP-216)
  - SummaryService (Tool Use + Prompt Caching) 구현 완료 (DP-219)
  - AI 요약 결과 DynamoDB ai_summaries 저장 구현 완료 (DP-220)
  - NormalizedContent 썸네일 필드 추가 및 본문 이미지 fallback 추출 완료 (DP-291)
  - AI 요약 실패 시 에러 분류 + 재시도 가능 응답 구현 완료 (DP-223)
  - LangChain + FAISS RAG 파이프라인 구현 완료 (DP-218)
  - AI 질문 개선 프롬프트 + RefineService + POST /internal/refine 구현 완료 (DP-231)
  - AI 1차 답변 프롬프트 + AnswerService + POST /internal/answer 구현 완료 (DP-234)
  - 질문 임베딩 저장 (rag_questions + FAISS questions 인덱스) 구현 완료 (DP-234)
  - 유사 질문 탐색 SimilarQuestionService + POST /internal/similar-questions 구현 완료 (DP-235)
  - 4레벨 동시 요약 AllLevelsSummaryService + POST /internal/summaries 구현 완료 (DP-300)
  - AI 처리 이벤트 로그 DynamoDB 저장 (event_logs) + 일별 중복 제거 구현 완료 (DP-252)
  - 주간 인사이트 InsightService + InsightRepository + POST /internal/report 구현 완료 (DP-259, DP-260)
  - **AI 레포 직접 PostgreSQL 저장 구조로 전환 (ContentRepository + ContentPipeline)**
  - **RSS 파이프라인 제거 → 통합 수집기(백필+incremental) 단일화 (중복 수집 문제 해결)**
  - **4레벨 퀴즈 생성 QuizService + QuizRepository + POST /internal/quiz 구현 완료 (DP-265)**
  - **수집 직후 ContentPipeline에서 요약 + 퀴즈 자동 생성 통합**
  - **NormalizedContent score 필드 추가 + tags 필드 제거 (소스별 지표 의미 분리: Velog=likes, SO=score) (DP-300)**
  - **AI 요약 tags·category → PostgreSQL contents 테이블 저장 (ContentPipeline Step 3-1, save_ai_metadata) (DP-300)**
  - **요약 프롬프트 개선: core_summary string 포맷 통일, 섹션 수 원본 구조 추적, 레벨별 독자 관점 차별화 (DP-300)**
  - **유사 콘텐츠 검색 SimilarContentService + POST /internal/similar-contents 구현 완료 (DP-288)**
  - **퀴즈 레벨별 출제 방향 차별화 + 누락 레벨 재시도 로직 추가 (DP-265)**
  - **주간 인사이트 키워드 분석 강화: UserRepository(user_tags+content_tags) + 미탐색 태그 기반 추천 글 + Sonnet 전환 (DP-254)**
  - **영어 제목 번역 후 translated_title을 DynamoDB ai_summaries + PostgreSQL contents에 저장 (DP-328)**
  - **태그 정규화(TagNormalizer) + 빈도 집계(FrequencyAnalyzer) + TF-IDF/tokenizer 구현 (DP-380, DP-381)**
  - **트렌드 랭킹 TrendRanker + TrendDataLoader + TrendSnapshotRepository 구현 (DP-378, DP-379, DP-383)**
  - **Top 5 콘텐츠 LLM 서사 요약 TopPostsSummaryGenerator 구현 (DP-404)**
  - **수집 동향 LLM 서사 요약 CollectionSummaryGenerator + TrendSignals 구현 (DP-384)**
  - **트렌드 배치 오케스트레이터 TrendOrchestrator + run_trend_batch.py + run_trend_scheduler.py 구현 (DP-386)**
  - **트렌드 내부 API POST /internal/trends + GET /internal/trends/latest + GET /internal/trends/{period_start} 구현 (DP-385)**

---

## 2. 시스템 구조

```text
브라우저
→ Nginx
→ Next.js (프론트, :3000)
→ Spring Boot (백엔드, :8080)
→ PostgreSQL (:5432)
→ DynamoDB (AWS)
→ Redis (:6379)
→ FastAPI AI 서버 (:8000)
→ DynamoDB (AWS)
→ FAISS (로컬 인덱스, data/vectors/)
```

---

## 3. 이 레포의 핵심 책임

1. **콘텐츠 수집 및 정규화** — 통합 수집기(백필+incremental) → `NormalizedContent`
2. **PostgreSQL 직접 저장** — `ContentRepository` (Backend push 없음)
3. **AI 요약 + 퀴즈 자동 생성** — `ContentPipeline`: 저장 직후 4레벨 요약 + 4레벨 퀴즈 생성 → DynamoDB. 요약 성공 시 tags·category → PostgreSQL UPDATE
4. **AI 질문/답변/리포트** — RefineService, AnswerService, InsightService
5. **트렌드 분석 배치** — `TrendOrchestrator`: 일/주/월 단위 태그 빈도·TF-IDF·LLM 서사 요약 → `trend_snapshots` PostgreSQL 저장
5. **출력 JSON 스키마 검증 + 파싱 실패 대응**
6. **캐시/저장/로그 기록**

---

## 4. 기술 스택

| 구분        | 기술                   | 비고                                  |
| --------- | -------------------- | ------------------------------------- |
| 언어        | Python 3.12          |                                       |
| 프레임워크     | FastAPI              | `main.py` 최소 서버                   |
| 테스트       | pytest               | CI에서 자동 실행                       |
| 린트/포맷     | ruff, black          | CI 체크 포함                           |
| DB(관계형)   | PostgreSQL           | AI 레포가 직접 저장 (ContentRepository) |
| DB(비정형)   | DynamoDB             | AWS IAM 기반, 키 불필요                |
| 벡터 검색    | FAISS                | 로컬 인덱스 (data/vectors/)            |
| 캐시        | Redis                | Backend가 요약/퀴즈 캐싱               |
| LLM       | Claude Sonnet 계열    | AWS Bedrock Converse API              |

---

## 5. 현재 레포 구조

```text
devpick-ai/
├── app/
│   ├── api/            # FastAPI 라우터 + 인증 (DP-215~)
│   │   ├── deps.py     # X-Internal-Key 인증 dependency
│   │   └── internal/   # /internal/* 라우터
│   ├── collectors/     # 통합 수집기 (backfill/ — 백필+incremental 단일 파이프라인)
│   ├── configs/        # 수집 대상 소스 목록
│   ├── core/           # 프롬프트 템플릿 + Tool Use 스키마 + 공통 유틸
│   │   └── prompts/    # 요약/질문/퀴즈/리포트 프롬프트
│   ├── rag/            # RAG 파이프라인 (청킹/임베딩/FAISS, DP-218)
│   ├── repositories/   # DynamoDB + PostgreSQL 접근 레이어
│   ├── schemas/        # Pydantic 스키마
│   ├── services/       # 비즈니스 로직 (수집, 요약, 퀴즈, 임베딩, 답변 등)
│   ├── stores/         # SentIdStore + BackfillCursor
│   └── utils/          # XML/HTML 파싱 헬퍼
├── scripts/            # 일회성/운영 스크립트
├── tests/              # pytest 테스트
├── data/raw/           # 수집 원본 JSONL (gitignore)
├── data/vectors/       # FAISS 인덱스 파일 (gitignore)
├── main.py             # FastAPI 앱 진입점
└── requirements.txt
```

---

## 6. 브랜치 / 커밋 / PR 규칙

브랜치 흐름: `feature/*` → `developV2` (통합) → `main` (배포)

```bash
git checkout -b feature/DP-{티켓번호}-{기능명}
```

> PR 머지 대상은 `developV2`이다. `main`은 배포 브랜치이므로 직접 푸시 금지.

커밋 예시:
```text
feat: add quiz generation pipeline (DP-265)
fix: handle invalid llm json output (DP-233)
```

PR 제목: `[DP-{티켓번호}] {설명}`

머지 조건: Jira 연결 + AC 충족 + 팀원 1인 승인 + CI 통과 + AI 사용 여부 기록

자세한 내용 → [CONTRIBUTING.md](CONTRIBUTING.md)

---

## 7. CI

`ruff check .` + `black --check .` + `pytest -q`

로컬 확인:
```bash
pip install -r requirements.txt -r requirements-dev.txt
ruff check . && black --check . && pytest -q
```

---

## 8. 자주 하는 작업

```bash
# 개발 서버
uvicorn main:app --reload

# 1회 수집 실행 (백필 + incremental, PostgreSQL 직접 저장 + AI 처리)
DATABASE_URL=postgresql://... python scripts/run_backfill_batch.py

# 스케줄러 (6시간 간격, 통합 수집)
DATABASE_URL=postgresql://... python scripts/run_scheduler.py

# FAISS 인덱스 초기화
python scripts/init_vectors.py

# FAISS 재빌드 (인덱스 유실 시)
python scripts/reindex_vectors.py

# 콘텐츠 요약 재생성 (특정 content_id)
DATABASE_URL=postgresql://... python scripts/reprocess_summary.py <content_id>

# 콘텐츠 퀴즈 재생성 (특정 content_id)
DATABASE_URL=postgresql://... python scripts/reprocess_quiz.py <content_id>

# DynamoDB → PostgreSQL tags/category 동기화
DATABASE_URL=postgresql://... python scripts/sync_ai_metadata.py

# 트렌드 분석 1회 실행 (unit: daily/weekly/monthly)
DATABASE_URL=postgresql://... python scripts/run_trend_batch.py --unit weekly
DATABASE_URL=postgresql://... python scripts/run_trend_batch.py --unit daily --force

# 트렌드 스케줄러 (daily 00:05 / weekly 월 00:10 / monthly 1일 00:15 KST)
DATABASE_URL=postgresql://... python scripts/run_trend_scheduler.py

# 테스트
pytest -q
```

---

## 9. 폴더별 CLAUDE.md

| 폴더 | CLAUDE.md |
|------|-----------|
| `app/` | [app/CLAUDE.md](app/CLAUDE.md) — 앱 전체 구조 개요 |
| `app/api/` | [app/api/CLAUDE.md](app/api/CLAUDE.md) — 라우터 레이어 |
| `app/api/internal/` | [app/api/internal/CLAUDE.md](app/api/internal/CLAUDE.md) — /internal 라우터 |
| `app/collectors/` | [app/collectors/CLAUDE.md](app/collectors/CLAUDE.md) — 수집기 클래스 |
| `app/core/` | [app/core/CLAUDE.md](app/core/CLAUDE.md) — 프롬프트 템플릿 + 설정 |
| `app/schemas/` | [app/schemas/CLAUDE.md](app/schemas/CLAUDE.md) — Pydantic 스키마 |
| `app/stores/` | [app/stores/CLAUDE.md](app/stores/CLAUDE.md) — 저장소 및 dedup |
| `app/configs/` | [app/configs/CLAUDE.md](app/configs/CLAUDE.md) — 소스 설정 |
| `app/utils/` | [app/utils/CLAUDE.md](app/utils/CLAUDE.md) — XML/HTML 헬퍼 |
| `app/services/` | [app/services/CLAUDE.md](app/services/CLAUDE.md) — 서비스 레이어 |
| `app/repositories/` | [app/repositories/CLAUDE.md](app/repositories/CLAUDE.md) — DynamoDB/PostgreSQL 접근 레이어 |
| `scripts/` | [scripts/CLAUDE.md](scripts/CLAUDE.md) — 운영 스크립트 |
| `tests/` | [tests/CLAUDE.md](tests/CLAUDE.md) — 테스트 |

---

## 10. 절대 잊지 말 것

* 이 레포의 1순위는 **안정적인 JSON 계약**이다.
* AI 품질만큼 **비용, 캐시, 실패 대응**이 중요하다.
* `.env`는 절대 커밋 금지. API Key 하드코딩 금지.
* AI 생성 코드라도 최종 책임은 PR 올린 사람에게 있다.
* PostgreSQL 저장은 AI 레포 `ContentRepository`가 직접 담당 — Backend push 불필요.
