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
    ↓ FileRawStore (data/raw/ JSONL 저장)
    ↓ NormalizeService (RawEntry → NormalizedContent)
    ↓ SentIdStore (이미 전송된 항목 dedup)
    ↓ PushService (POST {BACKEND_URL}/internal/contents)
    ↓ Backend → PostgreSQL
    ↓ (향후) PreprocessService (HTML → 구조 보존 텍스트)
    ↓ (향후) SummaryService → Claude API
```

### 주요 모듈

- `app/collectors`: RSS / RSS+크롤링 수집기
- `app/stores`: raw 저장 인터페이스(JSONL) + SentIdStore(전송 완료 ID 관리)
- `app/schemas`: SourceConfig, RawEntry, NormalizedContent 스키마
- `app/schemas/summary.py`: SummaryResponse 스키마 (AI 요약 출력 계약)
- `app/services`: IngestService, NormalizeService, PushService
- `app/services/preprocess_service.py`: HTML → 구조 보존 텍스트 전처리
- `app/configs`: 수집 대상 목록 (`DEFAULT_SOURCES`, `KAKAO_CRAWL_SOURCE`)
- `app/utils`: RSS/Atom 파싱, HTML 본문 추출 보조 유틸
- `data/raw`: 원본(raw) JSONL 저장 디렉토리
- `data/raw/sent_ids`: 소스별 전송 완료 ID 텍스트 파일

현재 레포의 수집 범위는 **RSS / RSS+크롤링**입니다.
PostgreSQL 저장은 Backend가 담당하며, 이 레포는 수집/정규화/전송만 수행합니다.

### 스크립트

| 스크립트 | 설명 |
|----------|------|
| `scripts/run_collect_and_push.py` | 수집 → 정규화 → Backend push 통합 실행 |
| `scripts/run_scheduler.py` | 6시간 간격으로 파이프라인 자동 반복 실행 |
| `scripts/run_rss_collect.py` | RSS 수집만 실행 (push 없음) |
| `scripts/run_rss_crawl_collect.py` | Kakao RSS + HTML 보강 수집만 실행 |
| `scripts/inspect_raw_data.py` | raw JSONL 점검 |
| `scripts/inspect_preprocess.py` | 전처리 출력 확인 (`--url` 또는 `--raw` 모드) |


## 통합 파이프라인 실행

```bash
# 1회 실행
BACKEND_URL=http://localhost:8080 python scripts/run_collect_and_push.py

# 6시간 간격 자동 반복 실행
BACKEND_URL=http://localhost:8080 python scripts/run_scheduler.py
```

## 개별 수집 실행 (push 없음)

```bash
# RSS 수집만
python scripts/run_rss_collect.py

# Kakao RSS + Crawl 수집만
python scripts/run_rss_crawl_collect.py
```


