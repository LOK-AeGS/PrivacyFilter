"""변환된 모든 JSONL 을 합쳐서 train/dev/test 로 분할.

- 입력: data/processed/*.jsonl (klue_*, naver_*, nikl, proj_synthetic)
- 출력:
    data/processed/train.jsonl
    data/processed/dev.jsonl
    data/processed/test.jsonl
    data/processed/label_list.txt   # BIO 라벨 마스터 리스트

기본 분할 비율: 8 : 1 : 1
이미 train/dev 가 명시된 파일(klue_train, klue_dev, naver_train)은 우선 그 분할을 따른다.
나머지(nikl, proj_synthetic, aihub) 는 비율대로 무작위 분할한다.

aihub 는 정규식 평가용이므로 기본적으로 test 에만 배치한다 (--aihub-to test 옵션).
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Dict, List

from common import REPO_ROOT, TARGET_LABELS, read_jsonl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in-dir", type=Path, default=REPO_ROOT / "data" / "processed")
    parser.add_argument("--ratios", type=str, default="0.8,0.1,0.1", help="train,dev,test")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--aihub-to",
        choices=("train", "dev", "test"),
        default="test",
        help="AI-Hub 데이터 배치 split (정규식 평가용이라 기본 test)",
    )
    args = parser.parse_args()

    rng = random.Random(args.seed)
    ratios = tuple(float(x) for x in args.ratios.split(","))
    assert len(ratios) == 3 and abs(sum(ratios) - 1.0) < 1e-6, "ratios must sum to 1.0"
    train_r, dev_r, _ = ratios

    bins: Dict[str, List[dict]] = {"train": [], "dev": [], "test": []}

    # 1) 사전 분할된 파일들
    preassigned = {
        "klue_train.jsonl": "train",
        "klue_dev.jsonl": "dev",
        "naver_train.jsonl": "train",
    }
    for fname, split in preassigned.items():
        fp = args.in_dir / fname
        if fp.exists():
            for r in read_jsonl(fp):
                bins[split].append(r)
            print(f"[fixed] {fname} → {split}")

    # 2) 비율 분할 대상
    random_split_files = ["nikl.jsonl", "proj_synthetic.jsonl"]
    for fname in random_split_files:
        fp = args.in_dir / fname
        if not fp.exists():
            print(f"[skip] {fname} (없음)")
            continue
        records = list(read_jsonl(fp))
        rng.shuffle(records)
        n = len(records)
        n_train = int(n * train_r)
        n_dev = int(n * dev_r)
        bins["train"].extend(records[:n_train])
        bins["dev"].extend(records[n_train : n_train + n_dev])
        bins["test"].extend(records[n_train + n_dev :])
        print(f"[split] {fname} → train {n_train} / dev {n_dev} / test {n - n_train - n_dev}")

    # 3) AI-Hub 배치
    aihub_fp = args.in_dir / "aihub.jsonl"
    if aihub_fp.exists():
        records = list(read_jsonl(aihub_fp))
        bins[args.aihub_to].extend(records)
        print(f"[fixed] aihub.jsonl → {args.aihub_to} ({len(records)} 문장)")

    # 4) 각 split shuffle 후 write
    for split, records in bins.items():
        rng.shuffle(records)
        out = args.in_dir / f"{split}.jsonl"
        with open(out, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False))
                f.write("\n")
        print(f"  {split}: {len(records)} 문장 → {out}")

    # 5) 라벨 마스터 리스트
    labels = ["O"]
    for lbl in TARGET_LABELS:
        labels.append(f"B-{lbl}")
        labels.append(f"I-{lbl}")
    label_out = args.in_dir / "label_list.txt"
    with open(label_out, "w", encoding="utf-8") as f:
        for lbl in labels:
            f.write(lbl + "\n")
    print(f"라벨 리스트({len(labels)}종) → {label_out}")


if __name__ == "__main__":
    main()
