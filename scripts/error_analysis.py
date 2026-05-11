"""학습된 NER 모델의 예측 오류를 분류·집계.

오류 카테고리:
  - missed       : gold 엔티티가 있는데 예측이 'O' 만 (또는 잘못된 라벨)
  - extra        : 예측 엔티티가 있는데 gold 가 없음 (false positive)
  - boundary     : 동일 라벨이지만 시작/끝 글자가 다름 (부분 매치)
  - type         : 같은 위치 다른 라벨로 예측 (예: ORG → LOCATION)

각 카테고리를 라벨별로 집계하고, 상위 N 사례를 출력해서 패턴을 보게 한다.

실행:
    python scripts/error_analysis.py --model-dir models/klue_bert_ner_full \
        --data data/processed/dev.jsonl --top 20
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO_ROOT, read_jsonl  # noqa: E402


def bio_to_spans(tags: List[str]) -> List[Tuple[int, int, str]]:
    """BIO → [(start, end, label), ...]  end-exclusive."""
    spans = []
    cur = None
    for i, t in enumerate(tags):
        if t == "O":
            if cur:
                spans.append(cur)
                cur = None
            continue
        pos, _, lbl = t.partition("-")
        if pos == "B":
            if cur:
                spans.append(cur)
            cur = (i, i + 1, lbl)
        elif pos == "I":
            if cur and cur[2] == lbl:
                cur = (cur[0], i + 1, lbl)
            else:
                # 잘못된 BIO — B 로 취급
                if cur:
                    spans.append(cur)
                cur = (i, i + 1, lbl)
    if cur:
        spans.append(cur)
    return spans


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForTokenClassification, AutoTokenizer

    labels = [l.strip() for l in open(args.model_dir / "label_list.txt", encoding="utf-8") if l.strip()]
    id2label = {i: l for i, l in enumerate(labels)}

    tokenizer = AutoTokenizer.from_pretrained(str(args.model_dir))
    model = AutoModelForTokenClassification.from_pretrained(str(args.model_dir))
    model.eval()

    records = list(read_jsonl(args.data))
    print(f"{args.data.name}: {len(records)} 문장 분석")

    # 카테고리별 카운터
    cat_cnt: dict[str, Counter] = defaultdict(Counter)  # cat → label → count
    examples: dict[str, List[dict]] = defaultdict(list)

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

            gold_spans = bio_to_spans(r["tags"])
            pred_spans = bio_to_spans(pred_tags)
            gold_set = {(s, e, l) for s, e, l in gold_spans}
            pred_set = {(s, e, l) for s, e, l in pred_spans}

            # exact 매치는 정답
            tp = gold_set & pred_set

            # gold 에만 있는 — missed 또는 boundary 또는 type
            gold_only = gold_set - tp
            pred_only = pred_set - tp

            # 매칭 시도: gold span 과 겹치는 pred span 찾기
            used_pred: set = set()
            for gs, ge, gl in gold_only:
                # 같은 위치 + 다른 라벨?
                same_pos_diff_label = [
                    (ps, pe, pl) for (ps, pe, pl) in pred_only
                    if (ps, pe) == (gs, ge) and pl != gl and (ps, pe, pl) not in used_pred
                ]
                if same_pos_diff_label:
                    pred_only_span = same_pos_diff_label[0]
                    used_pred.add(pred_only_span)
                    cat_cnt["type"][gl] += 1
                    if len(examples["type"]) < args.top:
                        examples["type"].append({
                            "tokens": r["tokens"], "gold": (gs, ge, gl), "pred": pred_only_span
                        })
                    continue
                # 겹치는 pred 있나? (boundary)
                overlapping = [
                    (ps, pe, pl) for (ps, pe, pl) in pred_only
                    if pl == gl and not (pe <= gs or ps >= ge) and (ps, pe, pl) not in used_pred
                ]
                if overlapping:
                    pred_only_span = overlapping[0]
                    used_pred.add(pred_only_span)
                    cat_cnt["boundary"][gl] += 1
                    if len(examples["boundary"]) < args.top:
                        examples["boundary"].append({
                            "tokens": r["tokens"], "gold": (gs, ge, gl), "pred": pred_only_span
                        })
                    continue
                # 그 외 — missed
                cat_cnt["missed"][gl] += 1
                if len(examples["missed"]) < args.top:
                    examples["missed"].append({
                        "tokens": r["tokens"], "gold": (gs, ge, gl), "pred": None
                    })

            # pred 만 있는 — extra (이미 사용된 것 제외)
            for ps, pe, pl in pred_only:
                if (ps, pe, pl) in used_pred:
                    continue
                cat_cnt["extra"][pl] += 1
                if len(examples["extra"]) < args.top:
                    examples["extra"].append({
                        "tokens": r["tokens"], "gold": None, "pred": (ps, pe, pl)
                    })

    # 출력
    print("\n=== 오류 카테고리 × 라벨 ===")
    print(f"{'카테고리':<10}", " | ".join(f"{l:<10}" for l in ("PERSON", "ORG", "LOCATION", "PROJ_N")))
    for cat in ("missed", "boundary", "type", "extra"):
        cnt = cat_cnt[cat]
        cells = [f"{cnt[l]:<10}" for l in ("PERSON", "ORG", "LOCATION", "PROJ_N")]
        print(f"{cat:<10}", " | ".join(cells))

    print("\n=== 상위 사례 ===")
    for cat in ("boundary", "missed", "extra", "type"):
        print(f"\n--- {cat} (최대 {args.top}) ---")
        for ex in examples[cat][: args.top]:
            tokens = ex["tokens"]
            gold = ex.get("gold")
            pred = ex.get("pred")
            if gold:
                gtext = " ".join(tokens[gold[0]:gold[1]])
            else:
                gtext = "—"
            if pred:
                ptext = " ".join(tokens[pred[0]:pred[1]])
            else:
                ptext = "—"
            print(f"  gold=[{gold}: '{gtext}']  pred=[{pred}: '{ptext}']")


if __name__ == "__main__":
    main()
