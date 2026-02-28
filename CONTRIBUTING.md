# Contributing Guide
처음 GitHub를 쓰는 DevPick 팀을 위한 **최소 규칙**입니다.  
목표는 간단합니다: **실수 줄이고(직접 push/PR 누락), 충돌 줄이고, 누구나 같은 방식으로 작업하기.**

---

## 0) 5가지 기본 원칙
- **main / develop 직접 push 금지** → 모든 변경은 PR로만 이동
- 작업은 **Jira 티켓 단위**로 진행(브랜치/PR/커밋에 티켓 번호 남기기)
- **작게 나눠서** 올리기(작은 PR, 작은 커밋)
- `.env`, 토큰, 키 등 **시크릿은 절대 커밋 금지**
- 30분 이상 막히면 **바로 공유**(같은 문제로 시간 낭비하지 않기)

---

## 1) 브랜치 지도(어디서 무엇을 하나요?)
- `main` : 배포 기준(안정) 브랜치 — **직접 작업/직접 push 금지**
- `develop` : 개발 통합 브랜치 — feature PR이 모이는 곳
- `feature/*` : 기능 개발 브랜치 — 새 기능/개선
- `fix/*` : 버그 수정 브랜치 — 개발/테스트 중 발견된 버그
- `hotfix/*` : 운영 긴급 수정 — 배포 장애/치명 이슈

### 네이밍 규칙(권장)
- `feature/DP-###-short-desc`
- 예시(DevPick AI 맥락):
  - `feature/DP-139-ai-init`
  - `feature/DP-150-summary-endpoint`
  - `fix/DP-162-json-parse-error`
  - `hotfix/DP-170-prod-timeout`

---

## 2) 표준 작업 흐름(체크리스트)
아래 순서만 지켜도 사고가 거의 안 납니다.

1. `develop` 최신화
2. 새 브랜치 생성
3. 기능 개발
4. 로컬 테스트/실행 확인
5. 커밋(작게)
6. 원격 push
7. PR 생성(`feature/*` → `develop`)
8. 리뷰 1명 이상 승인
9. 머지(권장: Squash)
10. 브랜치 정리(삭제)

---

## 3) PR 통행증(규칙)
### PR 크기
- 가능한 **작게**: 한 번에 이해되는 정도가 목표
- 가이드: 변경이 너무 크면(대략 수백 줄 이상) **PR을 쪼개기**를 먼저 고민

### PR 제목 규칙
- 형식: **`[type] 작업 요약`**
- type 예시: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`
- 예시:
  - `[feat] 요약 API 스켈레톤 추가`
  - `[fix] 요약 결과 스키마 누락 수정`

### PR 본문 템플릿(복붙)
```text
## Jira
- DP-### (링크)

## 의도(왜?)
- 이 PR이 해결하는 문제/목표

## 변경점(무엇?)
- 핵심 변경 3줄 요약

## 테스트(어떻게 확인?)
- 실행 명령 / 요청 예시 / 결과
- 예) uvicorn 실행, /health 또는 /summary 호출

## 리스크/주의사항(있다면)
- 배포/호환/마이그레이션 등

## AI 사용 여부
- Copilot/ChatGPT 사용 여부 + 어디에 사용했는지
```

### 승인 & 머지
- 승인 1개 이상 필수
- 승인 받기 전 혼자 머지하지 않기(급한 경우도 팀에 먼저 공유)

---

## 4) 커밋 규칙(짧고 일관되게)
### 커밋 메시지 포맷(권장)
- `type: 내용 (DP-###)`

예시:
- `feat: add summary endpoint skeleton (DP-150)`
- `fix: handle invalid json output (DP-162)`
- `docs: add contributing guide (DP-139)`

### type 추천
- `feat` 기능
- `fix` 버그
- `docs` 문서
- `chore` 설정/초기화
- `refactor` 리팩토링
- `test` 테스트

---

## 5) GitHub 보호 설정(권장)
`main`, `develop` 브랜치에 대해 아래 설정을 권장합니다.

- Pull Request 필수
- 최소 승인 1개
- 머지 전 CI 통과 필수(추후 Actions 붙이면 적용)
- Force push 금지

---

## 6) 머지 방식(처음 팀에 추천)
- **Squash and merge** 권장
- 이유: 커밋 히스토리가 깔끔하고, 되돌리기(rollback)가 쉽습니다.

---

## 7) 실전 명령어 모음
### (1) develop 최신화
```bash
git checkout develop
git pull origin develop
```

### (2) 브랜치 만들기
```bash
git checkout -b feature/DP-139-ai-init
```

### (3) 스테이징(add) 남아있나 확인
```bash
git status
git diff --cached --name-only
```

### (4) 커밋
```bash
git add .
git commit -m "chore: init ai service skeleton (DP-139)"
```

### (5) push
```bash
git push -u origin feature/DP-139-ai-init
```

### (6) (선택) 머지 후 브랜치 정리
```bash
git checkout develop
git pull origin develop
git branch -d feature/DP-139-ai-init
git push origin --delete feature/DP-139-ai-init
```
