# Devpick AI

DevPick 캡스톤 프로젝트의 AI 서버입니다.

## 설치 및 실행

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## 환경변수 설정

`.env.example` 파일을 복사해 `.env` 파일을 생성하세요.

```bash
cp .env.example .env
```

Windows PowerShell에서는 아래 명령을 사용하세요.

```powershell
Copy-Item .env.example .env
```

## 헬스체크 호출 예시

```bash
curl http://127.0.0.1:8000/health
```

응답 예시:

```json
{"status":"ok"}
```

## CI 파이프라인 (PR 체크)

GitHub Actions 워크플로 `AI PR Checks`가 아래 조건에서 실행됩니다.

- `develop` 브랜치 대상 Pull Request
- `develop` 브랜치로의 Push
- 관련 파일 변경 시: `**/*.py`, `requirements.txt`, `requirements-dev.txt`, `.github/workflows/ai-pr-check.yml`

체크 항목:

- `ruff check .`
- `black --check .`
- `pytest -q`

워크플로 파일: [.github/workflows/ai-pr-check.yml](.github/workflows/ai-pr-check.yml)

로컬에서 PR 전 동일하게 확인하려면:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
ruff check . && black --check . && pytest -q
```


