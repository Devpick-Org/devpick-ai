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
- MongoDB 인덱스 생성 시 `create_index` 대신 `ensure_index` 방식 또는 중복 무시 옵션을 사용한다

### 실패 처리
- 스크립트 실패 시 명확한 에러 메시지를 출력하고 non-zero exit code로 종료한다
- 부분 실패가 발생할 수 있는 작업은 트랜잭션 또는 롤백 로직을 고려한다

---

## 현재 스크립트

| 파일 | 설명 |
|------|------|
| `init_mongo.py` | Mongo ping 확인, 최소 컬렉션/인덱스 생성, seed upsert |
| `run_collect_and_save.py` | 수집 → 정규화 → dedup → 로컬 JSONL 저장 (백서버 미연동 환경) |
| `run_collect_and_push.py` | 수집 → 정규화 → dedup → Backend push 통합 파이프라인 (DP-199) |
| `run_scheduler.py` | 6시간 간격으로 `run_collect_and_push.main()` 반복 실행 |
| `inspect_preprocess.py` | URL 기반 전처리 출력 확인 |

### `run_collect_and_save.py` (DP-199)

백서버 미연동 환경에서 수집 결과를 로컬에 저장한다.

```bash
python scripts/run_collect_and_save.py
```

- 환경변수 불필요
- Level-2 소스(RSS/Atom) → `RSSCollector`, Level-1 소스(Crawl) → `RSSCrawlCollector` 순으로 실행
- `SentIdStore(data/raw/sent_ids)` — `run_collect_and_push.py`와 dedup 상태 공유
- 출력: `data/raw/normalized/{source_name}.jsonl` (append)
- 소스별 실패는 개별 catch — 전체 파이프라인이 중단되지 않는다

### `run_collect_and_push.py` (DP-199)

수집 파이프라인 전체를 한 번에 실행한다. 백서버 연동 시 사용.

```bash
BACKEND_URL=http://localhost:8080 python scripts/run_collect_and_push.py
```

- `BACKEND_URL` 미설정 시 `http://localhost:8080` 기본값 사용
- Level-2 소스(RSS/Atom) → `RSSCollector`, Level-1 소스(Crawl) → `RSSCrawlCollector` 순으로 실행
- `SentIdStore`로 cross-run dedup — 이미 전송된 항목은 재전송하지 않는다
- 소스별 실패는 개별 catch — 전체 파이프라인이 중단되지 않는다

### `run_scheduler.py`

APScheduler 기반 반복 실행기. 즉시 1회 실행 후 6시간마다 반복한다.

```bash
BACKEND_URL=http://localhost:8080 python scripts/run_scheduler.py
# Ctrl+C로 중단
```

- `BlockingScheduler` 사용 — 프로세스가 살아 있는 동안 계속 실행
- `next_run_time=datetime.now()` — 시작 즉시 첫 실행
- 도커/서버 환경에서 장기 실행 프로세스로 사용

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
python scripts/init_mongo.py
```

---

## 주의사항

- 이 폴더의 스크립트는 CI에서 자동 실행되지 않는다. 수동으로 실행한다
- 프로덕션 DB에 직접 접근하는 스크립트는 실행 전 반드시 팀에 공유한다
- 스크립트 결과로 데이터가 변경될 경우 실행 전 백업 여부를 확인한다
- 스크립트에 시크릿 값을 하드코딩하지 않는다. 항상 환경변수로 주입한다
