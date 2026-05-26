"""Multi-source 평가셋을 source 별로 분리해서 entity-F1 측정.

단일 출처(KLUE) 평가의 편향을 드러내기 위해, 같은 모델을 source 별로 따로 평가한다.

실행:
    python scripts/eval_by_source.py --model-dir models/klue_roberta_large_iter6 \
        --data data/eval/multisource_eval.jsonl
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_jsonl  # noqa: E402

# 가제티어 (extension/lib/mask_service.js 와 동일) — 모델이 놓친 ORG/LOC 보강.
_GAZETTEER = [
    (re.compile(r"[가-힣A-Za-z0-9]{2,}\s?(?:대학교|대학|주식회사|병원|의원|은행|증권|연구원|연구소|그룹)"), "ORG"),
    (re.compile(r"(?:㈜|\(주\))\s?[가-힣A-Za-z0-9]{2,}|[가-힣A-Za-z0-9]{2,}\s?(?:㈜|\(주\))"), "ORG"),
    (re.compile(r"[가-힣]{2,}(?:특별자치시|특별자치도|특별시|광역시)"), "LOCATION"),
]


def apply_gazetteer(tokens: List[str], tags: List[str]) -> List[str]:
    """공백 결합 문장에서 가제티어 매치 → 모델이 O 인 어절만 B/I 로 채움(모델 우선)."""
    text = " ".join(tokens)
    offs, pos = [], 0
    for w in tokens:
        offs.append((pos, pos + len(w)))
        pos += len(w) + 1
    out = list(tags)
    for rx, label in _GAZETTEER:
        for m in rx.finditer(text):
            s, e = m.start(), m.end()
            widx = [i for i, (ws, we) in enumerate(offs) if not (we <= s or ws >= e)]
            if not widx or any(out[i] != "O" for i in widx):
                continue  # 모델이 이미 본 어절이면 스킵
            for j, i in enumerate(widx):
                out[i] = ("B-" if j == 0 else "I-") + label
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--gazetteer", action="store_true", help="모델 예측에 가제티어 보강 적용(시스템 평가)")
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
            if args.gazetteer:
                tags = apply_gazetteer(r["tokens"], tags)
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
