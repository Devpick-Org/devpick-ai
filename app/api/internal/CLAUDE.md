# CLAUDE.md — app/api/internal/

Spring Boot ↔ FastAPI 내부 통신 전용 라우터. Base URL: `/internal`
외부 사용자가 접근하지 않으며, X-Internal-Key 인증이 필수다.

---

## 현재 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/internal/health` | AI 서버 내부 헬스체크 |
| POST | `/internal/summary` | 콘텐츠 AI 요약 생성 (DP-217) |

---

## 향후 추가 예정

| 메서드 | 경로 | 설명 | Epic |
|--------|------|------|------|
| POST | `/internal/answer` | 질문에 대한 AI 1차 답변 | D |
| POST | `/internal/report` | 주간 리포트 인사이트 생성 | F |

---

## 작성 원칙

- 모든 핸들러에 `dependencies=[Depends(verify_internal_key)]` 필수.
- 핸들러는 얇게 유지. 실제 처리는 `app/services/`에 위임.
- 응답은 JSON만 반환. HTTP 상태코드로 에러 표현.
