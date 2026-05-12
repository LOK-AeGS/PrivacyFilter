"""라벨 필터 — 라벨 노이즈 정제 / 사후 처리.

이 모듈은 두 종류 함수를 제공:
  1. 개별 record 단위 필터 (FILTERS 에 등록 가능)
  2. 배치(전체 dataset) 단위 정제 (build_dataset.py 에서 호출)
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple


def bio_to_spans(tags: List[str]) -> List[Tuple[int, int, str]]:
    spans: List[Tuple[int, int, str]] = []
    cur: Tuple[int, int, str] | None = None
    for i, t in enumerate(tags):
        if t == "O":
            if cur:
                spans.append(cur)
                cur = None
            continue
        pos, _, lbl = t.partition("-")
        if pos == "B" or (cur and cur[2] != lbl):
            if cur:
                spans.append(cur)
            cur = (i, i + 1, lbl)
        else:
            cur = (cur[0], i + 1, lbl) if cur else (i, i + 1, lbl)
    if cur:
        spans.append(cur)
    return spans


# ----------------------------------------------------------------------------
# 개별 record 필터
# ----------------------------------------------------------------------------
def drop_record_if_any_entity_dropped(record: dict, threshold: int = 0) -> Optional[dict]:
    """필터 체인 후 entity 수가 threshold 이하면 record 전체 drop.

    threshold=0: entity 가 모두 사라진 record drop
    threshold=1: entity 가 1개 이하면 drop (학습 신호 약한 문장 제거)
    """
    n = sum(1 for t in record["tags"] if t.startswith("B-"))
    if n <= threshold:
        return None
    return record


# ----------------------------------------------------------------------------
# 배치(전체 dataset) 단위 정제
# ----------------------------------------------------------------------------
def clean_label_noise(
    records: List[dict],
    minority_threshold: float = 0.15,
    min_count: int = 5,
) -> Tuple[List[dict], dict]:
    """surface→label 일관화. minority<threshold AND count>=min_count 인 surface 를 majority 라벨로 통일.

    Returns:
        (cleaned_records, stats)
    """
    surface_labels: Dict[str, Counter] = defaultdict(Counter)
    for r in records:
        for s, e, lbl in bio_to_spans(r["tags"]):
            surface_labels[" ".join(r["tokens"][s:e])][lbl] += 1

    cleanup: Dict[str, str] = {}
    for surf, c in surface_labels.items():
        total = sum(c.values())
        if total < min_count:
            continue
        majority_lbl, majority_n = c.most_common(1)[0]
        minority_n = total - majority_n
        if minority_n >= 1 and minority_n / total < minority_threshold:
            cleanup[surf] = majority_lbl

    cleaned = []
    n_changed_records = 0
    n_changed_entities = 0
    for r in records:
        tokens = r["tokens"]
        tags = list(r["tags"])
        modified = False
        for s, e, lbl in bio_to_spans(tags):
            surf = " ".join(tokens[s:e])
            if surf in cleanup and cleanup[surf] != lbl:
                new_lbl = cleanup[surf]
                for i in range(s, e):
                    tags[i] = f"{'B' if i == s else 'I'}-{new_lbl}"
                n_changed_entities += 1
                modified = True
        if modified:
            n_changed_records += 1
        cleaned.append({**r, "tags": tags})

    stats = {
        "total_unique_surfaces": len(surface_labels),
        "cleanup_targets": len(cleanup),
        "changed_records": n_changed_records,
        "changed_entities": n_changed_entities,
    }
    return cleaned, stats
