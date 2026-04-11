# CLAUDE.md — app/core/

AI 기능의 프롬프트 템플릿, 설정, 공통 유틸을 관리하는 레이어다.

---

## 현재 구조

```text
core/
├── bedrock.py      # Bedrock Converse API 공통 유틸 (to_tool_config)
├── exceptions.py   # AI 서비스 커스텀 예외 계층 (DP-223)
└── prompts/        # AI 기능별 프롬프트 + Tool Use 스키마
    ├── summary.py  # 4레벨 요약 프롬프트 (DP-300)
    ├── quiz.py     # 4레벨 퀴즈 프롬프트 (DP-265)
    ├── refine.py   # 질문 개선 프롬프트 (DP-231)
    ├── answer.py   # 1차 답변 프롬프트 (DP-234)
    └── insight.py  # 주간 인사이트 프롬프트 (DP-260)
```

---

## 예외 계층 (exceptions.py, DP-223)

```
AIServiceError (base, status_code + message)
├── AIBadRequestError  → 400  잘못된 입력 (level, text)
├── AIUpstreamError    → 502  LLM 연결 실패 / Rate Limit / API 에러
├── AITimeoutError     → 504  LLM 타임아웃
└── AIInternalError    → 500  파싱 실패 / tool_use 없음
```

---

## bedrock.py

```python
to_tool_config(tool: dict, tool_name: str) -> dict
```

Anthropic Tool Use 스키마를 Bedrock Converse API `toolConfig` 형식으로 변환한다.
모든 서비스에서 공통 사용.

---

## prompts/ 상세

| 파일 | 핵심 내용 |
|------|-----------|
| `summary.py` | `SYSTEM_PROMPT_ALL_LEVELS`, `SUMMARY_ALL_LEVELS_TOOL`, `build_user_prompt_all_levels()` — beginner/junior/mid/senior 4레벨 동시 요약 |
| `quiz.py` | `SYSTEM_PROMPT_QUIZ`, `QUIZ_TOOL`, `build_user_prompt()` — 4레벨 동시 퀴즈 (같은 개념, 레벨별 용어·표현 조정) |
| `refine.py` | `SYSTEM_PROMPT`, `REFINE_TOOL`, `build_user_prompt()` — 레벨별 질문 개선 + 컨텍스트 청크 |
| `answer.py` | `SYSTEM_PROMPT`, `ANSWER_TOOL`, `build_user_prompt()` — 아티클+RAG 컨텍스트 기반 답변 |
| `insight.py` | `SYSTEM_PROMPT`, `INSIGHT_TOOL`, `build_user_prompt()` — 주간 활동/읽은글/스크랩/질문 기반 인사이트 |

### quiz.py 구성 요소 (DP-265)

- `SYSTEM_PROMPT_QUIZ` — 4레벨 동시 출제 기준. 레벨별 용어 표현 기준 명시. Prompt Caching 대상
- `_QUESTIONS_SCHEMA` — 레벨별 questions 배열 스키마 (재사용)
- `QUIZ_TOOL` — `save_quiz` Tool Use input_schema. `beginner/junior/mid/senior` 4개 필드 required
- `build_user_prompt(text)` — 4레벨 동시 출제 지시문 + 본문

**레벨별 표현 기준:**
- `beginner`: 기술 용어 첫 등장 시 괄호 설명. 예: "캐시(임시 저장공간)"
- `junior`: 기본 용어 + 생소한 개념 한 문장 부연, 원리 위주 해설
- `mid`: 표준 기술 용어, 간결
- `senior`: 전문 용어·약어, 트레이드오프·심화 포함

### summary.py 구성 요소 (DP-300)

- `SYSTEM_PROMPT_ALL_LEVELS` — 4레벨 동시 요약 기준. Prompt Caching 대상
  - 레벨별 독자 관점 차별화: beginner(스토리), junior(과정·판단 근거), mid(수치·패턴), senior(설계·트레이드오프)
  - core_summary: 원본 소제목 구조 따르기, string 포맷(`heading\ncontent\n\n...`)
- `SUMMARY_ALL_LEVELS_TOOL` — `save_all_summaries` Tool Use input_schema. `core_summary` 타입: string
- `build_user_prompt_all_levels(text)` — 4레벨 지시문 + core_summary string 형식 리마인더 + 본문

---

## 프롬프트 작성 원칙

- 프롬프트는 서비스 코드에 직접 쓰지 않는다. 반드시 `core/prompts/`에 분리한다
- Tool Use 스키마(`input_schema`)와 Pydantic 스키마(`app/schemas/`)의 필드를 일치시킨다
- 시스템 프롬프트는 Prompt Caching 효율을 위해 자주 변경하지 않는다
