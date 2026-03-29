# CLAUDE.md — app/stores/

저장소 레이어. cross-run 중복 전송 방지를 담당한다.

---

## 현재 저장소

| 파일 | 클래스 | 역할 |
|------|--------|------|
| `sent_id_store.py` | `SentIdStore` | 소스별 처리 완료 ID 파일 저장 (cross-run dedup) |

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
- `run_collect_and_save.py`와 `run_collect_and_push.py`가 같은 디렉토리 공유

### dedup 흐름

```
SentIdStore.load(source.name) → sent_ids
new_entries = [entry for entry in entries if entry.entry_external_id not in sent_ids]
# normalize → save/push
SentIdStore.add(source.name, processed_ids)
```

새 항목이 없으면 처리 없이 skip한다.

---

## 주의사항

- `data/raw/` 디렉토리는 gitignore 대상이다. 로컬에만 존재한다.
- `SentIdStore`는 파일 기반이므로 멀티 프로세스 환경에서는 race condition이 발생할 수 있다.
  현재는 단일 프로세스 스케줄러 환경을 가정한다.
