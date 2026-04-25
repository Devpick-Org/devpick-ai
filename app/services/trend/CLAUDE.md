# CLAUDE.md — app/services/trend/

트렌드 분석 파이프라인 서비스 모음. 태그 정규화 → 빈도 집계 → TF-IDF → 랭킹 → LLM 서사 요약 → 스냅샷 저장까지의 전 흐름을 담당한다.

---

## 파일 구성

| 파일 | 클래스/함수 | 역할 |
|------|------------|------|
| `normalize.py` | `TagNormalizer` | rapidfuzz ratio 기반 태그 동의어 정규화 (DP-380) |
| `frequency.py` | `FrequencyAnalyzer`, `TagFrequency` | cur/prev 태그 빈도 집계 + 증감 상태 판정 (DP-380) |
| `tokenizer.py` | `KoreanTokenizer` | kiwipiepy NNG/NNP/SL POS 필터 기반 한국어 토크나이저 (DP-381) |
| `tfidf.py` | `TfidfAnalyzer` | scikit-learn TfidfVectorizer 기반 상위 키워드 추출 (DP-381) |
| `ranking.py` | `TrendRanker`, `RankedTag` | 기간 조회수 Top 5 콘텐츠 + 복합 점수 Top 10 태그 선정 (DP-383) |
| `data_loader.py` | `TrendDataLoader`, `TrendRawData` | cur/prev 기간 4개 쿼리 병렬 로드 (DP-379, DP-386) |
| `top_posts_summary.py` | `TopPostsSummaryGenerator` | Top 5 콘텐츠 주제 흐름 LLM 서사 요약 (DP-404) |
| `collection_summary.py` | `CollectionSummaryGenerator`, `TrendSignals` | 수집 동향 LLM 서사 요약 (DP-384) |
| `orchestrator.py` | `TrendOrchestrator`, `compute_period` | 배치 오케스트레이터 — 위 컴포넌트를 순서대로 조합 (DP-386) |
| `cache_eviction.py` | `CacheEvictionClient` | 배치 완료 후 BE Redis 캐시 무효화 요청 — best-effort (DP-387) |
| `external_signals.py` | `ExternalSignalFetcher`, `GitHubTrendingFetcher`, `HackerNewsFetcher`, `DevToFetcher` | GitHub Trending·HN Algolia·dev.to 외부 시그널 수집 + 가중치 블렌딩 (DP-382) |

---

## 트렌드 배치 전체 흐름

```
compute_period(unit) → (period_start, period_end)
    ↓
TrendDataLoader.load(start, end)
    ├─ find_by_published_range(start, end)       → cur_contents (source_name, thumbnail_url 포함)
    ├─ find_by_published_range(prev_start, start) → prev_contents
    ├─ find_view_counts_by_period(start, end)     → cur_view_counts
    └─ find_view_counts_by_period(prev_start, start) → prev_view_counts
    ↓
TagNormalizer.normalize(cur_tags, prev_tags)
    ↓
FrequencyAnalyzer.analyze(cur_tags, prev_tags) → list[TagFrequency]
    ↓
KoreanTokenizer.tokenize(titles) → TfidfAnalyzer.extract() → tfidf_keywords[:15]
    ↓
ExternalSignalFetcher.fetch(unit) → external_signals  # best-effort, 실패 시 {} (DP-382)
    ↓
TrendRanker.rank_contents(cur_view_counts, cur_contents) → top_contents_raw
TrendRanker.rank_tags(tag_frequencies, summary_meta, external_signals) → cur_ranked
    ↓
TopPostsSummaryGenerator.generate(top_contents_raw, unit, ..., prev_summary) → top_posts_summary
CollectionSummaryGenerator.generate(TrendSignals(...)) → collection_summary
    ↓
TrendingTag 조립 (cur_ranked[:top_n], rank_change 계산) → trending_tags  # top_n: daily=10/weekly=15/monthly=20
    ↓
TrendResponse 조립 (trending_tags 포함) → TrendSnapshotRepository.upsert()
    ↓
CacheEvictionClient.evict(unit, period_start)  # best-effort (DP-387)
```

---

## TagFrequency / TrendSignals 데이터 계약

### TagFrequency (frequency.py)
```python
@dataclass
class TagFrequency:
    keyword: str
    cur_count: int
    prev_count: int
    delta: int
    growth_rate: float | None  # None = state="new"
    state: str  # "new" | "up" | "down" | "same"
```

### TrendSignals (collection_summary.py)
```python
@dataclass
class TrendSignals:
    unit: str                       # "daily" | "weekly" | "monthly"
    period_start: str               # ISO 날짜 문자열
    period_end: str
    cur_content_count: int
    prev_content_count: int = 0
    top_tags: list[TagFrequency] = field(default_factory=list)
    tfidf_keywords: list[str] = field(default_factory=list)
    prev_summary: str | None = None  # 이전 기간 collection_summary
```

---

## LLM 실패 처리 정책

| 서비스 | 실패 시 동작 |
|--------|------------|
| `TopPostsSummaryGenerator` | `AIUpstreamError` / `AITimeoutError` 전파 → 오케스트레이터에서 catch → `top_posts_summary=None` |
| `CollectionSummaryGenerator` | 내부 catch → `None` 반환 (daily 포함) |

두 경우 모두 스냅샷 저장은 계속 진행된다.

---

## compute_period 단위별 로직

| unit | 기준 | period_start | period_end |
|------|------|-------------|------------|
| daily | 어제 자정~오늘 자정 | `today - 1일` | `today` |
| weekly | 이전 주 월~월 | `이번 주 월요일 - 7일` | `이번 주 월요일` |
| monthly | 이전 달 1일~이번 달 1일 | `지난달 1일` | `이번달 1일` |
