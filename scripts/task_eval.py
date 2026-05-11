"""마스킹 task 관점의 평가.

세 가지 지표를 함께 계산해서 모델의 마스킹 능력을 다각도로 본다.

1) entity-level F1 (seqeval, 표준 NER 평가)
   - B-X/I-X 경계가 정확히 일치해야 정답

2) token-level F1 (per-word)
   - 각 어절의 라벨 정확도. 경계 살짝 어긋나도 부분 점수.

3) masking coverage (privacy 관점 — recall 강조)
   - per-label "라벨이 X인 어절 중 모델이 같은 X 로 마스킹한 비율"
   - boundary 와 무관하게 라벨만 맞으면 OK
   - 실제 LLM 으로 PII 가 새는지 막는 task 에 가까운 지표

실행:
    python scripts/task_eval.py --model-dir models/klue_roberta_iter2 \
        --data data/processed/dev.jsonl
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_jsonl  # noqa: E402


def strip_bio(tag: str) -> str:
    if tag == "O":
        return "O"
    return tag.partition("-")[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    import torch
    from seqeval.metrics import classification_report, f1_score
    from transformers import AutoModelForTokenClassification, AutoTokenizer

    labels = [l.strip() for l in open(args.model_dir / "label_list.txt", encoding="utf-8") if l.strip()]
    id2label = {i: l for i, l in enumerate(labels)}
    target_labels = sorted({strip_bio(l) for l in labels if l != "O"})

    tokenizer = AutoTokenizer.from_pretrained(str(args.model_dir))
    model = AutoModelForTokenClassification.from_pretrained(str(args.model_dir))
    model.eval()

    records = list(read_jsonl(args.data))
    print(f"{args.data.name}: {len(records)} 문장")

    true_bio: List[List[str]] = []
    pred_bio: List[List[str]] = []
    # token-level: 라벨 strip ("PERSON" 등). 라벨별 카운터
    token_tp = Counter()  # (label)
    token_fp = Counter()
    token_fn = Counter()
    token_correct = 0
    token_total = 0
    # masking coverage
    cov_correct = Counter()  # gold label → 같은 label 로 예측한 어절 수
    cov_total = Counter()    # gold label 어절 수
    miss_to_o = Counter()    # gold X → 예측 O 로 누락된 어절 수
    miss_to_other = Counter()  # gold X → 다른 라벨 Y 로 잘못 예측

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
            n_words = len(r["tokens"])
            pred_tags = ["O"] * n_words
            prev_word = None
            for tok_idx, w in enumerate(word_ids):
                if w is None or w == prev_word or w >= n_words:
                    prev_word = w
                    continue
                pred_tags[w] = id2label[pred_ids[bi][tok_idx]]
                prev_word = w

            true_bio.append(r["tags"])
            pred_bio.append(pred_tags)

            for tg, pg in zip(r["tags"], pred_tags):
                tl = strip_bio(tg)
                pl = strip_bio(pg)
                token_total += 1
                if tl == pl:
                    token_correct += 1
                if tl != "O":
                    cov_total[tl] += 1
                    if pl == tl:
                        cov_correct[tl] += 1
                    elif pl == "O":
                        miss_to_o[tl] += 1
                    else:
                        miss_to_other[tl] += 1
                # token-level P/R/F1 per label (BIO 무시, 라벨만)
                if tl == pl and tl != "O":
                    token_tp[tl] += 1
                elif tl != "O" and pl != tl:
                    token_fn[tl] += 1
                elif pl != "O" and tl != pl:
                    token_fp[pl] += 1

    # === 1) Entity-level (seqeval) ===
    print("\n=== [1] Entity-level F1 (seqeval, 엄격) ===")
    print(classification_report(true_bio, pred_bio, digits=4, zero_division=0))
    print(f"micro F1: {f1_score(true_bio, pred_bio, zero_division=0):.4f}")

    # === 2) Token-level (BIO 무시) ===
    print("\n=== [2] Token-level F1 (라벨만, 경계 무관) ===")
    print(f"{'label':<12} {'P':>8} {'R':>8} {'F1':>8} {'support':>8}")
    f1s = {}
    for lbl in target_labels:
        tp, fp, fn = token_tp[lbl], token_fp[lbl], token_fn[lbl]
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        f1s[lbl] = f1
        support = tp + fn
        print(f"{lbl:<12} {p:>8.4f} {r:>8.4f} {f1:>8.4f} {support:>8}")
    print(f"token-acc: {token_correct / token_total:.4f}")

    # === 3) Masking coverage (privacy 관점) ===
    print("\n=== [3] Masking coverage (gold 엔티티 어절 중 같은 라벨로 마스킹된 비율) ===")
    print(f"{'label':<12} {'coverage':>10} {'missed→O':>10} {'missed→他':>10} {'gold tokens':>12}")
    for lbl in target_labels:
        total = cov_total[lbl]
        cov = cov_correct[lbl] / total if total > 0 else 0.0
        m_o = miss_to_o[lbl] / total if total > 0 else 0.0
        m_t = miss_to_other[lbl] / total if total > 0 else 0.0
        print(f"{lbl:<12} {cov:>10.4f} {m_o:>10.4f} {m_t:>10.4f} {total:>12}")

    # 요약
    print("\n=== 요약 ===")
    print(f"{'라벨':<12} {'entity-F1':>10} {'token-F1':>10} {'mask-cov':>10}")
    from seqeval.metrics import f1_score as seq_f1
    # 라벨별 entity F1 다시 계산
    entity_f1s = {}
    for lbl in target_labels:
        true_filt = [[t if strip_bio(t) == lbl else "O" for t in seq] for seq in true_bio]
        pred_filt = [[t if strip_bio(t) == lbl else "O" for t in seq] for seq in pred_bio]
        entity_f1s[lbl] = seq_f1(true_filt, pred_filt, zero_division=0)
    for lbl in target_labels:
        total = cov_total[lbl]
        cov = cov_correct[lbl] / total if total > 0 else 0.0
        print(f"{lbl:<12} {entity_f1s[lbl]:>10.4f} {f1s[lbl]:>10.4f} {cov:>10.4f}")


if __name__ == "__main__":
    main()
