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

## 콘텐츠 원본 수집기 스캐폴딩

FastAPI 기반 수집 파이프라인 확장을 위해 아래 구조를 추가했습니다.

- `app/collectors`: RSS / RSS+크롤링 수집기 구현
- `app/stores`: raw 저장 인터페이스와 파일(JSONL) 저장 구현
- `app/schemas`: 수집 대상(SourceConfig), 원본 엔트리(RawEntry) 스키마
- `app/services`: collector 실행 orchestration (`IngestService`)
- `app/configs`: 초기 수집 대상 목록 (`DEFAULT_SOURCES`)
- `app/utils`: RSS/Atom 파싱 보조 유틸
- `app/main.py`: 향후 수집 도메인 확장을 위한 FastAPI 앱 엔트리
- `scripts/run_rss_collect.py`: RSS 수집 실행 스크립트
- `scripts/run_rss_crawl_collect.py`: Kakao RSS + HTML 보강 수집 실행 스크립트
- `scripts/inspect_raw_data.py`: raw JSONL 점검 스크립트
- `data/raw`: 원본(raw) 저장 디렉토리
- `tests/test_rss_collector.py`: RSS collector 기본 스캐폴딩 테스트

현재 레포의 수집 범위는 **RSS / RSS+크롤링**입니다.
API 기반 수집은 현재 레포 범위에서 제외되며, 별도 담당자가 관리합니다.

## Kakao RSS + Crawl 실행

Kakao Tech(레벨 1) RSS 감지 후 상세 페이지 HTML 본문 후보를 보강 수집하려면:

```bash
python scripts/run_rss_crawl_collect.py
```

## PostgreSQL 저장 검증

정규화 결과 DB 저장 검증 순서:

```bash
# 1) devpick-infra 에서 Postgres 실행
# (devpick-infra 레포 루트)
docker compose up -d --build postgres

# 2) devpick-ai 레포에서 검증 실행
python scripts/check_db_connection.py

# 3) NAVER_D2 저장/조회 검증
python scripts/save_normalized_to_db.py --source NAVER_D2 --limit 5
python scripts/check_saved_contents.py --source NAVER_D2 --limit 5

# 4) Kakao_Tech 저장/조회 검증
python scripts/save_normalized_to_db.py --source Kakao_Tech --limit 5
python scripts/check_saved_contents.py --source Kakao_Tech --limit 5
```


