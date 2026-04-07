# CLAUDE.md — app/stores/

저장소 레이어. cross-run 중복 전송 방지를 담당한다.

---

## 현재 저장소

| 파일 | 클래스 | 역할 |
|------|--------|------|
| `sent_id_store.py` | `SentIdStore` | 소스별 처리 완료 ID 파일 저장 (cross-run dedup) |
| `backfill_cursor.py` | `BackfillCursor` | 소스별 백필 진행 상태 JSON 파일 관리 (DP-199) |

---

## SentIdStore

```python
SentIdStore(base_dir: str = "data/raw/sent_ids")
load(source_name: str) -> set[str]   # 이미 처리된 ID 집합 로드
add(source_name: str, ids: set[str]) -> None  # 처리 완료 ID 추가
```

- 소스별 텍스트 파일: `data/raw/sent_ids/{source_name}.txt`
- 파일 없으면 빈 집합 반환 (첫 실행 안전)
- `add()`는 기존 ID와 병합 후 정렬 저장 (idempotent)
- `run_collect_and_save.py`와 `run_backfill_batch.py`가 같은 디렉토리 공유

### dedup 흐름

```
SentIdStore.load(source.name) → sent_ids
new_entries = [entry for entry in entries if entry.entry_external_id not in sent_ids]
# normalize → save/push
SentIdStore.add(source.name, processed_ids)
```

새 항목이 없으면 처리 없이 skip한다.

---

## BackfillCursor (DP-199)

```python
BackfillCursor(base_dir: str = "data/raw/backfill_cursor")
load(source_name: str) -> dict        # 커서 로드 (없으면 빈 dict)
save(source_name: str, cursor: dict)  # 커서 저장
is_done(source_name: str) -> bool     # 백필 완료 여부
reset(source_name: str) -> None       # 커서 삭제 (재시작)
```

- 소스별 JSON 파일: `data/raw/backfill_cursor/{source_name}.json`
- 커서에 `"phase"` 필드로 단계 구분: `"backfill"` | `"incremental"`
- `is_done()`: `phase == "incremental"`이면 항상 `False` → 스케줄러가 계속 실행
- backfill 소진 시 수집기가 자동으로 `phase: "incremental"`으로 전환 (`done: true` 설정 안 함)
- `reset()` 호출 시 처음부터 재수집 (SentIdStore dedup이 중복 방지)

---

## 주의사항

- `data/raw/` 디렉토리는 gitignore 대상이다. 로컬에만 존재한다.
- `SentIdStore`는 파일 기반이므로 멀티 프로세스 환경에서는 race condition이 발생할 수 있다.
  현재는 단일 프로세스 스케줄러 환경을 가정한다.
