# CLAUDE.md — app/schemas/

Pydantic 기반 데이터 계약. 수집부터 전송까지 모든 데이터 형태를 정의한다.

---

## 현재 스키마

| 파일 | 클래스 | 역할 |
|------|--------|------|
| `source.py` | `SourceConfig` | 수집 대상 소스 설정 (URL, 레벨, 활성 여부) |
| `raw_content.py` | `RawEntry` | 수집기가 반환하는 원시 항목 |
| `raw_content.py` | `RawFeedMeta` | 피드 메타 정보 (제목, 수집 시각 등) |
| `normalized_content.py` | `NormalizedContent` | Backend로 전송하는 최종 정규화 항목 |

---

## 스키마 설계 원칙

- 모든 스키마는 Pydantic `BaseModel`을 상속한다.
- 필드는 타입 힌트 필수. `Optional` 필드는 명시적으로 `= None` 처리.
- `RawEntry` → `NormalizedContent` 변환은 `NormalizeService`가 담당하며, 스키마 자체에 로직을 두지 않는다.
- 스키마 변경 시 관련 테스트(`test_normalize_service.py` 등)도 함께 업데이트한다.

---

## 향후 추가 예정

AI 기능이 추가되면 아래 스키마가 생긴다.

| 파일 | 클래스 | 역할 |
|------|--------|------|
| `summary.py` | `SummaryResponse` | AI 요약 출력 스키마 |
| `refine.py` | `RefineResponse` | 질문 개선 출력 스키마 |
| `answer.py` | `AnswerResponse` | AI 1차 답변 출력 스키마 |
| `report.py` | `ReportResponse` | 주간 리포트 출력 스키마 |

AI 출력 스키마는 반드시 먼저 정의하고 구현한다. 스키마 없는 AI 출력은 허용하지 않는다.
