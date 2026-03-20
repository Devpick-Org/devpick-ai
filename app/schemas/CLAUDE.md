# CLAUDE.md — app/schemas/

Pydantic 기반 데이터 계약. 수집부터 전송까지 모든 데이터 형태를 정의한다.

---

## 현재 스키마

| 파일 | 클래스 | 역할 |
|------|--------|------|
| `source.py` | `SourceConfig` | 수집 대상 소스 설정 (URL, 레벨, 활성 여부) |
| `raw_content.py` | `RawEntry` | 수집기가 반환하는 원시 항목 |
| `raw_content.py` | `RawFeedMeta` | 피드 메타 정보 (제목, 수집 시각 등) |
| `normalized_content.py` | `NormalizedContent` | Backend로 전송하는 최종 정규화 항목 (DP-292: author/thumbnail/tags/is_original_visible 반영) |
| `summary.py` | `SummaryRequest` | AI 요약 요청 스키마 (content_id, level, text, thumbnail_url) |
| `summary.py` | `SectionSummary` | 소제목별 요약 항목 (heading + content) |
| `summary.py` | `SummaryResponse` | AI 요약 출력 스키마 (LLM 응답 계약) |
| `refine.py` | `RefineRequest` | AI 질문 개선 요청 스키마 (title, content, level, content_id?) (DP-231) |
| `refine.py` | `RefineResponse` | AI 질문 개선 출력 스키마 (LLM 응답 계약) (DP-231) |
| `answer.py` | `AnswerRequest` | AI 1차 답변 요청 스키마 (refined/original 질문 + content_id + question_id) (DP-234) |
| `answer.py` | `RelatedContent` | 참고 기술 블로그 항목 (content_id + one_line_summary) (DP-234) |
| `answer.py` | `AnswerResponse` | AI 1차 답변 출력 스키마 (answer_content, key_points, related_contents 등) (DP-234) |

---

## 스키마 설계 원칙

- 모든 스키마는 Pydantic `BaseModel`을 상속한다.
- 필드는 타입 힌트 필수. `Optional` 필드는 명시적으로 `= None` 처리.
- `RawEntry` → `NormalizedContent` 변환은 `NormalizeService`가 담당하며, 스키마 자체에 로직을 두지 않는다.
- 스키마 변경 시 관련 테스트(`test_normalize_service.py` 등)도 함께 업데이트한다.

---

## 향후 추가 예정

| 파일 | 클래스 | 역할 |
|------|--------|------|
| `report.py` | `ReportResponse` | 주간 리포트 출력 스키마 |

AI 출력 스키마는 반드시 먼저 정의하고 구현한다. 스키마 없는 AI 출력은 허용하지 않는다.
