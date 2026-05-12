"""라벨 노이즈 정제.

전략 (보수적):
  - train 에서 surface → labels Counter 집계
  - minority_count / total < threshold AND total >= min_count 인 surface 만 majority 라벨로 통일
  - 합법적 문맥 의존(예: '한국은' 15:14 처럼 거의 50:50) 은 보존
  - dev/test 는 절대 수정하지 않음 (평가 정직성)

기본값: minority_rate < 0.15, min_count >= 5
예: '한국' 170 LOC, 5 ORG (rate 2.8%) → 5 ORG 를 LOC 로 통일
    '한국은' 15 ORG, 14 LOC (rate 48%) → 보존
    '북한의' 47 ORG, 25 LOC (rate 35%) → 보존

실행:
    python scripts/clean_label_noise.py \
        --in data/processed/train.jsonl \
        --out data/processed/train_cleaned.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_jsonl  # noqa: E402


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_path", type=Path, required=True)
    parser.add_argument("--out", dest="out_path", type=Path, required=True)
    parser.add_argument("--minority-threshold", type=float, default=0.15,
                        help="minority/total 이 이 값 미만일 때 cleanup")
    parser.add_argument("--min-count", type=int, default=5,
                        help="surface 등장 횟수 합 (이 값 이상에만 적용)")
    args = parser.parse_args()

    records = list(read_jsonl(args.in_path))
    surface_labels: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        for s, e, lbl in bio_to_spans(r["tags"]):
            surface_labels[" ".join(r["tokens"][s:e])][lbl] += 1

    # cleanup 대상 surface → majority label 매핑
    cleanup: dict[str, str] = {}
    for surf, c in surface_labels.items():
        total = sum(c.values())
        if total < args.min_count:
            continue
        majority_lbl, majority_n = c.most_common(1)[0]
        minority_n = total - majority_n
        minority_rate = minority_n / total
        if minority_rate < args.minority_threshold and minority_n >= 1:
            cleanup[surf] = majority_lbl

    print(f"전체 unique surface: {len(surface_labels):,}")
    print(f"cleanup 대상: {len(cleanup):,}")
    print(f"\n예시 (상위 15):")
    examples = []
    for surf, maj in cleanup.items():
        c = surface_labels[surf]
        examples.append((sum(c.values()), surf, dict(c), maj))
    examples.sort(key=lambda x: -x[0])
    for total, surf, c, maj in examples[:15]:
        print(f"  '{surf}' total={total} {c} → {maj}")

    # 적용
    changed_records = 0
    changed_entities = 0
    out_records = []
    for r in records:
        tokens = r["tokens"]
        tags = list(r["tags"])
        modified = False
        spans = bio_to_spans(tags)
        for s, e, lbl in spans:
            surf = " ".join(tokens[s:e])
            if surf in cleanup and cleanup[surf] != lbl:
                # 다시 라벨 적용
                new_lbl = cleanup[surf]
                for i in range(s, e):
                    tags[i] = f"{'B' if i == s else 'I'}-{new_lbl}"
                changed_entities += 1
                modified = True
        if modified:
            changed_records += 1
        out_records.append({"tokens": tokens, "tags": tags, "source": r.get("source", "?")})

    args.out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_path, "w", encoding="utf-8") as f:
        for r in out_records:
            f.write(json.dumps(r, ensure_ascii=False))
            f.write("\n")

    print(f"\n수정된 문장: {changed_records:,} / 수정된 엔티티: {changed_entities:,}")
    print(f"출력: {args.out_path}")


if __name__ == "__main__":
    main()
