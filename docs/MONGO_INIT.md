# MongoDB 초기화 및 최소 세팅 (DevPick AI)

목적: devpick-ai가 필요로 하는 최소 MongoDB 컬렉션과 인덱스를 초기화하기 위한 문서 및 스크립트입니다. 이 초기화는 "별도 스크립트 1회 실행" 방식이며 재실행해도 안전(idempotent)합니다.

devpick-infra (참고)
- MongoDB 서비스명: `mongodb`
- MongoDB 컨테이너명: `devpick-mongodb`
- 포트: `27017:27017`
- 초기 인증 환경변수(예):
  - `MONGO_INITDB_ROOT_USERNAME=${MONGO_USERNAME}`
  - `MONGO_INITDB_ROOT_PASSWORD=${MONGO_PASSWORD}`
  - `MONGO_INITDB_DATABASE=${MONGO_DB}`
- 컨테이너 내부에서의 접속 URI 예시 (환경변수로 설정되어 사용됨):
  - `MONGO_URI=mongodb://${MONGO_USERNAME}:${MONGO_PASSWORD}@mongodb:27017/${MONGO_DB}`

구성 요소
- `.env.example` : 환경변수 템플릿(커밋됨). 실제 비밀값은 넣지 마세요.
- `.gitignore` : `.env`와 `.env.*` 를 무시하도록 보강됨(템플릿은 허용).
- `requirements-dev.txt` : 개발/초기화용 의존성 목록(`pymongo`, `python-dotenv` 등).
- `scripts/init_mongo.py` : 초기화 스크립트(재실행 안전).

적용 범위(최소)
- 컬렉션: `contents`, `configs`
- `contents` 인덱스:
  - `ux_contents_url` : `url` 필드, unique + sparse (중복 방지)
  - `ux_contents_source_external` : `(source, external_id)` 복합 unique + sparse (외부 연동 중복 방지)
  - `ix_contents_created_at_desc` : `created_at` 내림차순(조회 정렬 최적화)
- `configs` 인덱스:
  - `ux_configs_key` : `key` unique (설정 키 중복 방지)

초기 시드 동작
- `configs`에 `key="schema_version"`, `value=1` upsert (created_at/updated_at 포함)
- `configs`에 `key="initialized_at"` 은 최초 실행 시에만 삽입(setOnInsert)

실행 방법
1. devpick-infra에서 Mongo 올리기(예):

```bash
cd ../devpick-infra
docker-compose up -d mongodb
```

2. devpick-ai쪽에서 환경파일 준비

```bash
cd /path/to/devpick-ai
cp .env.example .env
# .env 편집: dev 환경에서는 MONGO_URI를 내부 도커 네트워크용(host: mongodb)로 설정
# 로컬에서 직접 실행할 경우 localhost URI 주석 예시를 참고
```

3. 의존성 설치 및 스크립트 실행

```bash
pip install -r requirements.txt -r requirements-dev.txt
python scripts/init_mongo.py
```

원칙 및 주의사항
- 접속은 `MONGO_URI` 로 통일합니다. (앱/스크립트 모두 동일 env 사용)
- 초기화는 스크립트 방식으로만 수행하며 앱 시작시 자동 실행하지 않습니다.
- 변경 이력 관리는 `schema_version` 값을 활용해 점진적 마이그레이션을 수행합니다.
- 실제 비밀번호/키는 절대 커밋하지 마세요.
