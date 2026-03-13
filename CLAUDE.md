# DevPick AI — Claude Code Context

> **읽는 순서**: 이 파일(전체 맥락) → `app/CLAUDE.md` (앱 구조) → 각 폴더별 CLAUDE.md

---

## 1. 프로젝트 개요

**DevPick** — 개발자 성장형 통합 플랫폼

> 개발 콘텐츠 탐색 → AI 요약/질문 → 커뮤니티 소통 → 성장 기록/리포트를 하나의 흐름으로 연결

이 레포는 **FastAPI 기반 AI 서버**다.

* 담당: **수헌** (AI 메인)
* MVP 데드라인: **2026-04-13**
* 현재 상태: **RSS/크롤 수집 파이프라인 + SentIdStore dedup + PushService 구현 완료 (DP-199)**

---

## 2. 시스템 구조

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

## 3. 이 레포의 핵심 책임

1. **콘텐츠 수집 및 정규화** — RSS/크롤링 → `NormalizedContent`
2. **Backend ingest push** — `POST /internal/contents`
3. **AI 요약/질문/리포트** (Epic C, D, F — 향후 구현)
4. **출력 JSON 스키마 검증 + 파싱 실패 대응**
5. **캐시/저장/로그 기록**
6. **실패 대응 및 품질 평가(Eval)**

---

## 4. 기술 스택

| 구분        | 기술                   | 비고                         |
| --------- | -------------------- | -------------------------- |
| 언어        | Python 3.12          |                            |
| 프레임워크     | FastAPI              | `main.py` 최소 서버            |
| 테스트       | pytest               | CI에서 자동 실행                 |
| 린트/포맷     | ruff, black          | CI 체크 포함                   |
| DB(비정형)   | MongoDB              | 초기 컬렉션/인덱스 구성              |
| 캐시        | Redis                | 향후 summary / answer 캐시     |
| 구조화 DB 연계 | PostgreSQL           | Backend가 담당                |
| LLM       | Claude Sonnet 계열 우선  |                            |
| RAG       | FAISS 또는 동급          | 추후 도입                      |

---

## 5. 현재 레포 구조

```text
devpick-ai/
├── app/
│   ├── collectors/     # RSS / RSS+크롤링 수집기
│   ├── configs/        # 수집 대상 소스 목록
│   ├── schemas/        # Pydantic 스키마
│   ├── services/       # 비즈니스 로직 (ingest, normalize, push)
│   ├── stores/         # raw JSONL 저장 + SentIdStore
│   └── utils/          # XML/HTML 파싱 헬퍼
├── docs/               # 운영/설계 문서
├── scripts/            # 일회성/운영 스크립트
├── tests/              # pytest 테스트
├── data/raw/           # 수집 원본 JSONL (gitignore)
├── main.py             # FastAPI 앱 진입점
└── requirements.txt
```

---

## 6. 브랜치 / 커밋 / PR 규칙

```bash
git checkout -b feature/DP-{티켓번호}-{기능명}
```

커밋 예시:
```text
feat: add summary response schema (DP-221)
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

# 1회 파이프라인 실행
BACKEND_URL=http://localhost:8080 python scripts/run_collect_and_push.py

# 스케줄러 (6시간 간격)
BACKEND_URL=http://localhost:8080 python scripts/run_scheduler.py

# Mongo 초기화
python scripts/init_mongo.py

# 테스트
pytest -q
```

---

## 9. 폴더별 CLAUDE.md

| 폴더 | CLAUDE.md |
|------|-----------|
| `app/` | [app/CLAUDE.md](app/CLAUDE.md) — 앱 전체 구조 개요 |
| `app/collectors/` | [app/collectors/CLAUDE.md](app/collectors/CLAUDE.md) — 수집기 클래스 |
| `app/schemas/` | [app/schemas/CLAUDE.md](app/schemas/CLAUDE.md) — Pydantic 스키마 |
| `app/stores/` | [app/stores/CLAUDE.md](app/stores/CLAUDE.md) — 저장소 및 dedup |
| `app/configs/` | [app/configs/CLAUDE.md](app/configs/CLAUDE.md) — 소스 설정 |
| `app/utils/` | [app/utils/CLAUDE.md](app/utils/CLAUDE.md) — XML/HTML 헬퍼 |
| `app/services/` | [app/services/CLAUDE.md](app/services/CLAUDE.md) — 서비스 레이어 |
| `scripts/` | [scripts/CLAUDE.md](scripts/CLAUDE.md) — 운영 스크립트 |
| `tests/` | [tests/CLAUDE.md](tests/CLAUDE.md) — 테스트 |
| `docs/` | [docs/CLAUDE.md](docs/CLAUDE.md) — 설계/운영 문서 |

---

## 10. 절대 잊지 말 것

* 이 레포의 1순위는 **안정적인 JSON 계약**이다.
* AI 품질만큼 **비용, 캐시, 실패 대응**이 중요하다.
* `.env`는 절대 커밋 금지. API Key 하드코딩 금지.
* AI 생성 코드라도 최종 책임은 PR 올린 사람에게 있다.
