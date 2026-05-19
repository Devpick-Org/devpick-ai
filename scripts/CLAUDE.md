# CLAUDE.md — scripts/

이 폴더는 devpick-ai 서버의 일회성 유틸리티 스크립트를 보관한다.

---

## 폴더 목적

- 서버 애플리케이션 코드에 포함되지 않는 운영/초기화 작업용 스크립트를 둔다
- 대표적인 용도: DB 초기화, 데이터 마이그레이션, 시드 데이터 삽입, 인덱스 생성

---

## 스크립트 작성 원칙

### 독립 실행 가능
- 각 스크립트는 단독으로 실행할 수 있어야 한다
- 앱 서버(`uvicorn`)가 실행 중이지 않아도 동작해야 한다
- 필요한 환경변수는 `.env`에서 `python-dotenv`로 직접 로드한다

### Idempotent (멱등성)
- 동일 스크립트를 여러 번 실행해도 결과가 동일해야 한다
- 중복 생성, 중복 삽입이 발생하지 않도록 upsert 또는 존재 여부 확인 후 처리한다
- PostgreSQL 인덱스 생성 시 `CREATE INDEX IF NOT EXISTS` 구문을 사용한다

### 실패 처리
- 스크립트 실패 시 명확한 에러 메시지를 출력하고 non-zero exit code로 종료한다
- 부분 실패가 발생할 수 있는 작업은 트랜잭션 또는 롤백 로직을 고려한다

---

## 현재 스크립트

| 파일 | 설명 |
|------|------|
| `run_backfill_batch.py` | 1회 수집 실행 — PostgreSQL 직접 저장 + AI 처리(요약·퀴즈·임베딩) |
| `run_scheduler.py` | 6시간 간격 자동 반복 실행 (APScheduler 기반) |
| `run_collect_and_save.py` | 수집 → 로컬 JSONL 저장 전용 (AI 처리 없음, 개발·디버그용) |
| `run_trend_batch.py` | 트렌드 분석 1회 실행 CLI — `--unit daily/weekly/monthly`, `--force` (DP-386) |
| `run_trend_scheduler.py` | 트렌드 분석 자동 실행 스케줄러 — daily/weekly/monthly cron (DP-386) |
| `run_youtube_batch.py` | YouTube 채널 영상 1회 수집 실행 |
| `run_youtube_scheduler.py` | YouTube 자동 수집 스케줄러 |
| `collect_rallit_jobs.py` | 랠릿 채용 공고 크롤링 → Spring `POST /internal/jobs/ingest` 전달 |
| `reingest_job_urls.py` | DB에 저장된 랠릿 공고 URL 재수집 → ingest API 재전달 |
| `init_postgres.py` | PostgreSQL UNIQUE 인덱스 초기화 — 배포 시 1회 실행 (멱등성 보장) |
| `init_vectors.py` | FAISS 벡터 디렉터리 초기화 (Bedrock Titan v2 기반) |
| `reindex_vectors.py` | FAISS 인덱스 재빌드 — DynamoDB rag_documents 기반 (인덱스 유실 시) |
| `reprocess_summary.py` | 특정 content_id 요약 재생성 |
| `reprocess_quiz.py` | 특정 content_id 퀴즈 재생성 |
| `reprocess_embedding.py` | 저장된 콘텐츠 RAG 임베딩 재시도 |
| `sync_ai_metadata.py` | DynamoDB → PostgreSQL tags/category/translated_title 동기화 |
| `backfill_youtube_content_tags.py` | YouTube 기존 콘텐츠 content_tags 백필 |
| `inspect_preprocess.py` | URL 기반 전처리 출력 확인 (디버그용) |

### `run_backfill_batch.py`

1회 수집 실행. 소스당 최대 20개 수집 → PostgreSQL 직접 저장 → AI 처리(요약·퀴즈·임베딩) 자동 실행.

```bash
DATABASE_URL=postgresql://... python scripts/run_backfill_batch.py
```

- `BackfillCursor(data/raw/backfill_cursor)` — 소스별 진행 상태(phase/커서) 파일 관리
- `SentIdStore(data/raw/sent_ids)` — cross-run dedup
- 커서 phase: `backfill`(과거 글 전량) → `incremental`(최신 글만) 자동 전환
- 소스별 실패는 개별 catch — 전체 배치가 중단되지 않는다

### `run_scheduler.py`

APScheduler 기반 반복 실행기. 즉시 1회 실행 후 6시간마다 반복한다.

```bash
DATABASE_URL=postgresql://... python scripts/run_scheduler.py
# Ctrl+C로 중단
```

- `BlockingScheduler` 사용 — 프로세스가 살아 있는 동안 계속 실행
- 도커/서버 환경에서 장기 실행 프로세스로 사용

### `run_collect_and_save.py`

수집 → 로컬 JSONL 저장 전용. AI 처리 없음. 개발·디버그 환경에서 사용.

```bash
python scripts/run_collect_and_save.py
```

- 출력: `data/raw/normalized/{source_name}.jsonl` (append)

### `run_trend_batch.py` (DP-386)

트렌드 분석 1회 실행 CLI.

```bash
# period-start 미입력 시 단위별 직전 기간 자동 계산
DATABASE_URL=postgresql://... python scripts/run_trend_batch.py --unit weekly
DATABASE_URL=postgresql://... python scripts/run_trend_batch.py --unit daily --period-start 2026-04-21
DATABASE_URL=postgresql://... python scripts/run_trend_batch.py --unit monthly --force
```

- `--unit`: `daily` / `weekly` / `monthly`
- `--period-start`: 기간 시작 (YYYY-MM-DD). 미입력 시 자동 계산
- `--force`: 기존 스냅샷이 있어도 재생성

### `run_trend_scheduler.py` (DP-386)

트렌드 분석 자동 실행 스케줄러. KST 기준 자정 직후에 실행한다.

```bash
DATABASE_URL=postgresql://... python scripts/run_trend_scheduler.py
# Ctrl+C로 중단
```

- `daily`: 매일 00:05 KST
- `weekly`: 매주 월요일 00:10 KST (직전 한 주 월~월)
- `monthly`: 매월 1일 00:15 KST (직전 달)
- 각 job 독립 try/except — 개별 실패가 스케줄러 전체를 중단하지 않는다

### `inspect_preprocess.py` (DP-216)

전처리 출력을 확인하는 디버그용 스크립트다.

```bash
python scripts/inspect_preprocess.py --url https://d2.naver.com/...
```

### 앞으로 추가 가능

* `seed_vectors.py` — 벡터 임베딩 초기 시드 데이터 삽입
* `backfill_ai_summary.py` — 기존 콘텐츠 요약 일괄 생성
* `eval_runner.py` — AI 출력 품질 평가 실행

---

## 실행 방법 (공통)

```bash
# 가상환경 활성화 후 실행
source .venv/bin/activate          # macOS/Linux
.venv\Scripts\activate             # Windows

# 환경변수 로드는 스크립트 내부에서 처리
DATABASE_URL=postgresql://... python scripts/init_postgres.py
```

---

## 주의사항

- 이 폴더의 스크립트는 CI에서 자동 실행되지 않는다. 수동으로 실행한다
- 프로덕션 DB에 직접 접근하는 스크립트는 실행 전 반드시 팀에 공유한다
- 스크립트 결과로 데이터가 변경될 경우 실행 전 백업 여부를 확인한다
- 스크립트에 시크릿 값을 하드코딩하지 않는다. 항상 환경변수로 주입한다
