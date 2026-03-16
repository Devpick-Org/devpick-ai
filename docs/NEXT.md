# DevPick AI — 인수인계 문서

> **이 문서는 devpick-ai 레포에서 마지막으로 진행 중이던 작업의 컨텍스트를 담고 있다.**
> 중간에 작업을 넘겨받거나, 시간이 지나 다시 작업을 재개할 때 이 문서부터 읽으면 된다.
> 완료된 작업 현황, 다음 작업 명세, 주의사항, 이후 로드맵 순으로 정리되어 있다.

> 마지막 업데이트: 2026-03-16
> 담당: 수헌

---

## 현재 브랜치

`feature/DP-219-summary-prompt`

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

**PreprocessService 처리 순서:**
1. `script`, `style`, `noscript`, `iframe` 태그 제거
2. nav, footer, sidebar 등 노이즈 섹션 제거
3. DOM 순회 → 구조 보존 텍스트 변환 (heading → `#`, code → ` ``` `, list → `-`)
4. 공백 정규화 (코드블록 내부 보호)
5. 보일러플레이트 라인 제거 ("공유하기", "구독하기" 등)

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

---

## 다음 작업: DP-217 — AI 요약 엔드포인트 (`POST /internal/summary`)

**브랜치**: `feature/DP-219-summary-prompt` (현재 브랜치에서 이어서 작업)

### 배경

SummaryService(DP-219)가 완료된 상태. Spring Boot 백엔드(`devpick-backend`)의 `AiServerClient.java`가 호출할 FastAPI 요약 엔드포인트를 구현한다.
백엔드 레포 확인 결과 계약 불일치가 있어 양쪽 조율이 필요하다.

### 백엔드와의 계약 불일치 해결 방향

| # | 항목 | 현재 상태 | 해결 방향 | 수정 주체 |
|---|------|----------|----------|----------|
| 1 | **text 전달** | 백엔드가 content_id + level만 전송 | 백엔드가 text도 함께 전송 | ✅ 백엔드 (확정) |
| 2 | **core_summary 타입** | 백엔드: string, AI: list[SectionSummary] | 백엔드도 list 구조 수용 | ✅ 백엔드 (확정) |
| 3 | **경로** | 백엔드: `/api/summary`, AI: `/internal/summary` | `/internal/summary` 추천 (백엔드 URL 변경) | 🔶 상의 필요 |
| 4 | **레벨 값** | 백엔드: JUNIOR/MIDDLE/SENIOR, AI: junior/mid/senior | AI 서버에서 매핑 (저비용) | 🔶 상의 필요 |
| 5 | **필드명** | 백엔드: `additional_questions`, AI: `study_questions` | `study_questions` 유지 추천 (의미 더 정확) | 🔶 상의 필요 |
| 6 | **추가 필드** | AI가 one_line_summary, tags 등 추가 반환 | AI가 전부 반환, 백엔드는 필요한 것만 사용 | 🔶 상의 필요 |

**추천 근거:**
- **3. 경로**: AI 서버는 이미 `/internal/*` + `X-Internal-Key` 인증 세팅 완료. `/api/`는 외부 공개 API와 혼동 가능. 백엔드는 `AiServerClient.java`에서 URL 한 줄만 수정
- **4. 레벨**: 백엔드가 이미 `JUNIOR/MIDDLE/SENIOR` enum을 쓰고 있으므로 AI 쪽 라우터에서 매핑 테이블로 변환하는 게 저비용. `{"JUNIOR": "junior", "MIDDLE": "mid", "SENIOR": "senior"}`
- **5. 필드명**: `study_questions`가 "학습 점검 질문" 의미를 더 정확히 전달. `additional_questions`는 "추가 질문"으로 모호
- **6. 추가 필드**: Jackson이 unknown fields는 기본적으로 무시하므로 (`FAIL_ON_UNKNOWN_PROPERTIES = false`) 백엔드에 영향 없음. 나중에 프론트에서 `one_line_summary`나 `tags`를 쓰고 싶으면 백엔드 DTO만 확장

### 수정 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `app/schemas/summary.py` | `SummaryRequest` 스키마 추가 |
| `app/api/internal/router.py` | `POST /internal/summary` 엔드포인트 추가 |
| `tests/test_summary_endpoint.py` | 엔드포인트 통합 테스트 (TestClient) |
| `app/api/internal/CLAUDE.md` | 엔드포인트 문서 업데이트 |

### 1. 요청 스키마 — `app/schemas/summary.py`

```python
class SummaryRequest(BaseModel):
    """백엔드 → AI 서버 요약 요청."""
    content_id: str
    level: str                          # 백엔드에서 오는 값 (JUNIOR/MIDDLE/SENIOR)
    text: str = Field(min_length=1)     # 전처리된 본문 텍스트 (빈 문자열 방지)
    thumbnail_url: str | None = None
```

- `text`에 `min_length=1`을 걸어 빈 문자열이 오면 Pydantic이 422로 자동 거부
- SummaryService의 `ValueError("요약할 텍스트가 없습니다")` 이전에 차단됨

### 2. 레벨 매핑 + 엔드포인트 — `app/api/internal/router.py`

```python
import os
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from app.api.deps import verify_internal_key
from app.schemas.summary import SummaryRequest, SummaryResponse
from app.services.summary_service import SummaryService

load_dotenv()
_ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

_LEVEL_MAP = {
    "JUNIOR": "junior",
    "MIDDLE": "mid",
    "SENIOR": "senior",
}

@router.post("/summary", dependencies=[Depends(verify_internal_key)])
def create_summary(req: SummaryRequest) -> SummaryResponse:
    level = _LEVEL_MAP.get(req.level.upper())
    if level is None:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 레벨: {req.level}")

    if not _ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    svc = SummaryService(api_key=_ANTHROPIC_API_KEY)
    return svc.summarize(
        content_id=req.content_id,
        level=level,
        text=req.text,
        thumbnail_url=req.thumbnail_url,
    )
```

**설계 포인트:**
- `_ANTHROPIC_API_KEY`는 `deps.py`와 동일 패턴으로 모듈 로드 시 1회 읽음
- 레벨 매핑 실패 시 400 반환 (서비스까지 내려가지 않음)
- API 키 미설정 시 500 반환 (명확한 에러 메시지)
- `SummaryService`에서 발생하는 `ValueError`(빈 text 등)는 글로벌 핸들러가 500으로 처리
- Anthropic API 에러(rate limit, 네트워크 등)도 글로벌 500 핸들러가 처리

### 3. 테스트 — `tests/test_summary_endpoint.py`

TestClient로 실제 HTTP 요청 테스트 (SummaryService는 mock):

| 테스트 | 검증 |
|--------|------|
| `test_summary_success` | 정상 요청 → 200 + SummaryResponse |
| `test_summary_level_mapping` | MIDDLE → mid 매핑 확인 |
| `test_summary_missing_auth` | X-Internal-Key 없음 → 422 |
| `test_summary_wrong_auth` | 잘못된 키 → 401 |
| `test_summary_empty_text` | text="" → 422 (Pydantic min_length) |
| `test_summary_invalid_level` | 존재하지 않는 레벨 → 400 |

### 4. 난이도 평가

**낮음**. 라우터는 얇은 레이어 — 기존 패턴(`/internal/health`)과 동일. SummaryService는 이미 완성 + 테스트됨. 인증도 기존 `verify_internal_key` 재사용. 새로운 의존성 없음.

핵심은 **백엔드와의 계약 합의**이지, 코드 구현 자체가 아님.

### 백엔드 팀에게 전달할 변경 목록

1. **`AiServerClient.java`**: URL `/api/summary` → `/internal/summary`, 요청에 `text` 필드 추가
2. **`AiSummaryResult.java`**: `core_summary`를 `List<CoreSummarySection>` 타입으로 변경, `additional_questions` → `study_questions`
3. **`AiSummaryDocument.java`** (MongoDB): 동일하게 구조 변경
4. **`AiSummaryResponse.java`** (프론트 응답 DTO): core_summary 구조 반영

### 검증

```bash
# 1. 엔드포인트 테스트
pytest tests/test_summary_endpoint.py -v

# 2. 전체 CI
ruff check . && black --check . && pytest -q

# 3. 수동 확인 (서버 띄운 후)
curl -X POST http://localhost:8000/internal/summary \
  -H "X-Internal-Key: {키값}" \
  -H "Content-Type: application/json" \
  -d '{"content_id":"test-001","level":"JUNIOR","text":"테스트 본문"}'
```

---

## 이후 작업 순서 (Epic C)

| 티켓 | 내용 | 비고 |
|------|------|------|
| DP-219 | 레벨별 AI 요약 프롬프트 + SummaryService | ✅ 완료 |
| DP-217 | AI 요약 엔드포인트 (`POST /internal/summary`) | 🔶 현재 작업 |
| DP-220 | AI 요약 결과 MongoDB 저장 | |
| DP-218 | LangChain + FAISS RAG 파이프라인 | |
| DP-226 | AI 요약 Golden Set 테스트 | |

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
