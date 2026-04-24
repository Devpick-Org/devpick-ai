"""태그 동의어 정규화 (DP-380)."""

from __future__ import annotations

from rapidfuzz import fuzz


class TagNormalizer:
    """rapidfuzz ratio 기반 동의어 그룹핑으로 태그를 정규화한다.

    첫 등장 태그가 canonical이 된다.
    이후 유사도 >= threshold인 태그는 해당 canonical로 매핑된다.
    예: ["react", "reactjs", "React.js"] → ["react", "react", "react"]
    """

    def __init__(self, threshold: int = 85) -> None:
        self._threshold = threshold

    def normalize(self, tags: list[str]) -> list[str]:
        """동의어를 통합하여 정규화된 태그 리스트를 반환한다 (순서 유지)."""
        canonicals: list[str] = []
        mapping: dict[str, str] = {}

        for tag in tags:
            key = tag.lower().strip()
            if key in mapping:
                continue
            matched = next(
                (c for c in canonicals if fuzz.ratio(key, c) >= self._threshold),
                None,
            )
            if matched:
                mapping[key] = matched
            else:
                canonicals.append(key)
                mapping[key] = key

        return [mapping.get(t.lower().strip(), t.lower().strip()) for t in tags]
