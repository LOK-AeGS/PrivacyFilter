"""데이터셋 통계.

- 문장 수, 어절 수
- 라벨 분포 (BIO 단위 + 엔티티 단위)
- source 별 분포

실행:
    python verification/stats.py data/processed/train.jsonl
    python verification/stats.py data/processed/*.jsonl
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import read_jsonl  # noqa: E402


def count_entities(tags: Iterable[str]) -> Counter:
    """B-X 의 개수 = 엔티티 개수."""
    cnt = Counter()
    for t in tags:
        if t.startswith("B-"):
            cnt[t[2:]] += 1
    return cnt


def summarize(path: Path) -> None:
    bio_cnt = Counter()
    ent_cnt = Counter()
    src_cnt = Counter()
    n_sent = 0
    n_word = 0
    n_word_o = 0
    for r in read_jsonl(path):
        n_sent += 1
        n_word += len(r["tokens"])
        n_word_o += sum(1 for t in r["tags"] if t == "O")
        for t in r["tags"]:
            bio_cnt[t] += 1
        ent_cnt.update(count_entities(r["tags"]))
        src_cnt[r.get("source", "?")] += 1

    print(f"\n=== {path.name} ===")
    print(f"문장: {n_sent}")
    print(f"어절: {n_word} (O 비율 {n_word_o / n_word * 100:.1f}%)" if n_word else "어절: 0")
    print(f"source 분포: {dict(src_cnt)}")
    print("엔티티 (B- 기준):")
    for k in sorted(ent_cnt):
        print(f"  {k}: {ent_cnt[k]}")
    print("BIO 태그 (상위 15):")
    for k, v in bio_cnt.most_common(15):
        print(f"  {k}: {v}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    for p in args.paths:
        if not p.exists():
            print(f"[skip] {p} 없음")
            continue
        summarize(p)


if __name__ == "__main__":
    main()
