# CLAUDE.md — .github/

이 폴더는 GitHub 협업 설정 파일(CI 워크플로, PR 템플릿)을 보관한다.

---

## 폴더 구조

```
.github/
├── workflows/
│   └── ai-pr-check.yml      # CI: ruff, black --check, pytest
└── pull_request_template.md # PR 작성 시 자동으로 채워지는 본문 템플릿
```

---

## CI 게이트 — ai-pr-check.yml

**트리거 조건**: `develop` 브랜치 대상 PR 및 Push (`.py`, `requirements*.txt`, 워크플로 파일 변경 시)

**실행 단계 및 의미**

| 단계 | 명령 | 의미 |
|------|------|------|
| Ruff check | `ruff check .` | 린트 오류, 미사용 임포트 등 코드 품질 검사 |
| Black check | `black --check .` | 포맷 일관성 검사 (실제 수정은 로컬에서) |
| Pytest | `pytest -q` | 기능 회귀 방지, 테스트 통과 여부 확인 |

세 단계 모두 통과해야 PR 머지가 가능하다.

---

## 워크플로 수정 시 주의사항

- 워크플로를 변경하면 CI 자체가 영향을 받으므로 반드시 팀에 사전 공유한다
- 새 단계를 추가할 때는 로컬에서 먼저 동일한 명령이 통과하는지 확인한다
- 의존성(`requirements.txt`, `requirements-dev.txt`)을 변경하면 워크플로의 `cache-dependency-path`도 함께 확인한다
- `permissions: contents: read` 설정은 의도된 것이다. 쓰기 권한이 필요한 작업을 추가할 경우 명시적으로 선언한다

---

## PR 템플릿 — pull_request_template.md

PR 생성 시 본문에 자동으로 삽입되는 템플릿이다.

**필수 항목**
- **Jira 티켓**: 작업 추적을 위해 반드시 연결한다
- **작업내용**: 이 PR이 해결하는 문제 또는 목표를 명확히 기술한다
- **변경점**: 핵심 변경 3줄 요약
- **테스트**: 실행 명령, 요청 예시, 결과를 구체적으로 작성한다
- **AI 사용 여부**: Copilot, ChatGPT 등 사용 시 어디에 활용했는지 반드시 기록한다

**PR 템플릿을 수정할 경우**
- 팀 전체에 영향을 주므로 사전 합의 후 변경한다
- 항목을 삭제하기보다 선택 사항임을 명시하는 방향으로 조정한다

---

## 주의사항

- 이 폴더의 파일은 GitHub 자체 동작에 직접 영향을 준다. 실험적 변경은 별도 브랜치에서 먼저 검증한다
- 워크플로에 시크릿이 필요한 경우 코드에 값을 하드코딩하지 않고 `${{ secrets.SECRET_NAME }}` 형식으로 참조한다
