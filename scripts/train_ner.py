"""한국어 NER 모델 학습 (HuggingFace Trainer).

기본 백본: `klue/bert-base` (KLUE 팀이 공개한 한국어 BERT).

입력:
    --train data/processed/<train>.jsonl
    --dev   data/processed/<dev>.jsonl
    --labels data/processed/label_list.txt
    각 JSONL 라인: {"tokens": [...], "tags": ["B-PERSON", ...], "source": "..."}

출력:
    --out-dir 에 모델 + 토크나이저 + label_list 저장 (HF from_pretrained 로 재로드 가능)

평가:
    seqeval 기반 entity-level F1 (Precision/Recall/F1) — KLUE-NER 평가 방식과 동일.

실행 예:
    python scripts/train_ner.py \
        --train data/processed/klue_train.jsonl \
        --dev   data/processed/klue_dev.jsonl \
        --labels data/processed/label_list.txt \
        --out-dir models/klue_bert_ner \
        --epochs 3 --batch-size 32 --lr 5e-5

CPU 만 있는 환경에서는 --epochs 1 --batch-size 8 --max-train-samples 1000 정도로 동작 확인.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO_ROOT, read_jsonl  # noqa: E402


def load_label_list(path: Path) -> List[str]:
    with open(path, encoding="utf-8") as f:
        labels = [ln.strip() for ln in f if ln.strip()]
    if "O" not in labels:
        raise ValueError("label_list 에 'O' 가 없습니다")
    return labels


def load_jsonl_as_dataset(path: Path, limit: int | None = None):
    from datasets import Dataset

    records = list(read_jsonl(path))
    if limit:
        records = records[:limit]
    return Dataset.from_list(records)


def build_align_fn(tokenizer, label2id: Dict[str, int]):
    """단어 단위 라벨을 서브워드 단위로 정렬.

    - 한 단어가 여러 서브워드로 쪼개지면 첫 서브워드만 라벨을 갖고, 나머지는 -100.
    - 특수 토큰([CLS], [SEP], padding)도 -100.
    """
    def align(examples):
        tokenized = tokenizer(
            examples["tokens"],
            is_split_into_words=True,
            truncation=True,
            max_length=256,
        )
        all_labels = []
        for i, tags in enumerate(examples["tags"]):
            word_ids = tokenized.word_ids(batch_index=i)
            prev_word = None
            label_ids = []
            for w in word_ids:
                if w is None:
                    label_ids.append(-100)
                elif w != prev_word:
                    label_ids.append(label2id[tags[w]])
                else:
                    label_ids.append(-100)
                prev_word = w
            all_labels.append(label_ids)
        tokenized["labels"] = all_labels
        return tokenized

    return align


def build_metrics_fn(id2label: Dict[int, str]):
    """seqeval entity-level P/R/F1 + 라벨별 F1."""
    import numpy as np
    from seqeval.metrics import (
        classification_report,
        f1_score,
        precision_score,
        recall_score,
    )

    def metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)

        true_labels: List[List[str]] = []
        pred_labels: List[List[str]] = []
        for p_row, l_row in zip(preds, labels):
            t_seq, p_seq = [], []
            for p_i, l_i in zip(p_row, l_row):
                if l_i == -100:
                    continue
                t_seq.append(id2label[l_i])
                p_seq.append(id2label[p_i])
            true_labels.append(t_seq)
            pred_labels.append(p_seq)

        out = {
            "precision": precision_score(true_labels, pred_labels, zero_division=0),
            "recall": recall_score(true_labels, pred_labels, zero_division=0),
            "f1": f1_score(true_labels, pred_labels, zero_division=0),
        }
        report = classification_report(
            true_labels, pred_labels, output_dict=True, zero_division=0
        )
        for ent, stats in report.items():
            if ent in ("micro avg", "macro avg", "weighted avg"):
                continue
            out[f"f1_{ent}"] = stats.get("f1-score", 0.0)
        return out

    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, default=REPO_ROOT / "data" / "processed" / "klue_train.jsonl")
    parser.add_argument("--dev", type=Path, default=REPO_ROOT / "data" / "processed" / "klue_dev.jsonl")
    parser.add_argument("--labels", type=Path, default=REPO_ROOT / "data" / "processed" / "label_list.txt")
    parser.add_argument("--model", type=str, default="klue/bert-base")
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "models" / "klue_bert_ner")
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=5e-5)
    parser.add_argument("--max-train-samples", type=int, default=None)
    parser.add_argument("--max-dev-samples", type=int, default=None)
    parser.add_argument("--fp16", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    # imports inside main to keep --help fast and avoid heavy startup on errors
    from transformers import (
        AutoModelForTokenClassification,
        AutoTokenizer,
        DataCollatorForTokenClassification,
        Trainer,
        TrainingArguments,
        set_seed,
    )

    set_seed(args.seed)

    # 라벨
    labels = load_label_list(args.labels)
    label2id = {lbl: i for i, lbl in enumerate(labels)}
    id2label = {i: lbl for lbl, i in label2id.items()}
    print(f"라벨 수: {len(labels)} — {labels}")

    # 데이터
    train_ds = load_jsonl_as_dataset(args.train, args.max_train_samples)
    dev_ds = load_jsonl_as_dataset(args.dev, args.max_dev_samples)
    print(f"train: {len(train_ds)} / dev: {len(dev_ds)}")

    # 토크나이저 / 모델
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForTokenClassification.from_pretrained(
        args.model,
        num_labels=len(labels),
        id2label=id2label,
        label2id=label2id,
    )

    align = build_align_fn(tokenizer, label2id)
    train_tok = train_ds.map(align, batched=True, remove_columns=train_ds.column_names)
    dev_tok = dev_ds.map(align, batched=True, remove_columns=dev_ds.column_names)

    collator = DataCollatorForTokenClassification(tokenizer)
    metrics_fn = build_metrics_fn(id2label)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    targs = TrainingArguments(
        output_dir=str(args.out_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        learning_rate=args.lr,
        weight_decay=0.01,
        warmup_ratio=0.1,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        logging_steps=50,
        save_total_limit=2,
        fp16=args.fp16,
        report_to="none",
        seed=args.seed,
    )

    # transformers 5.x 부터 `tokenizer` 인자가 `processing_class` 로 이름 변경됨.
    # 4.x 호환을 위해 try/except 으로 분기.
    try:
        trainer = Trainer(
            model=model,
            args=targs,
            train_dataset=train_tok,
            eval_dataset=dev_tok,
            processing_class=tokenizer,
            data_collator=collator,
            compute_metrics=metrics_fn,
        )
    except TypeError:
        trainer = Trainer(
            model=model,
            args=targs,
            train_dataset=train_tok,
            eval_dataset=dev_tok,
            tokenizer=tokenizer,
            data_collator=collator,
            compute_metrics=metrics_fn,
        )

    trainer.train()
    final_metrics = trainer.evaluate()
    print("=== dev 평가 ===")
    for k, v in final_metrics.items():
        print(f"  {k}: {v}")

    # 모델 + 토크나이저 + 라벨 리스트 저장
    trainer.save_model(str(args.out_dir))
    tokenizer.save_pretrained(str(args.out_dir))
    with open(args.out_dir / "label_list.txt", "w", encoding="utf-8") as f:
        for lbl in labels:
            f.write(lbl + "\n")
    with open(args.out_dir / "eval_results.json", "w", encoding="utf-8") as f:
        json.dump(final_metrics, f, ensure_ascii=False, indent=2)
    print(f"모델/토크나이저/라벨 저장: {args.out_dir}")


if __name__ == "__main__":
    main()
