# Devpick AI

DevPick 캡스톤 프로젝트의 AI 서버입니다.

**커밋·푸시 전:** `develop` / `developV2`에 Python 변경을 올리기 전에 [CI 파이프라인](#ci-파이프라인-pr-체크)과 **동일한 로컬 검사**(`ruff` → `black` → `pytest`)를 먼저 통과시키세요. 푸시 후에야 실패하는 **GitHub Actions `AI PR Checks`**(`.github/workflows/ai-pr-check.yml`)를 미리 맞춰 두면 빨간 CI를 줄일 수 있습니다.

## 설치 및 실행

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## 환경변수 설정

`.env.example` 파일을 복사해 `.env` 파일을 생성하세요.

```bash
cp .env.example .env
```

Windows PowerShell에서는 아래 명령을 사용하세요.

```powershell
Copy-Item .env.example .env
```

## 헬스체크 호출 예시

```bash
curl http://127.0.0.1:8000/health
```

응답 예시:

```json
{"status":"ok"}
```

## Internal API (Spring ↔ FastAPI 내부 통신)

Spring Boot가 AI 서버와 통신할 때 사용하는 내부 전용 API다.
Base URL: `http://ai-server:8000/internal`

### 인증

모든 `/internal/*` 엔드포인트는 `X-Internal-Key` 헤더 인증이 필요하다.
키 값은 `.env`의 `INTERNAL_API_KEY`로 관리한다.

| 상황 | 응답 |
|------|------|
| 헤더 없음 | 422 |
| 키 불일치 | 401 |
| 키 일치 | 200 |

### 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/internal/health` | AI 서버 내부 헬스체크 |
| POST | `/internal/summaries` | 4레벨 동시 요약 생성 — DynamoDB ai_summaries 저장 + RAG 임베딩 (DP-300) |
| POST | `/internal/quiz` | 4레벨 퀴즈 생성 — DynamoDB ai_quizzes 저장 (DP-265) |
| POST | `/internal/refine` | AI 질문 개선 (DP-231) |
| POST | `/internal/answer` | AI 1차 답변 생성 (DP-234) |
| POST | `/internal/similar-questions` | 유사 질문 검색 (DP-235) |
| POST | `/internal/similar-contents` | 유사 콘텐츠 검색 (DP-288) |
| POST | `/internal/report` | 주간 리포트 AI 인사이트 생성 (DP-259) |

> **summaries / quiz 엔드포인트는 fallback 용도**다. 정상 운영 시에는 배치 수집 파이프라인이 자동으로 생성한다.

## 콘텐츠 수집 + AI 처리 파이프라인

AI 서버가 수집부터 PostgreSQL 저장, AI 처리까지 직접 담당한다.

```
통합 수집기 (Backfill + Incremental)
    ↓
NormalizeService → NormalizedContent
    ↓
ContentRepository → PostgreSQL 직접 저장
    ↓ (신규 저장된 콘텐츠만)
ContentPipeline.process_content()
    ├─ Step 1:   PreprocessService    — HTML → 구조 보존 텍스트
    ├─ Step 2:   AllLevelsSummaryService — 4레벨 요약 생성 (Bedrock 1회 호출)
    ├─ Step 3:   SummaryRepository    — DynamoDB ai_summaries 저장
    ├─ Step 3-1: ContentRepository    — PostgreSQL contents tags·category UPDATE
    ├─ Step 4:   QuizService          — 4레벨 퀴즈 생성 (Bedrock 1회 호출)
    │            QuizRepository       — DynamoDB ai_quizzes 저장
    └─ Step 5:   EmbeddingOrchestrator — RAG 임베딩 → DynamoDB + FAISS
```

- 요약(Step 2~3)과 퀴즈(Step 4)는 독립 실행 — 요약 실패해도 퀴즈는 생성
- Step 3-1은 요약 성공 시에만 실행 — AI 생성 tags·category를 PostgreSQL에 저장
- Backend는 Redis → DynamoDB 순서로 조회, miss 시 fallback 엔드포인트 호출

### 수집 소스

| 소스 | 수집 전략 |
|------|----------|
| Kakao Tech | 순차 post ID 열거 |
| NAVER D2 | REST API 리스팅 + 개별 글 fetch |
| Toss Tech | 리스팅 페이지네이션 |
| OliveYoung Tech | 리스팅 페이지네이션 |
| Medium (daangn/musinsa-tech 등) | Medium API 직접 fetch |
| Stack Overflow | SO API |
| Velog | GraphQL API |

### 스크립트

| 스크립트 | 설명 |
|----------|------|
| `scripts/run_backfill_batch.py` | 1회 수집 실행 — PostgreSQL 저장 + AI 처리 (요약+퀴즈+임베딩) |
| `scripts/run_scheduler.py` | 6시간 간격 자동 반복 실행 |
| `scripts/run_collect_and_save.py` | 로컬 JSONL 저장 전용 (AI 처리 없음, 개발용) |
| `scripts/run_trend_batch.py` | 트렌드 분석 1회 실행 (`--unit daily/weekly/monthly`, `--force`) |
| `scripts/run_trend_scheduler.py` | 트렌드 분석 자동 실행 (daily 00:05 / weekly 월 00:10 / monthly 1일 00:15 KST) |
| `scripts/init_postgres.py` | PostgreSQL UNIQUE 인덱스 초기화 (배포 시 1회) |
| `scripts/init_vectors.py` | FAISS 인덱스 초기화 |
| `scripts/reindex_vectors.py` | FAISS 인덱스 재빌드 (인덱스 유실 시) |
| `scripts/reprocess_summary.py` | 특정 콘텐츠 요약 재생성 |
| `scripts/reprocess_quiz.py` | 특정 콘텐츠 퀴즈 재생성 |
| `scripts/sync_ai_metadata.py` | DynamoDB → PostgreSQL tags/category 동기화 |
| `scripts/inspect_preprocess.py` | URL 기반 전처리 출력 확인 |

## 주요 실행 명령

```bash
# 1회 수집 실행 (PostgreSQL 저장 + 요약+퀴즈 자동 생성)
DATABASE_URL=postgresql://... python scripts/run_backfill_batch.py

# 스케줄러 (6시간 간격 자동 반복)
DATABASE_URL=postgresql://... python scripts/run_scheduler.py

# 트렌드 분석 1회 실행
DATABASE_URL=postgresql://... python scripts/run_trend_batch.py --unit weekly
DATABASE_URL=postgresql://... python scripts/run_trend_batch.py --unit daily --force

# 트렌드 분석 스케줄러 (daily/weekly/monthly 자동 실행)
DATABASE_URL=postgresql://... python scripts/run_trend_scheduler.py

# 개발 서버
uvicorn main:app --reload

# FAISS 재빌드 (인덱스 유실 시)
python scripts/reindex_vectors.py
```

## 트렌드 분석 배치 파이프라인

AI 서버가 일/주/월 단위로 태그 빈도·TF-IDF·LLM 서사 요약을 생성하고 PostgreSQL `trend_snapshots`에 저장한다. Backend는 이 테이블을 읽어 Frontend에 전달한다.

```
TrendOrchestrator.run(unit, period_start, period_end)
    ├─ TrendDataLoader         — cur/prev 콘텐츠 + 조회수 4개 병렬 쿼리
    ├─ TagNormalizer            — rapidfuzz 동의어 정규화
    ├─ FrequencyAnalyzer        — 태그 빈도 집계 + 증감 상태 (new/up/down/same)
    ├─ KoreanTokenizer + TfidfAnalyzer — TF-IDF 키워드 추출 (제목 기반)
    ├─ TrendRanker              — 조회수 Top 5 콘텐츠 선정
    ├─ TopPostsSummaryGenerator — Top 5 콘텐츠 LLM 서사 요약 (Bedrock)
    ├─ CollectionSummaryGenerator — 수집 동향 LLM 서사 요약 (Bedrock, weekly/monthly만)
    └─ TrendSnapshotRepository  — trend_snapshots upsert
```

- `force=False`이고 동일 기간 스냅샷이 이미 있으면 재생성 없이 즉시 반환
- LLM 실패 시 해당 요약 필드만 `null`로 저장, 스냅샷 저장은 계속 진행

## DynamoDB 테이블 목록

| 테이블 | 내용 |
|--------|------|
| `ai_summaries` | 4레벨 요약 결과 (content_id + level 기준) |
| `ai_quizzes` | 4레벨 퀴즈 결과 (content_id 기준, 4레벨 중첩) |
| `rag_documents` | RAG 청크 + 임베딩 (content_id + chunk_index 기준) |
| `rag_questions` | 질문 임베딩 (question_id 기준) |
| `ai_answers` | AI 답변 결과 (question_id 기준) |
| `event_logs` | AI 처리 이벤트 로그 (일별 dedup) |
| `weekly_report_insights` | 주간 인사이트 (report_id 기준) |

## CI 파이프라인 (PR 체크)

> **메모:** 원격에 푸시하기 **전에** 아래 명령을 로컬에서 실행해 통과 여부를 확인할 것. 실패한 채로 푸시하면 동일한 단계에서 `pr-check` 잡이 exit code 1로 끝난다.

GitHub Actions 워크플로 `AI PR Checks`가 아래 조건에서 실행됩니다.

- `developV2` 브랜치 대상 Pull Request
- `developV2` 브랜치로의 Push

체크 항목:

- `ruff check .`
- `black --check .`
- `pytest -q`

로컬에서 PR 전 동일하게 확인하려면:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
ruff check . && black --check . && pytest -q
```
