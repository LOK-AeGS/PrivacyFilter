"""Multi-source 평가셋을 source 별로 분리해서 entity-F1 측정.

단일 출처(KLUE) 평가의 편향을 드러내기 위해, 같은 모델을 source 별로 따로 평가한다.

실행:
    python scripts/eval_by_source.py --model-dir models/klue_roberta_large_iter6 \
        --data data/eval/multisource_eval.jsonl
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_jsonl  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()

    import torch
    from seqeval.metrics import f1_score, precision_score, recall_score
    from transformers import AutoModelForTokenClassification, AutoTokenizer

    labels = [l.strip() for l in open(args.model_dir / "label_list.txt", encoding="utf-8") if l.strip()]
    id2label = {i: l for i, l in enumerate(labels)}

    tokenizer = AutoTokenizer.from_pretrained(str(args.model_dir))
    model = AutoModelForTokenClassification.from_pretrained(str(args.model_dir))
    model.eval()

    records = list(read_jsonl(args.data))
    print(f"모델: {args.model_dir.name}")
    print(f"평가셋: {args.data.name} ({len(records):,} 문장)\n")

    # source 별 그룹
    by_src: Dict[str, List[dict]] = defaultdict(list)
    for r in records:
        by_src[r.get("source", "?")].append(r)

    # 예측 (전체 한 번에)
    pred_map: Dict[int, List[str]] = {}
    for start in range(0, len(records), args.batch_size):
        batch = records[start : start + args.batch_size]
        enc = tokenizer(
            [r["tokens"] for r in batch],
            is_split_into_words=True,
            truncation=True,
            max_length=256,
            padding=True,
            return_tensors="pt",
        )
        with torch.no_grad():
            logits = model(**enc).logits
        pred_ids = logits.argmax(dim=-1).cpu().tolist()
        for bi, r in enumerate(batch):
            word_ids = enc.word_ids(batch_index=bi)
            n = len(r["tokens"])
            tags = ["O"] * n
            prev = None
            for ti, w in enumerate(word_ids):
                if w is None or w == prev or w >= n:
                    prev = w
                    continue
                tags[w] = id2label[pred_ids[bi][ti]]
                prev = w
            pred_map[id(r)] = tags

    def eval_group(recs: List[dict]):
        true = [r["tags"] for r in recs]
        pred = [pred_map[id(r)] for r in recs]
        return (
            precision_score(true, pred, zero_division=0),
            recall_score(true, pred, zero_division=0),
            f1_score(true, pred, zero_division=0),
        )

    def eval_group_label(recs: List[dict], label: str):
        true = [[t if t.endswith(label) else "O" for t in r["tags"]] for r in recs]
        pred = [[t if t.endswith(label) else "O" for t in pred_map[id(r)]] for r in recs]
        return f1_score(true, pred, zero_division=0)

    # source 별 출력
    print(f"{'source':<12} {'문장':>7} {'P':>8} {'R':>8} {'F1':>8} | {'PERSON':>8} {'ORG':>8} {'LOC':>8} {'PROJ_N':>8}")
    print("-" * 90)
    order = ["klue", "nikl", "naver", "synthetic", "realworld"]
    for src in order:
        if src not in by_src:
            continue
        recs = by_src[src]
        p, r, f = eval_group(recs)
        pe = eval_group_label(recs, "PERSON")
        og = eval_group_label(recs, "ORG")
        lc = eval_group_label(recs, "LOCATION")
        pj = eval_group_label(recs, "PROJ_N")
        print(f"{src:<12} {len(recs):>7,} {p:>8.4f} {r:>8.4f} {f:>8.4f} | {pe:>8.4f} {og:>8.4f} {lc:>8.4f} {pj:>8.4f}")

    # 전체
    p, r, f = eval_group(records)
    pe = eval_group_label(records, "PERSON")
    og = eval_group_label(records, "ORG")
    lc = eval_group_label(records, "LOCATION")
    pj = eval_group_label(records, "PROJ_N")
    print("-" * 90)
    print(f"{'ALL':<12} {len(records):>7,} {p:>8.4f} {r:>8.4f} {f:>8.4f} | {pe:>8.4f} {og:>8.4f} {lc:>8.4f} {pj:>8.4f}")


if __name__ == "__main__":
    main()
