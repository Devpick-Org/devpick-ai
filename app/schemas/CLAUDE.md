# CLAUDE.md — app/schemas/

Pydantic 기반 데이터 계약. 수집부터 AI 처리까지 모든 데이터 형태를 정의한다.

---

## 현재 스키마

| 파일 | 클래스 | 역할 |
|------|--------|------|
| `source.py` | `SourceConfig` | 수집 대상 소스 설정 |
| `raw_content.py` | `RawEntry` | 수집기가 반환하는 원시 항목 |
| `raw_content.py` | `RawFeedMeta` | 피드 메타 정보 |
| `normalized_content.py` | `NormalizedContent` | PostgreSQL 저장 + AI 처리 입력 스키마. `likes`(Velog), `score`(SO) 분리. `tags` 필드 없음 |
| `summary.py` | `SectionSummary` | 소제목별 요약 항목 (heading + content) |
| `summary.py` | `SummaryResponse` | 단일 레벨 AI 요약 출력 스키마 |
| `summary.py` | `CommonSummary` | 레벨 무관 공통 요약 필드 (DP-300) |
| `summary.py` | `LevelSummary` | 레벨별 요약 필드 (DP-300) |
| `summary.py` | `AllLevelsSummaryRequest` | 4레벨 동시 요약 요청 스키마 (DP-300). `title` 필드 추가 (DP-328) |
| `summary.py` | `AllLevelsSummaryResponse` | 4레벨 동시 요약 응답 스키마 (DP-300). `translated_title` 필드 추가 (DP-328) |
| `quiz.py` | `QuizQuestion` | 퀴즈 문제 한 개 (type/question/options/answer/explanation) |
| `quiz.py` | `LevelQuiz` | 레벨별 퀴즈 3문제 컨테이너 |
| `quiz.py` | `QuizRequest` | POST /internal/quiz 요청 스키마 (content_id + text + user_id?) |
| `quiz.py` | `AllLevelsQuizResponse` | 4레벨 동시 퀴즈 응답 스키마 (beginner/junior/mid/senior) |
| `refine.py` | `RefineRequest` | AI 질문 개선 요청 스키마 (DP-231) |
| `refine.py` | `RefineResponse` | AI 질문 개선 출력 스키마 (DP-231) |
| `answer.py` | `AnswerRequest` | AI 1차 답변 요청 스키마 (DP-234) |
| `answer.py` | `RelatedContent` | 참고 기술 블로그 항목 (DP-234) |
| `answer.py` | `AnswerResponse` | AI 1차 답변 출력 스키마 (DP-234) |
| `similar_question.py` | `SimilarQuestionRequest` | 유사 질문 검색 요청 스키마 (DP-235) |
| `similar_question.py` | `SimilarQuestion` | 유사 질문 개별 항목 (DP-235) |
| `similar_question.py` | `SimilarQuestionResponse` | 유사 질문 검색 결과 (DP-235) |
| `event.py` | `EventType` | AI 처리 이벤트 유형 enum (DP-252) |
| `insight.py` | `ActivityData` | 주간 활동 데이터 |
| `insight.py` | `InsightRequest` | 주간 인사이트 요청 스키마 (DP-259) |
| `insight.py` | `InsightResponse` | 주간 인사이트 응답 스키마 (DP-259) |
| `trend.py` | `TrendingTag` | 트렌딩 태그 항목 (keyword, count, rank, rank_change, state) (DP-378보강, DP-380) |
| `trend.py` | `TrendResponse` | 트렌드 배치 결과 응답 스키마 — `trending_tags` 필드 포함 (DP-378보강) |

---

## EventType 목록 (event.py)

| 값 | 트리거 |
|----|--------|
| `SUMMARY_GENERATED` | POST /internal/summary (legacy) |
| `ALL_LEVELS_SUMMARY_GENERATED` | POST /internal/summaries |
| `QUESTION_REFINED` | POST /internal/refine |
| `ANSWER_GENERATED` | POST /internal/answer |
| `SIMILAR_QUESTIONS_SEARCHED` | POST /internal/similar-questions |
| `INSIGHT_GENERATED` | POST /internal/report |
| `QUIZ_GENERATED` | POST /internal/quiz (fallback) |

---

## 스키마 설계 원칙

- 모든 스키마는 Pydantic `BaseModel`을 상속한다.
- 필드는 타입 힌트 필수. Optional 필드는 명시적으로 `= None` 처리.
- AI 출력 스키마는 구현 전에 먼저 정의한다. 스키마 없는 AI 출력은 허용하지 않는다.
- `RawEntry` → `NormalizedContent` 변환은 `NormalizeService`가 담당. 스키마에 로직 없음.
