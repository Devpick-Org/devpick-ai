# CLAUDE.md — app/configs/

수집 대상 소스 목록을 관리한다.

---

## 현재 파일

| 파일 | 내용 |
|------|------|
| `sources.py` | `get_default_sources()`, `get_crawl_sources()` 함수 및 소스 목록 정의 |

---

## 소스 목록 구조

```python
SourceConfig(
    name: str,           # 소스 식별자 (SentIdStore 키로도 사용)
    url: str,            # RSS/Atom 피드 URL
    content_level: int,  # 1=크롤링 보강, 2=RSS만
    active: bool,        # False면 수집 건너뜀
)
```

- `get_default_sources()` → `content_level=2` 소스 목록 (RSS/Atom 전용)
- `get_crawl_sources()` → `content_level=1` 소스 목록 (RSS + HTML 크롤링)

---

## 소스 추가 원칙

- 소스를 추가할 때 `active=False`로 시작해 동작을 확인한 후 `active=True`로 전환한다.
- `name`은 파일시스템 경로에 사용되므로 영문/숫자/하이픈만 사용한다.
- URL은 코드에 직접 적는다. 환경변수로 관리하지 않는다 (공개 피드이므로 시크릿 아님).
