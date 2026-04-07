# Devpick AI

DevPick 캡스톤 프로젝트의 AI 서버입니다.

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

### 호출 예시

```bash
# 헤더 없음 → 422
curl http://localhost:8000/internal/health

# 잘못된 키 → 401
curl -H "X-Internal-Key: wrong" http://localhost:8000/internal/health

# 올바른 키 → 200 {"status": "ok"}
curl -H "X-Internal-Key: {키값}" http://localhost:8000/internal/health
```

## CI 파이프라인 (PR 체크)

GitHub Actions 워크플로 `AI PR Checks`가 아래 조건에서 실행됩니다.

- `develop` 브랜치 대상 Pull Request
- `develop` 브랜치로의 Push
- 관련 파일 변경 시: `**/*.py`, `requirements.txt`, `requirements-dev.txt`, `.github/workflows/ai-pr-check.yml`

체크 항목:

- `ruff check .`
- `black --check .`
- `pytest -q`

워크플로 파일: [.github/workflows/ai-pr-check.yml](.github/workflows/ai-pr-check.yml)

로컬에서 PR 전 동일하게 확인하려면:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
ruff check . && black --check . && pytest -q
```

## 콘텐츠 수집 파이프라인

수집 → 중복 제거 → 정규화 → Backend 전송 흐름으로 동작합니다.

```
RSS/Atom Feed
    ↓ Collector (RSSCollector / RSSCrawlCollector)
    ↓ NormalizeService (RawEntry → NormalizedContent)
    ↓ SentIdStore (이미 전송된 항목 dedup)
    ↓ PushService (POST {BACKEND_URL}/internal/contents)
    ↓ Backend → PostgreSQL
    ↓ PreprocessService (HTML → 구조 보존 텍스트)
    ↓ SummaryService (Tool Use + Prompt Caching) → Claude API
```

### 수집 소스 목록

#### RSS 소스 (최신 글 수집)

| 소스 | 수집기 | 비고 |
|------|--------|------|
| 카카오 테크 | RSSCrawlCollector | RSS + HTML 크롤링 보강 |
| 네이버 D2 | RSSCollector | Atom 피드 |
| 토스 테크 | RSSCollector | RSS |
| 올리브영 테크 | RSSCollector | RSS, 182개 전체 본문 포함 |
| Medium daangn | RSSCollector | Medium RSS |
| Medium zigbang | RSSCollector | Medium RSS (2023년 이후 비활성) |
| Medium watcha | RSSCollector | Medium RSS |
| Medium coupang-engineering | RSSCollector | Medium RSS |
| Medium musinsa-tech | RSSCollector | Medium RSS |

#### 백필 소스 (과거 글 수집, 2025.01~)

| 소스 | 수집 전략 | 예상 글 수 |
|------|----------|-----------|
| 카카오 테크 | 순차 post ID 열거 (675~) | ~135개 |
| 네이버 D2 | REST API 리스팅 + 개별 글 fetch | ~40개 |
| 토스 테크 | 리스팅 페이지네이션 + article body | ~50개 |
| Medium daangn | Wayback Machine CDX + 캐시 fetch | ~490개 |
| Medium coupang-engineering | Wayback Machine CDX + 캐시 fetch | 미조사 |
| Medium musinsa-tech | Wayback Machine CDX + 캐시 fetch | 미조사 |
| Medium watcha | Wayback Machine CDX + 캐시 fetch | ~172개 |
| LY Corp | 리스팅 페이지네이션 + article body | 미조사 |
| 우아한형제들 | Wayback Machine CDX + 캐시 fetch | 미조사 |

### 주요 모듈

- `app/collectors`: RSS / RSS+크롤링 수집기 + 백필 크롤러 (`backfill/`)
- `app/stores`: SentIdStore(전송 완료 ID 관리) + BackfillCursor(백필 진행 상태)
- `app/schemas`: SourceConfig, RawEntry, NormalizedContent 스키마
- `app/schemas/summary.py`: SectionSummary, SummaryResponse 스키마 (AI 요약 출력 계약)
- `app/services`: IngestService, NormalizeService, PushService, SummaryService
- `app/services/summary_service.py`: Claude Tool Use 기반 레벨별 AI 요약 생성
- `app/services/preprocess_service.py`: HTML → 구조 보존 텍스트 전처리
- `app/core/prompts/summary.py`: 요약 시스템 프롬프트 + Tool Use 스키마 + 레벨별 지시문
- `app/configs`: 수집 대상 목록 (`get_default_sources()`, `get_crawl_sources()`, `get_backfill_sources()`)
- `app/utils`: RSS/Atom 파싱, HTML 본문 추출 보조 유틸 (BeautifulSoup 기반 공통 함수 포함)
- `data/raw/sent_ids`: 소스별 전송 완료 ID 텍스트 파일
- `data/raw/backfill_cursor`: 소스별 백필 진행 상태 JSON 파일

현재 레포의 수집 범위는 **RSS / RSS+크롤링 + 백필(과거 글)**입니다.
PostgreSQL 저장은 Backend가 담당하며, 이 레포는 수집/정규화/전송만 수행합니다.

### 스크립트

| 스크립트 | 설명 |
|----------|------|
| `scripts/run_collect_and_save.py` | 수집 → 정규화 → 로컬 JSONL 저장 (push 없음). `--backfill` 플래그로 백필 수집 지원 |
| `scripts/run_collect_and_push.py` | 수집 → 정규화 → Backend push 통합 실행 |
| `scripts/run_backfill_batch.py` | 백필 1회 배치 실행 — 소스당 20개 과거 글 수집 → push |
| `scripts/run_scheduler.py` | 6시간 간격으로 RSS + 백필 배치 자동 반복 실행 |
| `scripts/inspect_preprocess.py` | 전처리 출력 확인 (`--url` 또는 `--raw` 모드) |


## 통합 파이프라인 실행

```bash
# RSS + Crawl 1회 실행 (로컬 저장, push 없음)
python scripts/run_collect_and_save.py

# 백필 포함 로컬 저장 (소스당 3개 기본)
python scripts/run_collect_and_save.py --backfill

# 특정 백필 소스만 로컬 저장
python scripts/run_collect_and_save.py --backfill --source LY_Corp --batch-size 5

# RSS 1회 실행 + Backend push
BACKEND_URL=http://localhost:8080 python scripts/run_collect_and_push.py

# 백필 1회 배치 실행 (소스당 20개) + Backend push
BACKEND_URL=http://localhost:8080 python scripts/run_backfill_batch.py

# 6시간 간격 자동 반복 실행 (RSS + 백필)
BACKEND_URL=http://localhost:8080 python scripts/run_scheduler.py
```

## 백필 (과거 글 수집)

RSS 피드가 최근 10~20개만 반환하기 때문에, 과거 글(2025.01~)은 백필 크롤러로 수집합니다.

| 소스 | 수집 전략 | 예상 글 수 |
|------|----------|-----------|
| 카카오 테크 | 순차 post ID 열거 | ~135개 |
| 네이버 D2 | 내부 REST API | ~40개 |
| 토스 테크 | 리스팅 페이지네이션 | ~50개 |
| Medium daangn | Wayback Machine CDX + 캐시 | ~490개 |
| Medium coupang-engineering | Wayback Machine CDX + 캐시 | 미조사 |
| Medium musinsa-tech | Wayback Machine CDX + 캐시 | 미조사 |
| Medium watcha | Wayback Machine CDX + 캐시 | ~172개 |
| LY Corp | 리스팅 페이지네이션 | 미조사 |
| 우아한형제들 | Wayback Machine CDX + 캐시 | 미조사 |

- 스케줄러에 통합되어 6시간마다 소스당 20개씩 점진적 수집
- 커서 파일(`data/raw/backfill_cursor/`)로 진행 상태 관리
- 전체 완료 시 자동 skip, `BackfillCursor.reset()`으로 재시작 가능
