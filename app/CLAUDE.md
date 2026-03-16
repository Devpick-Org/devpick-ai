# CLAUDE.md — app/

이 디렉토리는 devpick-ai의 핵심 애플리케이션 코드다.

---

## 현재 구조

```text
app/
├── collectors/     # 수집기 — RSS, RSS+크롤링
├── configs/        # 수집 대상 소스 목록
├── schemas/        # Pydantic 스키마 (RawEntry, NormalizedContent, SourceConfig)
├── services/       # 비즈니스 로직 (IngestService, NormalizeService, PushService)
├── stores/         # raw JSONL 저장 + SentIdStore (cross-run dedup)
├── utils/          # XML/HTML 파싱 헬퍼
└── main.py         # FastAPI 앱 서브모듈 진입점 (현재 사용 최소)
```

---

## 수집 파이프라인 전체 흐름

```
SourceConfig (app/configs/sources.py)
    ↓
Collector.collect() → (RawFeedMeta, list[RawEntry], raw_xml)
    ↓
FileRawStore.save_feed() + save_entries() → data/raw/ JSONL
    ↓
NormalizeService.normalize_entry() → list[NormalizedContent]
    ↓
SentIdStore.load() → 이미 전송된 ID 필터링
    ↓
PushService.push(new_items) → POST /internal/contents → Backend
    ↓
SentIdStore.add() → 전송 완료 ID 기록
```

전체 파이프라인 실행 진입점: `scripts/run_collect_and_push.py`

---

## 향후 추가될 구조

AI 기능(요약/질문/리포트)이 추가되면 아래 폴더가 생긴다.

```text
app/
├── api/
│   └── v1/         # FastAPI 라우터
├── core/
│   ├── config.py
│   ├── prompts/    # 프롬프트 템플릿
│   └── logging.py
└── repositories/   # DB 접근 레이어
```

---

## 폴더별 CLAUDE.md 링크

- [collectors/CLAUDE.md](collectors/CLAUDE.md)
- [schemas/CLAUDE.md](schemas/CLAUDE.md)
- [stores/CLAUDE.md](stores/CLAUDE.md)
- [configs/CLAUDE.md](configs/CLAUDE.md)
- [utils/CLAUDE.md](utils/CLAUDE.md)
- [services/CLAUDE.md](services/CLAUDE.md)
