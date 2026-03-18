# DevPick AI — 인수인계 문서

> **이 문서는 devpick-ai 레포에서 마지막으로 진행 중이던 작업의 컨텍스트를 담고 있다.**
> 중간에 작업을 넘겨받거나, 시간이 지나 다시 작업을 재개할 때 이 문서부터 읽으면 된다.
> 완료된 작업 현황, 다음 작업 명세, 주의사항, 이후 로드맵 순으로 정리되어 있다.

> 마지막 업데이트: 2026-03-18
> 담당: 수헌

---

## 현재 브랜치

`feature/DP-218-rag-pipeline`

> PR 대상 브랜치: `develop`

---

## 완료된 작업

### DP-215 — /internal 라우터 + X-Internal-Key 인증 + 에러 핸들러
- `app/api/deps.py` — X-Internal-Key 인증 dependency
- `app/api/internal/` — `/internal/*` 라우터

### DP-216 — 전처리 파이프라인 (HTML → 구조 보존 텍스트)
- `app/services/preprocess_service.py` — `PreprocessService.preprocess(html: str) -> str`
- `app/schemas/summary.py` — `SummaryResponse` Pydantic 스키마
- `tests/test_preprocess_service.py` — 17개 테스트 통과

### DP-219 — 레벨별 AI 요약 프롬프트 + SummaryService
- `app/core/prompts/summary.py` — SYSTEM_PROMPT + SUMMARY_TOOL(Tool Use 스키마) + `build_user_prompt()`
- `app/services/summary_service.py` — Claude API 호출 + SummaryResponse 파싱
- `tests/test_summary_service.py` — mock 기반 단위 테스트 6개 통과

**SummaryService 핵심 설계:**
- **Tool Use**: `tool_choice={"type": "tool", "name": "save_summary"}` — JSON 파싱 실패 0%
- **Prompt Caching**: system 블록에 `cache_control: ephemeral` — 비용 90% 절감
- **Temperature 0**: 일관성 + 속도

**SummaryResponse 스키마 필드 (최종):**
```python
content_id: str
level: Literal["junior", "mid", "senior"]
one_line_summary: str
core_summary: list[SectionSummary]   # 소제목별 요약 (heading + content)
key_points: list[str]
keywords: list[str]
tags: list[str]                      # AI 추출 기술 카테고리
difficulty: Literal["easy", "medium", "hard"]
next_recommendation: str
study_questions: list[str]
confidence: float                    # 0.0 ~ 1.0
generated_at: str                    # ISO 8601
thumbnail_url: str | None = None     # 호출자 주입, AI 생성 아님
```

### DP-217 — POST /internal/summary 엔드포인트
- `app/schemas/summary.py` — `SummaryRequest` 스키마 추가
- `app/api/internal/router.py` — `POST /internal/summary` 엔드포인트
- `tests/test_summary_endpoint.py` — TestClient 통합 테스트 6개 통과

### DP-220 — AI 요약 결과 MongoDB ai_summaries 저장
- `app/repositories/summary_repository.py` — MongoDB 저장 레이어

### DP-223 — AI 요약 실패 시 에러 분류 + 재시도 가능 응답
### DP-291 — NormalizedContent 썸네일 필드 추가 및 본문 이미지 fallback 추출
### DP-292 — NormalizedContent 스키마 정렬 및 정규화 구조 개선

---

## 다음 작업: DP-218 — LangChain + FAISS RAG 파이프라인 구현

**브랜치**: `feature/DP-218-rag-pipeline`

---

## 이후 작업 순서

### Epic C — AI 요약

| 티켓 | 내용 | 상태 | 비고 |
|------|------|------|------|
| DP-218 | LangChain + FAISS RAG 파이프라인 구현 | 진행 중 | |
| DP-226 | AI 요약 Golden Set 테스트 작성 | 대기 | API 키 발급 후 진행 |

### Epic D — 질문/커뮤니티

| 티켓 | 내용 | 상태 | 비고 |
|------|------|------|------|
| DP-235 | 유사 질문 탐색 API 개발 (FAISS) | 진행 중 | DP-218 완료 후 |
| DP-231 | AI 질문 개선 프롬프트 작성 및 테스트 | 진행 중 | |
| DP-234 | AI 1차 답변 프롬프트 작성 및 테스트 | 해야 할 일 | DP-233 전에 선행 |
| DP-233 | AI 답변 자동 생성 API 개발 | 진행 중 | DP-234 완료 후 |
| DP-232 | 사용자가 AI 1차 답변을 받을 수 있다 (스토리) | 해야 할 일 | DP-233, DP-234 완료 후 |

### Epic E — 학습 히스토리

| 티켓 | 내용 | 상태 |
|------|------|------|
| DP-252 | 이벤트 로그 MongoDB 저장 | 해야 할 일 |

### Epic F — 주간 리포트

| 티켓 | 내용 | 상태 | 비고 |
|------|------|------|------|
| DP-260 | AI 인사이트 프롬프트 작성 및 테스트 | 해야 할 일 | DP-259 전에 선행 |
| DP-259 | AI 인사이트 생성 API 개발 (FastAPI) | 해야 할 일 | DP-260 완료 후 |

### MVP+

| 티켓 | 내용 | 상태 |
|------|------|------|
| DP-265 | AI 퀴즈 생성 API 개발 (FastAPI) | 해야 할 일 |
| DP-267 | 학습 자료 추천 API 개발 | 해야 할 일 |

---

## 로컬 실행 확인

```bash
# 의존성
pip install -r requirements.txt -r requirements-dev.txt

# 테스트
pytest -q

# 린트/포맷
ruff check . && black --check .

# 개발 서버
uvicorn main:app --reload
```
