"""소스 별 표본 비율을 강제한 train 서브셋 생성.

학습 시간을 줄이면서도 소수 소스(예: synthetic [PROJ_N])가 충분히 학습되도록
소스별 표본 수를 지정해 만든다.

예:
    python scripts/stratified_sample.py \
        --in data/processed/train.jsonl \
        --out data/processed/train_balanced.jsonl \
        --take klue=3000 synthetic=all
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_jsonl  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_path", type=Path, required=True)
    parser.add_argument("--out", dest="out_path", type=Path, required=True)
    parser.add_argument(
        "--take",
        nargs="+",
        required=True,
        help='source=N 또는 source=all 형식. 예: klue=3000 synthetic=all',
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rules: dict[str, int | str] = {}
    for kv in args.take:
        k, _, v = kv.partition("=")
        rules[k] = "all" if v == "all" else int(v)

    by_source: dict[str, list] = defaultdict(list)
    for r in read_jsonl(args.in_path):
        by_source[r.get("source", "?")].append(r)

    rng = random.Random(args.seed)
    selected = []
    for src, items in by_source.items():
        rule = rules.get(src)
        if rule is None:
            continue
        if rule == "all" or rule >= len(items):
            picked = items
        else:
            picked = rng.sample(items, rule)
        selected.extend(picked)
        print(f"  {src}: {len(items)} 중 {len(picked)} 선택")

    rng.shuffle(selected)
    args.out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_path, "w", encoding="utf-8") as f:
        for r in selected:
            f.write(json.dumps(r, ensure_ascii=False))
            f.write("\n")
    print(f"총 {len(selected)} 문장 → {args.out_path}")


if __name__ == "__main__":
    main()
