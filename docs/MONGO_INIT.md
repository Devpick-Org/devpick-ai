# DevPick AI Mongo 기본 세팅 (최소 세팅)

## 목적
DevPick AI에서 MongoDB를 **MVP 베이스**로 시작하기 위한 최소 초기화 문서입니다.
아직 컬렉션 상세 스키마가 확정 전이므로, 필수 컬렉션과 인덱스/기본 메타 설정만 적용합니다.

## 구성 요소
- `.env.example`
  - `APP_ENV`, `SERVER_PORT`
  - `MONGO_URI`, `MONGO_DB`
  - `ANTHROPIC_API_KEY`, 선택 `OPENAI_API_KEY`
- `.gitignore`
  - `.env`, `.env.*`는 커밋 제외
  - `!.env.example`는 커밋 허용
- `requirements-dev.txt`
  - `pymongo`, `python-dotenv`, `pytest`, `ruff`, `black`
- `scripts/init_mongo.py`
  - Mongo 연결 확인(ping)
  - 최소 컬렉션/인덱스 생성
  - 기본 설정 seed(upsert)

## 현재 적용 범위
### 1) `contents` 컬렉션
- `ux_contents_url` (unique + sparse)
  - 동일 `url` 중복 저장 방지
  - `url`이 없는 문서는 허용(sparse)
- `ux_contents_source_external` ((`source`, `external_id`) unique + sparse)
  - 외부 소스 기반 식별자 중복 방지
  - 일부 필드가 없는 문서는 허용(sparse)
- `ix_contents_created_at_desc` (`created_at` 내림차순)
  - 최신 생성 문서 조회 성능 개선

### 2) `configs` 컬렉션
- `ux_configs_key` (`key` unique)
  - 설정 키 중복 방지

### seed/upsert 데이터
- `key=schema_version`, `value=1`
  - upsert로 유지
  - `created_at`/`updated_at` 관리
- `key=initialized_at`
  - 최초 1회만 `setOnInsert`로 기록

## 실행 방법

### 1) devpick-infra에서 MongoDB 실행
`devpick-infra` 디렉터리에서:

```bash
docker compose up -d mongodb
```

(전체 스택 실행 시)

```bash
docker compose up -d
```

### 2) devpick-ai 환경변수 준비
`devpick-ai` 디렉터리에서:

```bash
cp .env.example .env
```

실행 환경에 맞게 `MONGO_URI`를 설정합니다.

- 도커 네트워크 내부(컨테이너 간 통신):
  - host를 `mongodb` 사용
  - 예: `mongodb://<MONGO_USERNAME>:<MONGO_PASSWORD>@mongodb:27017/devpick`
- 호스트(내 PC)에서 실행:
  - host를 `localhost` 사용
  - 예: `mongodb://<MONGO_USERNAME>:<MONGO_PASSWORD>@localhost:27017/devpick`

### 3) 의존성 설치 및 초기화 스크립트 실행

```bash
pip install -r requirements.txt -r requirements-dev.txt
python scripts/init_mongo.py
```

## 변경 대비 원칙
- Mongo 접속은 **항상 `MONGO_URI`로 통일**합니다.
- 초기화는 앱 자동 실행이 아닌 **별도 스크립트 1회 실행 방식**으로 유지합니다.
- 향후 스키마 확장은 `schema_version`을 기준으로 단계적으로 관리합니다.

## 재실행 안전성(idempotent)
- 인덱스는 동일 이름/정의로 반복 생성해도 동일 상태 유지
- seed는 `upsert`/`setOnInsert` 사용으로 재실행 시 데이터 일관성 유지
