# CLAUDE.md — app/api/

FastAPI 라우터 레이어. Spring Boot ↔ FastAPI 내부 통신 엔드포인트와 인증 dependency를 관리한다.

---

## 현재 구조

| 파일 | 역할 |
|------|------|
| `deps.py` | X-Internal-Key 헤더 인증 FastAPI Dependency |
| `internal/router.py` | `/internal/*` 라우터 |

---

## 인증 흐름

모든 `/internal/*` 라우터는 `verify_internal_key` dependency를 통해 인증된다.

```
요청 → verify_internal_key(x_internal_key: Header)
         ├── 헤더 없음 → 422 (FastAPI 자동)
         ├── 키 불일치 → 401 Unauthorized
         └── 키 일치 → 라우터 핸들러 실행
```

키 값은 `.env`의 `INTERNAL_API_KEY`에서 읽는다. 서버 시작 시 1회 로드된다.

---

## 작성 원칙

- 라우터는 얇게 유지한다. 비즈니스 로직은 `app/services/`에 위치한다.
- 모든 `/internal/*` 엔드포인트는 `verify_internal_key` dependency를 달아야 한다.
- 에러는 HTTP 상태코드로만 표현한다 (Spring이 AI_001/002/003으로 변환).

---

## 폴더별 CLAUDE.md 링크

- [internal/CLAUDE.md](internal/CLAUDE.md)
