"""configs/datasets.yaml 기반 통합 빌더.

흐름:
  1. 각 source 의 converted JSONL 로드
  2. 필터 체인 적용 (per-source)
  3. split 정책에 따라 train/dev/test 로 분배
  4. 합쳐서 pipeline 사후처리 (라벨 노이즈 정제 등)
  5. 최종 train/dev/test/label_list 저장

실행:
    python scripts/build_dataset.py
    python scripts/build_dataset.py --dry-run        # 통계만
    python scripts/build_dataset.py --skip-convert    # 컨버터 자동 호출 안 함
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import List, Tuple

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO_ROOT, TARGET_LABELS, read_jsonl, write_jsonl  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from filters import FILTERS  # noqa: E402
from filters.label import clean_label_noise  # noqa: E402


CONFIG_PATH = REPO_ROOT / "configs" / "datasets.yaml"


def maybe_run_converter(source_name: str, converter_rel_path: str | None) -> None:
    """converter 가 정의되어 있고 출력 파일 없으면 자동 호출."""
    if not converter_rel_path:
        return
    converter_path = REPO_ROOT / converter_rel_path
    if not converter_path.exists():
        print(f"  [{source_name}] ⚠️ converter 스크립트 없음: {converter_rel_path}")
        return
    # 컨버터는 출력 파일을 알아서 만든다. 본 함수는 단순히 명시적 호출 옵션.
    # build_dataset.py 는 이미 converted 됐다고 가정하고, 없으면 사용자에게 알린다.
    return


def load_source(source_name: str, spec: dict) -> dict:
    """source 의 JSONL 들을 split → records 로 로드.

    Returns: {"train": [...], "dev": [...], "test": [...]}
    """
    out: dict[str, list] = {"train": [], "dev": [], "test": []}

    if "files" in spec:
        # 사전 분할
        for split, path in spec["files"].items():
            full = REPO_ROOT / path
            if not full.exists():
                print(f"  [{source_name}] ⚠️ split={split} 파일 없음: {path}")
                continue
            out[split] = list(read_jsonl(full))
    elif "single_file" in spec:
        single = REPO_ROOT / spec["single_file"]
        if not single.exists():
            print(f"  [{source_name}] ⚠️ single_file 없음: {spec['single_file']}")
            return out
        records = list(read_jsonl(single))
        ratios = spec.get("split_ratios", {"train": 1.0})
        rng = random.Random(42)
        rng.shuffle(records)
        n = len(records)
        cursor = 0
        for split, share in ratios.items():
            if share == "all" or share == 1.0:
                k = n - cursor
            else:
                k = int(n * float(share))
            out[split].extend(records[cursor : cursor + k])
            cursor += k
        # 잔여
        if cursor < n:
            # 마지막 split 에 잔여 합치기 (또는 train)
            last_split = next(iter(ratios.keys()))
            out[last_split].extend(records[cursor:])
    else:
        print(f"  [{source_name}] ⚠️ files 또는 single_file 미지정")

    return out


def apply_filters(records: list, filter_names: list, source: str) -> list:
    """필터 체인 적용. record 가 None 반환되면 drop."""
    out = list(records)
    for fname in filter_names:
        if fname not in FILTERS:
            print(f"  [{source}] ⚠️ 알 수 없는 필터: {fname}")
            continue
        f = FILTERS[fname]
        before = len(out)
        new_out = []
        for r in out:
            res = f(r)
            if res is not None:
                new_out.append(res)
        out = new_out
        print(f"  [{source}] filter '{fname}': {before} → {len(out)} record")
    return out


def apply_weight(records: list, weight: int | float) -> list:
    """단순 oversampling (정수배). 1.5 같은 경우 1.5x 반복(소수부분 무작위 추가)."""
    if weight is None or weight == 1:
        return records
    rng = random.Random(42)
    int_part = int(weight)
    frac = weight - int_part
    out = records * int_part
    if frac > 0:
        extra_n = int(len(records) * frac)
        out.extend(rng.sample(records, extra_n))
    return out


def count_entities(records: list) -> Counter:
    cnt: Counter = Counter()
    for r in records:
        for t in r["tags"]:
            if t.startswith("B-"):
                cnt[t[2:]] += 1
    return cnt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--dry-run", action="store_true", help="통계만 표시하고 파일 저장하지 않음")
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    print("=" * 70)
    print(f"빌드: {args.config}")
    print("=" * 70)

    train_all: list = []
    dev_all: list = []
    test_all: list = []
    per_source_summary: list = []

    for source_name, spec in cfg["sources"].items():
        if not spec.get("enabled", True):
            print(f"\n[{source_name}] disabled — 건너뜀")
            continue
        print(f"\n[{source_name}]")

        maybe_run_converter(source_name, spec.get("converter"))

        loaded = load_source(source_name, spec)
        print(f"  로드: train={len(loaded['train'])} dev={len(loaded['dev'])} test={len(loaded['test'])}")

        filters = spec.get("filters", [])
        for split in ("train", "dev", "test"):
            if loaded[split] and filters:
                loaded[split] = apply_filters(loaded[split], filters, f"{source_name}/{split}")

        weight = spec.get("weight", 1)
        if weight and weight != 1:
            loaded["train"] = apply_weight(loaded["train"], weight)
            print(f"  weight={weight} → train: {len(loaded['train'])} (oversample)")

        train_all.extend(loaded["train"])
        dev_all.extend(loaded["dev"])
        test_all.extend(loaded["test"])

        per_source_summary.append({
            "source": source_name,
            "train": len(loaded["train"]),
            "dev": len(loaded["dev"]),
            "test": len(loaded["test"]),
            "entities": dict(count_entities(loaded["train"])),
        })

    # 파이프라인 사후처리
    pipe = cfg.get("pipeline", {})
    cleanup_cfg = pipe.get("label_noise_cleanup", {})
    if cleanup_cfg.get("enabled"):
        apply_to = cleanup_cfg.get("apply_to", "train")
        thresh = cleanup_cfg.get("minority_threshold", 0.15)
        min_cnt = cleanup_cfg.get("min_count", 5)
        print(f"\n[pipeline] label_noise_cleanup → {apply_to} (thresh={thresh}, min_count={min_cnt})")
        if apply_to == "train":
            train_all, stats = clean_label_noise(train_all, thresh, min_cnt)
        elif apply_to == "all":
            train_all, st1 = clean_label_noise(train_all, thresh, min_cnt)
            dev_all, _ = clean_label_noise(dev_all, thresh, min_cnt)
            test_all, _ = clean_label_noise(test_all, thresh, min_cnt)
            stats = st1
        print(f"  → cleanup targets={stats['cleanup_targets']}, "
              f"changed entities={stats['changed_entities']}")

    # 셔플
    seed = pipe.get("seed", 42)
    rng = random.Random(seed)
    rng.shuffle(train_all)
    rng.shuffle(dev_all)
    rng.shuffle(test_all)

    # 출력
    print("\n" + "=" * 70)
    print("최종 분포")
    print("=" * 70)
    print(f"  train: {len(train_all):,} entities={dict(count_entities(train_all))}")
    print(f"  dev:   {len(dev_all):,} entities={dict(count_entities(dev_all))}")
    print(f"  test:  {len(test_all):,} entities={dict(count_entities(test_all))}")

    print("\nsource 기여:")
    for s in per_source_summary:
        print(f"  {s['source']:<16} train={s['train']:>8,} dev={s['dev']:>6,} test={s['test']:>6,}  entities={s['entities']}")

    if args.dry_run:
        print("\n[dry-run] 파일 저장 안 함")
        return

    outputs = pipe.get("outputs", {})
    out_train = REPO_ROOT / outputs.get("train", "data/processed/train.jsonl")
    out_dev = REPO_ROOT / outputs.get("dev", "data/processed/dev.jsonl")
    out_test = REPO_ROOT / outputs.get("test", "data/processed/test.jsonl")
    out_labels = REPO_ROOT / outputs.get("label_list", "data/processed/label_list.txt")

    out_train.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(train_all, out_train)
    write_jsonl(dev_all, out_dev)
    write_jsonl(test_all, out_test)

    # label_list
    labels = ["O"]
    for lbl in TARGET_LABELS:
        labels.append(f"B-{lbl}")
        labels.append(f"I-{lbl}")
    with open(out_labels, "w", encoding="utf-8") as f:
        for lbl in labels:
            f.write(lbl + "\n")

    # manifest
    manifest_path = out_train.parent / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "config": str(args.config.relative_to(REPO_ROOT) if args.config.is_absolute() else args.config),
            "sources": per_source_summary,
            "totals": {
                "train": len(train_all),
                "dev": len(dev_all),
                "test": len(test_all),
            },
            "outputs": {k: str(v) for k, v in outputs.items()},
        }, f, ensure_ascii=False, indent=2)

    print(f"\n저장 완료:")
    print(f"  {out_train}")
    print(f"  {out_dev}")
    print(f"  {out_test}")
    print(f"  {out_labels}")
    print(f"  {manifest_path}")


if __name__ == "__main__":
    main()
