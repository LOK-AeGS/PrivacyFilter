"""엔티티 치환 데이터 증강.

방법:
  1. train.jsonl 에서 라벨별 엔티티 surface form (토큰 리스트) 수집
  2. 각 학습 문장에 대해, 엔티티를 같은 라벨의 다른 surface 로 확률 P 로 치환
  3. K 개 증강본 생성 후 jsonl 로 저장

목적:
  ORG/LOCATION 의 surface 변이를 늘려서 generalization 향상.
  같은 문맥에 다양한 entity 표면형을 보여 줌.

실행:
    python scripts/augment_entity.py \
        --in data/processed/train.jsonl \
        --out data/processed/train_augmented.jsonl \
        --k 2 --p 0.7 --include-original
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

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
        else:  # I and same label
            cur = (cur[0], i + 1, lbl) if cur else (i, i + 1, lbl)
    if cur:
        spans.append(cur)
    return spans


def build_pool(records: List[dict], min_freq: int = 1) -> Dict[str, List[List[str]]]:
    """라벨별 surface form (토큰 리스트) 풀 + 빈도 가중치."""
    raw: Dict[str, List[Tuple[str, ...]]] = defaultdict(list)
    for r in records:
        spans = bio_to_spans(r["tags"])
        for s, e, lbl in spans:
            surface = tuple(r["tokens"][s:e])
            raw[lbl].append(surface)
    # 빈도 기준 필터 + 리스트 변환
    pool: Dict[str, List[List[str]]] = {}
    for lbl, items in raw.items():
        from collections import Counter
        cnt = Counter(items)
        kept = [list(s) for s, n in cnt.items() if n >= min_freq]
        pool[lbl] = kept
    return pool


def augment_one(record: dict, pool: Dict[str, List[List[str]]], p: float, rng: random.Random) -> dict:
    tokens = record["tokens"]
    tags = record["tags"]
    spans = bio_to_spans(tags)
    if not spans:
        return dict(record)  # 변경 없음

    new_tokens: List[str] = []
    new_tags: List[str] = []
    cursor = 0
    for s, e, lbl in spans:
        # 엔티티 앞 'O' 구간 복사
        new_tokens.extend(tokens[cursor:s])
        new_tags.extend(tags[cursor:s])
        # 치환 결정
        if rng.random() < p and pool.get(lbl):
            replacement = rng.choice(pool[lbl])
            new_tokens.extend(replacement)
            new_tags.append(f"B-{lbl}")
            new_tags.extend([f"I-{lbl}"] * (len(replacement) - 1))
        else:
            new_tokens.extend(tokens[s:e])
            new_tags.extend(tags[s:e])
        cursor = e
    new_tokens.extend(tokens[cursor:])
    new_tags.extend(tags[cursor:])

    return {
        "tokens": new_tokens,
        "tags": new_tags,
        "source": record.get("source", "?") + "_aug",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_path", type=Path, required=True)
    parser.add_argument("--out", dest="out_path", type=Path, required=True)
    parser.add_argument("--k", type=int, default=2, help="문장당 증강본 개수")
    parser.add_argument("--p", type=float, default=0.7, help="엔티티별 치환 확률")
    parser.add_argument("--min-freq", type=int, default=1, help="풀에 포함할 최소 빈도")
    parser.add_argument(
        "--include-original",
        action="store_true",
        help="원본 문장도 결과에 포함",
    )
    parser.add_argument(
        "--only-labels",
        nargs="+",
        default=None,
        help='특정 라벨만 치환 (예: ORG LOCATION)',
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    records = list(read_jsonl(args.in_path))
    pool = build_pool(records, min_freq=args.min_freq)
    print("라벨별 surface form 수:")
    for lbl, items in pool.items():
        print(f"  {lbl}: {len(items)}")

    if args.only_labels:
        # 다른 라벨은 풀에서 제외 → 그 라벨은 치환 안 됨
        keep = set(args.only_labels)
        pool = {k: v for k, v in pool.items() if k in keep}
        print(f"치환 대상 라벨 제한: {keep}")

    args.out_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with open(args.out_path, "w", encoding="utf-8") as f:
        for r in records:
            if args.include_original:
                f.write(json.dumps(r, ensure_ascii=False))
                f.write("\n")
                total += 1
            for _ in range(args.k):
                aug = augment_one(r, pool, args.p, rng)
                f.write(json.dumps(aug, ensure_ascii=False))
                f.write("\n")
                total += 1

    print(f"총 {total} 문장 → {args.out_path}")


if __name__ == "__main__":
    main()
