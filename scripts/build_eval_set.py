"""Multi-source 평가셋 구성.

단일 출처(KLUE dev)의 좁은 평가 분포 문제를 보완하기 위해, 여러 출처를 섞은
평가셋을 만든다. iter6(KLUE-only) vs iter9(KLUE+NIKL) 같은 모델을 공정 비교.

구성:
  - KLUE dev      : 기존 dev.jsonl 의 klue source (학습에 안 쓰임)
  - NIKL holdout  : nikl.jsonl 중 train(nikl_sample.jsonl) 에 없는 문장에서 추출
  - Naver holdout : naver_train.jsonl 에서 추출 (현 train 에 Naver 미사용)
  - 합성          : 기존 dev.jsonl 의 synthetic source
  - 실사용        : data/eval/realworld_labeled.jsonl (수작업 라벨)

data leak 방지: 각 holdout 은 train 에 쓰인 문장과 토큰 단위로 중복 제거.

실행:
    python scripts/build_eval_set.py
출력:
    data/eval/multisource_eval.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import List, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO_ROOT, read_jsonl  # noqa: E402

DATA = REPO_ROOT / "data" / "processed"
EVAL = REPO_ROOT / "data" / "eval"


def token_key(rec: dict) -> Tuple[str, ...]:
    return tuple(rec["tokens"])


def count_entities(records: List[dict]) -> Counter:
    c: Counter = Counter()
    for r in records:
        for t in r["tags"]:
            if t.startswith("B-"):
                c[t[2:]] += 1
    return c


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nikl-n", type=int, default=2000, help="NIKL holdout 추출 수")
    parser.add_argument("--naver-n", type=int, default=2000, help="Naver holdout 추출 수")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=EVAL / "multisource_eval.jsonl")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    bins: dict[str, List[dict]] = {}

    # ── 1. KLUE dev + 합성 dev (기존 dev.jsonl 에서 source 별 분리) ──
    dev_path = DATA / "dev.jsonl"
    if dev_path.exists():
        klue_dev, synth_dev = [], []
        for r in read_jsonl(dev_path):
            src = r.get("source", "?")
            if src == "klue":
                klue_dev.append(r)
            elif src == "synthetic":
                synth_dev.append(r)
        bins["klue"] = klue_dev
        bins["synthetic"] = synth_dev
        print(f"KLUE dev: {len(klue_dev)} / 합성 dev: {len(synth_dev)}")
    else:
        print(f"⚠️ {dev_path} 없음")

    # ── 2. NIKL holdout (train 에 쓴 nikl_sample 제외) ──
    nikl_full = DATA / "nikl.jsonl"
    nikl_train = DATA / "nikl_sample.jsonl"
    if nikl_full.exists():
        used: Set[Tuple[str, ...]] = set()
        if nikl_train.exists():
            for r in read_jsonl(nikl_train):
                used.add(token_key(r))
        holdout = [r for r in read_jsonl(nikl_full) if token_key(r) not in used]
        rng.shuffle(holdout)
        # 엔티티 있는 문장 위주로 추출 (평가 의미있게)
        with_ent = [r for r in holdout if any(t != "O" for t in r["tags"])]
        picked = with_ent[: args.nikl_n]
        bins["nikl"] = picked
        print(f"NIKL holdout: 전체 {len(holdout)} (엔티티 포함 {len(with_ent)}) → {len(picked)} 추출")
    else:
        print(f"⚠️ {nikl_full} 없음 — NIKL holdout 스킵")

    # ── 3. Naver holdout ──
    naver_path = DATA / "naver_train.jsonl"
    if naver_path.exists():
        naver = list(read_jsonl(naver_path))
        rng.shuffle(naver)
        with_ent = [r for r in naver if any(t != "O" for t in r["tags"])]
        picked = with_ent[: args.naver_n]
        bins["naver"] = picked
        print(f"Naver holdout: 전체 {len(naver)} (엔티티 포함 {len(with_ent)}) → {len(picked)} 추출")
    else:
        print(f"⚠️ {naver_path} 없음 — Naver holdout 스킵")

    # ── 4. 실사용 수작업 라벨 ──
    rw_path = EVAL / "realworld_labeled.jsonl"
    if rw_path.exists():
        rw = list(read_jsonl(rw_path))
        bins["realworld"] = rw
        print(f"실사용 라벨: {len(rw)}")
    else:
        print(f"⚠️ {rw_path} 없음 — 실사용 스킵")

    # ── 합치기 ──
    all_records: List[dict] = []
    print("\n=== 출처별 구성 ===")
    print(f"{'source':<12} {'문장':>8} {'엔티티':>30}")
    for src, recs in bins.items():
        ent = count_entities(recs)
        all_records.extend(recs)
        print(f"{src:<12} {len(recs):>8,} {str(dict(ent)):>30}")

    rng.shuffle(all_records)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False))
            f.write("\n")

    total_ent = count_entities(all_records)
    print(f"\n총 {len(all_records):,} 문장 → {args.out}")
    print(f"전체 엔티티: {dict(total_ent)}")


if __name__ == "__main__":
    main()
