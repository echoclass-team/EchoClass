"""学科迷思库加载与匹配。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from schemas.misconception import Misconception


_SUBJECT_ALIASES = {
    "math": "数学",
    "chinese": "语文",
    "english": "英语",
    "physics": "物理",
    "chemistry": "化学",
    "biology": "生物",
    "politics": "政治",
    "history": "历史",
    "geography": "地理",
}


def _default_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "data" / "misconceptions"


@lru_cache(maxsize=4)
def _load_misconceptions_cached(misconceptions_dir: str) -> tuple[Misconception, ...]:
    items: list[Misconception] = []
    for fp in sorted(Path(misconceptions_dir).glob("*.json")):
        if fp.name.startswith("_"):
            continue
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        items.extend(Misconception(**item) for item in data)
    return tuple(sorted(items, key=lambda item: item.id))


def load_misconceptions(misconceptions_dir: str | Path | None = None) -> list[Misconception]:
    """读取 data/misconceptions/*.json，跳过 schema 文件并稳定排序。"""
    directory = Path(misconceptions_dir) if misconceptions_dir is not None else _default_dir()
    return list(_load_misconceptions_cached(str(directory)))


def match_misconceptions(
    subject: str,
    stage_id: str,
    key_points: list[str],
    topic: str = "",
    difficult_points: list[str] | None = None,
    limit: int = 5,
    misconceptions: list[Misconception] | None = None,
) -> list[Misconception]:
    """按学科、学段、主题/重点/难点匹配最相关的迷思。"""
    pool = misconceptions if misconceptions is not None else load_misconceptions()
    subject_norm = _normalize_subject(subject)
    key_queries = [q for q in key_points if q]
    secondary_queries = [q for q in [topic, *(difficult_points or [])] if q]

    scored: list[tuple[int, str, Misconception]] = []
    for item in pool:
        if not _subject_matches(subject_norm, item.subject):
            continue
        if stage_id and stage_id not in item.stage:
            continue
        key_score = _score(item, key_queries)
        if key_queries and key_score <= 0:
            continue
        score = key_score * 2 + _score(item, secondary_queries)
        if score > 0:
            scored.append((score, item.id, item))

    scored.sort(key=lambda row: (-row[0], row[1]))
    return [item for _, _, item in scored[:limit]]


def _subject_matches(subject: str, item_subject: str) -> bool:
    item_subject_norm = _normalize_subject(item_subject)
    return (
        subject == item_subject_norm
        or subject in item_subject_norm
        or item_subject_norm in subject
    )


def _normalize_subject(subject: str) -> str:
    normalized = subject.strip().lower()
    return _SUBJECT_ALIASES.get(normalized, subject.strip())


def _score(item: Misconception, queries: list[str]) -> int:
    haystacks = [item.topic, item.name, item.description, item.typical_error]
    score = 0
    for query in queries:
        for haystack in haystacks:
            if query in haystack or haystack in query:
                score += 10
            else:
                score += min(_bigram_overlap(query, haystack), 4)
    return score


def _bigram_overlap(left: str, right: str) -> int:
    def bigrams(text: str) -> set[str]:
        chars = [c for c in text if "\u4e00" <= c <= "\u9fff"]
        return {"".join(chars[i : i + 2]) for i in range(len(chars) - 1)}

    return len(bigrams(left) & bigrams(right))
