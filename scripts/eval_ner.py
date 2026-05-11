"""학습된 NER 모델을 임의 JSONL 에 대해 평가.

실행:
    python scripts/eval_ner.py --model-dir models/klue_bert_ner_partial --data data/processed/dev.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO_ROOT, read_jsonl  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    import torch
    from seqeval.metrics import classification_report, f1_score, precision_score, recall_score
    from transformers import AutoModelForTokenClassification, AutoTokenizer

    label_path = args.model_dir / "label_list.txt"
    if not label_path.exists():
        raise SystemExit(f"label_list.txt 가 없습니다: {label_path}")
    labels = [ln.strip() for ln in open(label_path, encoding="utf-8") if ln.strip()]
    id2label = {i: l for i, l in enumerate(labels)}
    label2id = {l: i for i, l in id2label.items()}

    tokenizer = AutoTokenizer.from_pretrained(str(args.model_dir))
    model = AutoModelForTokenClassification.from_pretrained(str(args.model_dir))
    model.eval()

    records = list(read_jsonl(args.data))
    print(f"{args.data.name}: {len(records)} 문장")

    true_seqs: List[List[str]] = []
    pred_seqs: List[List[str]] = []

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
            tags_true = r["tags"]
            t_seq: List[str] = []
            p_seq: List[str] = []
            prev_word = None
            for tok_idx, w in enumerate(word_ids):
                if w is None or w == prev_word:
                    prev_word = w
                    continue
                if w >= len(tags_true):
                    prev_word = w
                    continue
                t_seq.append(tags_true[w])
                p_seq.append(id2label[pred_ids[bi][tok_idx]])
                prev_word = w
            true_seqs.append(t_seq)
            pred_seqs.append(p_seq)

    print(f"P/R/F1 (entity-level, seqeval):")
    print(f"  precision: {precision_score(true_seqs, pred_seqs, zero_division=0):.4f}")
    print(f"  recall:    {recall_score(true_seqs, pred_seqs, zero_division=0):.4f}")
    print(f"  f1:        {f1_score(true_seqs, pred_seqs, zero_division=0):.4f}")
    print("\n라벨별 리포트:")
    print(classification_report(true_seqs, pred_seqs, digits=4, zero_division=0))


if __name__ == "__main__":
    main()
