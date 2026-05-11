"""여러 NER 모델의 로짓을 평균해서 앙상블 평가.

각 모델은 같은 label_list.txt 를 가져야 한다 (같은 라벨 공간).
서브워드 토크나이저가 달라도 word-level 라벨로 환원해서 비교 가능.

실행:
    python scripts/ensemble_eval.py \
        --model-dirs models/klue_bert_ner_full models/klue_roberta_iter2 \
        --data data/processed/dev.jsonl \
        --weights 1.0 1.0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_jsonl  # noqa: E402


def get_word_logits(model_dir: Path, records: List[dict], batch_size: int = 32) -> List[List[List[float]]]:
    """각 모델에서 각 문장의 word-level logit (num_labels) 리스트를 얻는다.

    각 word 의 logit = 그 word 의 첫 서브워드 토큰의 logit. (학습 시 라벨 정렬 방식과 동일)
    """
    from transformers import AutoModelForTokenClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
    model = AutoModelForTokenClassification.from_pretrained(str(model_dir))
    model.eval()

    all_word_logits: List[List[List[float]]] = []
    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        enc = tokenizer(
            [r["tokens"] for r in batch],
            is_split_into_words=True,
            truncation=True,
            max_length=256,
            padding=True,
            return_tensors="pt",
        )
        with torch.no_grad():
            logits = model(**enc).logits  # (B, T, C)

        for bi, r in enumerate(batch):
            n_words = len(r["tokens"])
            word_ids = enc.word_ids(batch_index=bi)
            word_logits: List[List[float]] = [None] * n_words  # type: ignore
            prev_word = None
            for tok_idx, w in enumerate(word_ids):
                if w is None or w == prev_word or w >= n_words:
                    prev_word = w
                    continue
                word_logits[w] = logits[bi, tok_idx].tolist()
                prev_word = w
            # 만약 truncation 으로 word_logits 가 안 채워졌으면 0 벡터로
            n_labels = logits.shape[-1]
            for w in range(n_words):
                if word_logits[w] is None:
                    word_logits[w] = [0.0] * n_labels
            all_word_logits.append(word_logits)

    return all_word_logits


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dirs", nargs="+", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--weights", nargs="+", type=float, default=None)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    from seqeval.metrics import classification_report, f1_score, precision_score, recall_score

    weights = args.weights if args.weights else [1.0] * len(args.model_dirs)
    if len(weights) != len(args.model_dirs):
        raise SystemExit("--weights 개수가 모델 수와 다릅니다")

    # 첫 번째 모델의 label_list 사용
    labels_file = args.model_dirs[0] / "label_list.txt"
    labels = [l.strip() for l in open(labels_file, encoding="utf-8") if l.strip()]
    id2label = {i: l for i, l in enumerate(labels)}
    n_labels = len(labels)
    print(f"라벨({n_labels}): {labels}")

    # 모든 모델이 같은 label space 인지 확인
    for d in args.model_dirs[1:]:
        f = d / "label_list.txt"
        other = [l.strip() for l in open(f, encoding="utf-8") if l.strip()]
        if other != labels:
            raise SystemExit(f"라벨 공간이 다릅니다: {d}")

    records = list(read_jsonl(args.data))
    print(f"문장: {len(records)} / 모델: {len(args.model_dirs)} / weights: {weights}")

    # 각 모델에서 word-level logits 얻기
    summed = None
    for mdl, w in zip(args.model_dirs, weights):
        print(f"  {mdl} 추론 중...")
        wl = get_word_logits(mdl, records, args.batch_size)
        if summed is None:
            summed = [[[w * v for v in lg] for lg in sent] for sent in wl]
        else:
            for si, sent in enumerate(wl):
                for wi, lg in enumerate(sent):
                    for ci, v in enumerate(lg):
                        summed[si][wi][ci] += w * v

    # 가중합 → argmax → BIO 태그
    true_seqs: List[List[str]] = []
    pred_seqs: List[List[str]] = []
    for r, lg_sent in zip(records, summed):
        true = r["tags"]
        pred = []
        for word_logit in lg_sent:
            best = max(range(n_labels), key=lambda i: word_logit[i])
            pred.append(id2label[best])
        true_seqs.append(true)
        pred_seqs.append(pred)

    print("\nP/R/F1 (entity-level, seqeval):")
    print(f"  precision: {precision_score(true_seqs, pred_seqs, zero_division=0):.4f}")
    print(f"  recall:    {recall_score(true_seqs, pred_seqs, zero_division=0):.4f}")
    print(f"  f1:        {f1_score(true_seqs, pred_seqs, zero_division=0):.4f}")
    print("\n라벨별 리포트:")
    print(classification_report(true_seqs, pred_seqs, digits=4, zero_division=0))


if __name__ == "__main__":
    main()
