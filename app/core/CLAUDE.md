# CLAUDE.md — app/core/

AI 기능의 프롬프트 템플릿, 설정, 공통 유틸을 관리하는 레이어다.

---

## 현재 구조

```text
core/
├── exceptions.py   # AI 서비스 커스텀 예외 계층 (DP-223)
└── prompts/        # AI 기능별 프롬프트 + Tool Use 스키마
    ├── summary.py  # 요약 프롬프트 (DP-219)
    ├── refine.py   # 질문 개선 프롬프트 (DP-231)
    └── answer.py   # 1차 답변 프롬프트 (DP-234)
```

---

## 예외 계층 (exceptions.py, DP-223)

```
AIServiceError (base, status_code + message)
├── AIBadRequestError  → 400  잘못된 입력 (level, text)
├── AIUpstreamError    → 502  LLM 연결 실패 / Rate Limit / API 에러
├── AITimeoutError     → 504  LLM 타임아웃
└── AIInternalError    → 500  인증 실패 / 파싱 실패 / tool_use 없음
```

백엔드(Spring Boot)가 HTTP 상태코드로 AI_001/002/003을 변환한다:
- 400, 500 → AI_001 (재시도 불가)
- 502 → AI_001 (재시도 가능)
- 504 → AI_002 (타임아웃, 재시도 가능)

**규칙**: 에러는 HTTP 상태코드로만 표현한다. 별도 에러 코드 필드 없음.

---

## prompts/ 상세

| 파일 | 내용 |
|------|------|
| `summary.py` | `SYSTEM_PROMPT`, `SUMMARY_TOOL` (Tool Use 스키마), `build_user_prompt()` (레벨별 지시문 생성) |
| `refine.py` | `SYSTEM_PROMPT`, `REFINE_TOOL` (Tool Use 스키마), `build_user_prompt()` (레벨별 지시문 + 컨텍스트 청크) (DP-231) |
| `answer.py` | `SYSTEM_PROMPT`, `ANSWER_TOOL` (Tool Use 스키마), `build_user_prompt()` (아티클 + RAG + 원본 질문 + 태그 섹션) (DP-234) |

### summary.py 구성 요소

- `SYSTEM_PROMPT` — 필드별 작성 기준을 포함한 시스템 프롬프트. Prompt Caching 대상
- `SUMMARY_TOOL` — `save_summary` Tool Use input_schema. 9개 필드 required
- `_LEVEL_INSTRUCTIONS` — junior/mid/senior 레벨별 요약 관점 지시문
- `build_user_prompt(level, text)` — 레벨 지시문 + 본문을 결합하여 user 메시지 생성

---

## 프롬프트 작성 원칙

- 프롬프트는 서비스 코드에 직접 쓰지 않는다. 반드시 `core/prompts/`에 분리한다
- Tool Use 스키마(`input_schema`)와 Pydantic 스키마(`app/schemas/`)의 필드를 일치시킨다
- 시스템 프롬프트는 Prompt Caching 효율을 위해 자주 변경하지 않는다
- 레벨별 지시문은 `_LEVEL_INSTRUCTIONS` dict으로 관리하여 확장이 용이하게 한다

---

### answer.py 구성 요소 (DP-234)

- `SYSTEM_PROMPT` — "DevPick 기술 질문 답변 전문가". refined 질문 기반 정확한 답변, original로 눈높이 조절
- `ANSWER_TOOL` — `save_answer` Tool Use input_schema. 5개 필드: `answer_content`, `key_points`, `suggested_tags`, `references`, `confidence`
  - `references`: LLM이 활용한 content_id 리스트 (내부용 — AnswerResponse에는 미포함, 라우터가 related_contents로 변환)
- `build_user_prompt(refined_title, refined_content, original_title?, original_content?, suggested_tags?, article_chunks?, rag_chunks?)`:
  - 섹션 순서: `## 관련 아티클` → `## 참고 문서` → `## 원본 질문` → `## 관련 기술 태그` → `## 질문`
  - 빈 refined_title/refined_content → `ValueError`

---

## 향후 추가 예정

| 파일 | 역할 |
|------|------|
| `prompts/report.py` | 주간 리포트 프롬프트 (Epic F) |
| `config.py` | 공통 설정 (모델명, temperature 등) |
| `logging.py` | 로깅 설정 |
