# DevPick AI — Claude Code Context

> **읽는 순서**: 이 파일(전체 맥락) → `docs/MONGO_INIT.md` (Mongo 최소 세팅) → 추후 추가될 `app/CLAUDE.md` 또는 도메인별 CLAUDE.md

---

## 1. 프로젝트 개요

**DevPick** — 개발자 성장형 통합 플랫폼

> 개발 콘텐츠 탐색 → AI 요약/질문 → 커뮤니티 소통 → 성장 기록/리포트를 하나의 흐름으로 연결

이 레포는 **FastAPI 기반 AI 서버**다.
현재는 초기 세팅 단계이며, health check / Mongo 초기화 / CI / 기본 협업 규칙까지 구성되어 있다.

* 담당: **수헌** (AI 메인)
* MVP 데드라인: **2026-04-13**
* 현재 상태: **AI 서버 스켈레톤 + Mongo 초기화 + PR 체크 파이프라인 구성 완료**

### 시스템 구조 (4개 서버)

```text
브라우저
→ Nginx
→ Next.js (프론트, :3000)
→ Spring Boot (백엔드, :8080)
→ PostgreSQL (:5432)
→ MongoDB (:27017)
→ Redis (:6379)
→ FastAPI AI 서버 (:8000)
```

---

## 2. 이 레포의 역할

AI 서버는 단순히 LLM을 한 번 호출하는 서버가 아니다.

이 레포의 핵심 책임은 다음 6가지다.

1. **요청 입력을 AI 작업에 맞게 정규화**
2. **프롬프트 조합 및 모델 호출 제어**
3. **RAG 검색/컨텍스트 주입**
4. **출력 JSON 스키마 검증**
5. **캐시/저장/로그 기록**
6. **실패 대응 및 품질 평가(Eval)**

즉, DevPick AI 서버는 **LLM 호출기**가 아니라 **AI application layer**로 본다.

---

## 3. 담당 기능 범위 (MVP 기준)

### Epic C — AI 요약

* 콘텐츠 상세 페이지용 레벨별 요약 생성
* 핵심 포인트 / 키워드 / 다음 학습 행동 제안

### Epic D — 질문 기능

* 질문 개선 (`refine`)
* AI 1차 답변 (`ai-answer`)
* 유사 질문 추천 (`similar`)

### Epic F — 주간 리포트

* 사용자 활동 해석
* 개인화 인사이트/코멘트 생성

백엔드 API 목록 기준으로 AI와 직접 연결되는 엔드포인트:

* `GET /contents/{contentId}/summary`
* `POST /contents/{contentId}/summary/retry`
* `POST /posts/refine`
* `GET /posts/{postId}/similar`
* `POST /posts/{postId}/ai-answer`
* `GET /reports/weekly`

---

## 4. 기술 스택

| 구분        | 기술                   | 비고                              |
| --------- | -------------------- | ------------------------------- |
| 언어        | Python               | 3.12                            |
| 프레임워크     | FastAPI              | 현재 `main.py` 기준 최소 서버 구성        |
| 테스트       | pytest               | health 테스트 존재                   |
| 린트/포맷     | ruff, black          | CI 체크에 포함                       |
| DB(비정형)   | MongoDB              | 초기 컬렉션/인덱스 세팅 존재               |
| 캐시        | Redis                | 향후 summary / answer / report 캐시 |
| 구조화 DB 연계 | PostgreSQL           | 백엔드와 연계                         |
| LLM       | Claude Sonnet 계열 우선  | 필요 시 보조 모델 검토                   |
| RAG       | FAISS 또는 동급 벡터 검색 계층 | 추후 도입                           |

---

## 5. 현재 레포 구조

현재 `develop` 브랜치 기준 루트 구조:

```text
devpick-ai/
├── .github/
│   ├── workflows/
│   └── pull_request_template.md
├── docs/
│   └── MONGO_INIT.md
├── scripts/
│   └── init_mongo.py
├── tests/
│   └── test_health.py
├── .env.example
├── .gitignore
├── CONTRIBUTING.md
├── README.md
├── main.py
├── pytest.ini
├── requirements-dev.txt
└── requirements.txt
```

현재는 **앱 로직이 루트 중심**으로 얇게 시작되어 있다.
기능이 늘어나면 아래 구조로 확장하는 것을 기본 방향으로 본다.

```text
app/
├── api/
├── core/
├── schemas/
├── services/
├── repositories/
└── utils/
```

---

## 6. 파일/폴더별 역할

### `main.py`

* FastAPI 앱 진입점
* 최소 health endpoint 유지
* 비즈니스 로직 직접 작성 금지
* 현재는 `/health` 한 개만 존재

### `docs/`

* 사람이 읽는 운영/설계 문서
* 현재는 Mongo 초기화 문서(`MONGO_INIT.md`)가 존재
* 앞으로 추가 권장: `AI_SCHEMA.md`, `RAG_DESIGN.md`, `EVAL_GUIDE.md`, `PROMPT_RULES.md`

### `scripts/`

* 일회성 실행 스크립트
* 현재 `init_mongo.py`는 재실행 안전(idempotent)하게 Mongo 인덱스/기본 설정을 초기화
* 스크립트는 앱 시작 시 자동 실행보다 **수동 실행 가능**하고 **독립적**이어야 한다

### `tests/`

* pytest 기반 테스트
* 현재 health check 테스트가 있다
* 앞으로 추가 권장: schema validation, prompt output parsing, fallback/timeout, cache hit/miss

### `.github/`

* 협업 자동화 및 PR 규칙
* PR 템플릿과 `AI PR Checks` 워크플로가 존재
* 이 폴더 변경은 협업 규칙에 직접 영향 주므로, 사소해 보여도 의도를 PR에 명시

---

## 7. 브랜치 / 커밋 / PR 규칙

이 레포는 [CONTRIBUTING.md](CONTRIBUTING.md)의 최소 규칙과 팀 브랜치 전략을 함께 따른다.

### 브랜치

```bash
git checkout develop
git pull origin develop
git checkout -b feature/DP-{티켓번호}-{기능명}
```

예시:

```bash
git checkout -b feature/DP-230-question-refine-endpoint
```

### 커밋 메시지

권장 1:

```text
DP-{티켓번호}: {작업 내용}
```

권장 2 (`CONTRIBUTING.md` 스타일):

```text
type: 내용 (DP-###)
```

예시:

```text
feat: add summary response schema (DP-221)
fix: handle invalid llm json output (DP-233)
docs: add root CLAUDE context (DP-169)
```

### PR 제목

```text
[DP-{티켓번호}] {설명}
```

### 머지 조건

* Jira 티켓 연결
* AC 충족
* 팀원 1명 이상 승인
* CI 통과
* AI 사용 여부 기록

---

## 8. 현재 CI 규칙

GitHub Actions 워크플로 `AI PR Checks`가 존재한다.
`develop` 대상 PR 또는 `develop` push에서, Python 파일/requirements/워크플로 파일 변경 시 실행된다.
체크 항목: `ruff check .`, `black --check .`, `pytest -q`

로컬에서 PR 전 권장 실행:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
ruff check .
black --check .
pytest -q
```

---

## 9. 코드 컨벤션

| 대상     | 규칙                       | 예시                     |
| ------ | ------------------------ | ---------------------- |
| 파일/모듈  | snake_case               | `summary_service.py`   |
| 클래스    | PascalCase               | `SummaryService`       |
| 함수/변수  | snake_case               | `build_summary_prompt` |
| 상수     | UPPER_SNAKE_CASE         | `MAX_RETRY_COUNT`      |
| 환경변수   | UPPER_SNAKE_CASE         | `MONGO_URI`            |
| API 경로 | kebab-case 또는 팀 합의 경로 유지 | `/posts/refine`        |

추가 원칙:

* 타입 힌트 필수
* 라우터는 얇게 유지
* 프롬프트 문자열을 라우터에 직접 쓰지 않기
* JSON 후처리/검증 로직은 분리
* 예외는 삼키지 말고 로그/재시도 정책과 함께 관리

---

## 10. AI 출력 계약 원칙

AI 기능은 모두 **구조화된 JSON 반환**을 우선한다.

### 공통 원칙

* 반드시 스키마 정의 후 구현
* 필수 공통 필드 포함 권장: `confidence`, `follow_up_questions`
* JSON 파싱 실패를 기본 실패 시나리오로 간주
* 파싱 실패 시:
  1. 1회 재시도
  2. 그래도 실패하면 fallback 응답
  3. 로그 남기기

### 기능별 방향

* 요약: `summary`, `key_points`, `keywords`, `difficulty`, `next_actions`
* 질문 개선: `title`, `refined_question`, `missing_info_checklist`, `tags`
* AI 1차 답변: `answer`, `assumptions`, `verification_steps`, `risks`
* 리포트: `insights`, `strengths`, `gaps`, `next_week_actions`

### 절대 금지

* 스키마에 없는 필드 임의 추가
* 원문 장문을 그대로 복붙 수준으로 반환
* 확신 없는 내용을 단정 표현

---

## 11. MongoDB 사용 원칙

현재 `docs/MONGO_INIT.md`와 `scripts/init_mongo.py`에 따라 Mongo는 최소 세팅이 구성되어 있다.
기본 컬렉션은 `contents`, `configs`이며, URL 중복 방지와 source/external_id 중복 방지 인덱스가 생성된다.
`schema_version`, `initialized_at`도 upsert로 관리한다.

### 현재 원칙

* 접속은 항상 `MONGO_URI` 기준
* 초기화는 앱 자동실행이 아니라 별도 스크립트 방식
* 재실행 안전성(idempotent) 보장

### AI 확장 시 권장 컬렉션

* `ai_summaries`
* `ai_answers`
* `weekly_report_insights`
* `event_logs`

### 저장 시 함께 남길 것

* `request_id`
* `model`
* `latency_ms`
* `token_usage`
* `schema_version`
* `created_at`

---

## 12. 보안 / 시크릿 주의사항

* API Key, DB 비밀번호, 토큰은 코드에 하드코딩 금지
* `.env`는 절대 커밋 금지
* `.env.example`만 추적
* 프롬프트에 개인정보/시크릿 직접 포함 금지
* AI 생성 코드도 PR 올린 사람이 책임
* PR 본문에 AI 사용 여부 반드시 기록

---

## 13. 앞으로 추가될 앱 구조 기준

현재는 아직 `app/` 폴더가 없지만, FastAPI 기능이 늘어나면 아래 구조로 옮긴다.

```text
app/
├── api/
│   └── v1/
├── core/
│   ├── config.py
│   ├── prompts/
│   └── logging.py
├── schemas/
├── services/
├── repositories/
└── utils/
```

그때부터는 폴더별 `CLAUDE.md`를 아래처럼 추가한다.

* `app/CLAUDE.md` → 앱 전체 아키텍처
* `app/api/CLAUDE.md` → 라우터/응답 규칙
* `app/services/CLAUDE.md` → 비즈니스 로직/LLM 호출 규칙
* `app/schemas/CLAUDE.md` → Pydantic/JSON 계약 규칙
* `app/core/prompts/CLAUDE.md` → 프롬프트 작성 원칙

즉, **지금 당장은 루트 + 현재 실존 폴더 기준 CLAUDE.md**,
앱 구조가 생기면 그때 세부 CLAUDE.md를 추가하는 방식이 맞다.

---

## 14. 폴더별 CLAUDE.md 참고 초안

현재 각 폴더에 CLAUDE.md가 생성되어 있다. 아래는 각 파일의 핵심 방향 요약이다.

### `docs/CLAUDE.md`

운영/설계 문서 목적, 작성 규칙, 현재/향후 문서 목록.
핵심 문서: `MONGO_INIT.md` (현재), `AI_SCHEMA.md`, `RAG_DESIGN.md`, `EVAL_GUIDE.md`, `PROMPT_RULES.md` (향후)

### `scripts/CLAUDE.md`

일회성 스크립트 원칙: 독립 실행, idempotent, 명확한 실패 처리.
현재: `init_mongo.py` / 향후: `seed_vectors.py`, `backfill_ai_summary.py`, `eval_runner.py`

### `tests/CLAUDE.md`

pytest 기반 테스트 원칙. 현재: `test_health.py`
우선 추가: summary schema validation, refine output parsing, ai-answer fallback, cache hit/miss

### `.github/CLAUDE.md`

PR 템플릿/워크플로 변경 주의사항, CI 게이트 3단계 의미 설명.

---

## 15. 자주 하는 작업

```bash
# 개발 서버 실행
uvicorn main:app --reload

# health check
curl http://127.0.0.1:8000/health

# 테스트
pytest -q

# 포맷/린트
ruff check .
black --check .

# Mongo 초기화
python scripts/init_mongo.py
```

---

## 16. 우선 구현 순서

1. 루트 `CLAUDE.md` 확정
2. 폴더별 `CLAUDE.md` 추가
3. `app/` 구조 도입
4. Pydantic 요청/응답 스키마 정의
5. 요약/질문개선/1차답변 엔드포인트 스켈레톤 추가
6. JSON 파싱/재시도 유틸 추가
7. Redis 캐시 도입
8. RAG/임베딩 구조 연결
9. Eval 테스트 세트 추가

---

## 17. 참고 문서

* [README.md](README.md) — 현재 실행/CI 방법
* [CONTRIBUTING.md](CONTRIBUTING.md) — 브랜치/PR/커밋 최소 규칙
* [docs/MONGO_INIT.md](docs/MONGO_INIT.md) — Mongo 초기화 원칙
* [.github/pull_request_template.md](.github/pull_request_template.md) — PR 작성 양식
* [.github/workflows/ai-pr-check.yml](.github/workflows/ai-pr-check.yml) — 현재 품질 게이트

---

## 18. 절대 잊지 말 것

* 이 레포의 1순위는 **안정적인 JSON 계약**이다.
* 멋진 답변보다 **파싱 가능한 구조**가 먼저다.
* AI 품질만큼 **비용, 캐시, 실패 대응**이 중요하다.
* 문서/코드/PR 규칙은 결국 팀 협업 품질에 직결된다.
* AI가 생성한 코드라도 최종 책임은 PR 올린 사람에게 있다.
