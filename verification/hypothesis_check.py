"""모델 저성능 가설 검증 — 6개.

H1) 라벨 노이즈        — 같은 surface 가 dev 에서 여러 라벨로 나타나면 모델이 어떻게든 손해
H2) 조사 부착 비일관    — 같은 base 가 KLUE 에서 조사 포함/제외 비일관
H3) 클래스 불균형       — train 의 라벨 빈도 vs dev F1 상관
H4) 엔티티 길이         — 긴 엔티티에서 F1 더 낮은가?
H5) 국가명 모호성       — country surfaces 가 ORG/LOC 사이에서 진동
H6) train/dev 분포 어긋남 — dev 의 surface 가 train 에 등장한 비율

실행:
    python verification/hypothesis_check.py --model-dir models/klue_roberta_large_iter6
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import REPO_ROOT, read_jsonl  # noqa: E402


def bio_to_spans(tags: List[str]) -> List[Tuple[int, int, str]]:
    spans: List[Tuple[int, int, str]] = []
    cur: Tuple[int, int, str] | None = None
    for i, t in enumerate(tags):
        if t == "O":
            if cur:
                spans.append(cur)
                cur = None
            continue
        pos, _, lbl = t.partition("-")
        if pos == "B" or (cur and cur[2] != lbl):
            if cur:
                spans.append(cur)
            cur = (i, i + 1, lbl)
        else:
            cur = (cur[0], i + 1, lbl) if cur else (i, i + 1, lbl)
    if cur:
        spans.append(cur)
    return spans


def get_predictions(model_dir: Path, records: list, batch_size: int = 16):
    import torch
    from transformers import AutoModelForTokenClassification, AutoTokenizer

    labels = [l.strip() for l in open(model_dir / "label_list.txt", encoding="utf-8") if l.strip()]
    id2label = {i: l for i, l in enumerate(labels)}

    tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
    model = AutoModelForTokenClassification.from_pretrained(str(model_dir))
    model.eval()

    all_preds: list = []
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
            all_preds.append(pred_tags)
    return all_preds


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--train", type=Path, default=REPO_ROOT / "data" / "processed" / "train.jsonl")
    parser.add_argument("--dev", type=Path, default=REPO_ROOT / "data" / "processed" / "dev.jsonl")
    args = parser.parse_args()

    print("데이터 로드 및 모델 예측 수집...")
    train = list(read_jsonl(args.train))
    dev = list(read_jsonl(args.dev))
    dev_preds = get_predictions(args.model_dir, dev)

    # ---------- H1: 라벨 노이즈 ----------
    print("\n" + "=" * 70)
    print("H1) 라벨 노이즈 — 같은 surface 가 dev/train 에서 여러 라벨로 등장")
    print("=" * 70)
    train_surface_labels: dict[str, Counter] = defaultdict(Counter)
    for r in train:
        for s, e, lbl in bio_to_spans(r["tags"]):
            train_surface_labels[" ".join(r["tokens"][s:e])][lbl] += 1
    noisy_surfaces = {s: c for s, c in train_surface_labels.items() if len(c) >= 2}

    # dev 의 gold 엔티티 중 train 에서 모호하게 학습된 surface 의 비율
    dev_total = 0
    dev_on_noisy = 0
    dev_on_noisy_correct = 0
    dev_on_clean = 0
    dev_on_clean_correct = 0
    for r, p in zip(dev, dev_preds):
        gold_spans = bio_to_spans(r["tags"])
        pred_spans_set = {(s, e, l) for s, e, l in bio_to_spans(p)}
        for s, e, lbl in gold_spans:
            dev_total += 1
            surface = " ".join(r["tokens"][s:e])
            hit = (s, e, lbl) in pred_spans_set
            if surface in noisy_surfaces:
                dev_on_noisy += 1
                dev_on_noisy_correct += int(hit)
            else:
                dev_on_clean += 1
                dev_on_clean_correct += int(hit)

    print(f"  train 라벨 노이즈 surface: {len(noisy_surfaces):,}")
    print(f"  dev gold 엔티티 총 {dev_total:,}")
    print(f"    노이즈 surface 위: {dev_on_noisy:,} (entity recall {dev_on_noisy_correct/max(dev_on_noisy,1):.4f})")
    print(f"    클린 surface 위:  {dev_on_clean:,} (entity recall {dev_on_clean_correct/max(dev_on_clean,1):.4f})")

    # ---------- H2: 조사 부착 비일관 ----------
    print("\n" + "=" * 70)
    print("H2) 조사 부착 비일관 — 같은 base 의 entity 가 다양한 끝글자로 등장")
    print("=" * 70)
    base_endings: dict[str, Counter] = defaultdict(Counter)
    for r in train:
        for s, e, lbl in bio_to_spans(r["tags"]):
            words = r["tokens"][s:e]
            if not words:
                continue
            base = words[0]
            end_char = words[-1][-1] if words[-1] else ""
            base_endings[f"{lbl}|{base}"][end_char] += 1
    inconsistent_bases = {k: c for k, c in base_endings.items() if len(c) >= 3}

    # dev 의 gold 엔티티 중 train 에서 base 가 3+ 끝글자로 등장한 것 비율 (어려운 entity)
    hard_total, hard_correct = 0, 0
    easy_total, easy_correct = 0, 0
    for r, p in zip(dev, dev_preds):
        gold_spans = bio_to_spans(r["tags"])
        pred_set = {(s, e, l) for s, e, l in bio_to_spans(p)}
        for s, e, lbl in gold_spans:
            words = r["tokens"][s:e]
            if not words:
                continue
            base = words[0]
            key = f"{lbl}|{base}"
            hit = (s, e, lbl) in pred_set
            if key in inconsistent_bases:
                hard_total += 1
                hard_correct += int(hit)
            else:
                easy_total += 1
                easy_correct += int(hit)
    print(f"  3+ 끝글자 base: {len(inconsistent_bases):,}")
    print(f"  dev gold:")
    print(f"    경계 변이 base: {hard_total:,} (recall {hard_correct/max(hard_total,1):.4f})")
    print(f"    경계 일관 base: {easy_total:,} (recall {easy_correct/max(easy_total,1):.4f})")

    # ---------- H3: 클래스 불균형 ----------
    print("\n" + "=" * 70)
    print("H3) 클래스 불균형 — train 빈도 vs dev recall")
    print("=" * 70)
    train_cnt: Counter = Counter()
    dev_cnt: Counter = Counter()
    for r in train:
        for s, e, lbl in bio_to_spans(r["tags"]):
            train_cnt[lbl] += 1
    for r in dev:
        for s, e, lbl in bio_to_spans(r["tags"]):
            dev_cnt[lbl] += 1
    print(f"  {'라벨':<12} {'train_n':>10} {'dev_n':>10} {'recall':>10}")
    # recall per label from preds
    correct: Counter = Counter()
    total: Counter = Counter()
    for r, p in zip(dev, dev_preds):
        pred_set = {(s, e, l) for s, e, l in bio_to_spans(p)}
        for s, e, lbl in bio_to_spans(r["tags"]):
            total[lbl] += 1
            if (s, e, lbl) in pred_set:
                correct[lbl] += 1
    for lbl in sorted(train_cnt):
        rec = correct[lbl] / max(total[lbl], 1)
        print(f"  {lbl:<12} {train_cnt[lbl]:>10,} {dev_cnt[lbl]:>10,} {rec:>10.4f}")

    # ---------- H4: 엔티티 길이별 ----------
    print("\n" + "=" * 70)
    print("H4) 엔티티 길이별 recall")
    print("=" * 70)
    len_total: dict[int, Counter] = defaultdict(Counter)  # length → label → count
    len_correct: dict[int, Counter] = defaultdict(Counter)
    for r, p in zip(dev, dev_preds):
        pred_set = {(s, e, l) for s, e, l in bio_to_spans(p)}
        for s, e, lbl in bio_to_spans(r["tags"]):
            length = e - s
            len_total[length][lbl] += 1
            if (s, e, lbl) in pred_set:
                len_correct[length][lbl] += 1
    print(f"  {'len':<5} {'PERSON':>16} {'ORG':>16} {'LOCATION':>16} {'PROJ_N':>16}")
    for length in sorted(len_total):
        row = [f"{length:<5}"]
        for lbl in ("PERSON", "ORG", "LOCATION", "PROJ_N"):
            tot = len_total[length][lbl]
            cor = len_correct[length][lbl]
            if tot == 0:
                row.append(f"{'-':>16}")
            else:
                row.append(f"{cor}/{tot} {cor/tot:.3f}".rjust(16))
        print("  " + " ".join(row))

    # ---------- H5: 국가명 모호성 ----------
    print("\n" + "=" * 70)
    print("H5) 국가명 모호성 — 특정 surface 의 train ORG↔LOC 분포 + dev 결과")
    print("=" * 70)
    countries = ["한국", "미국", "중국", "일본", "북한", "러시아", "독일", "프랑스", "영국", "브라질",
                 "이스라엘", "벨기에", "이탈리아", "스페인", "인도", "터키", "캐나다", "호주",
                 "한국은", "한국의", "한국이", "한국을", "한국과", "미국은", "미국의", "미국이", "미국과", "북한의"]
    print(f"  {'surface':<10} {'train_ORG':>10} {'train_LOC':>10} {'dev_gold':>20} {'pred_correct':>13}")
    for surf in countries:
        if surf not in train_surface_labels:
            continue
        t = train_surface_labels[surf]
        # dev 에서 이 surface 가 어떻게 처리됐는지
        dev_gold = Counter()
        dev_hit = 0
        dev_tot = 0
        for r, p in zip(dev, dev_preds):
            gold_spans = bio_to_spans(r["tags"])
            pred_set = {(s, e, l) for s, e, l in bio_to_spans(p)}
            for s, e, lbl in gold_spans:
                if " ".join(r["tokens"][s:e]) == surf:
                    dev_gold[lbl] += 1
                    dev_tot += 1
                    if (s, e, lbl) in pred_set:
                        dev_hit += 1
        dev_str = "/".join(f"{k}={v}" for k, v in dev_gold.items()) if dev_gold else "-"
        rec = f"{dev_hit}/{dev_tot}" if dev_tot else "-"
        print(f"  {surf:<10} {t.get('ORG',0):>10} {t.get('LOCATION',0):>10} {dev_str:>20} {rec:>13}")

    # ---------- H6: train/dev 분포 어긋남 ----------
    print("\n" + "=" * 70)
    print("H6) train/dev surface 일치율")
    print("=" * 70)
    train_surfaces_per_label: dict[str, set] = defaultdict(set)
    for r in train:
        for s, e, lbl in bio_to_spans(r["tags"]):
            train_surfaces_per_label[lbl].add(" ".join(r["tokens"][s:e]))
    dev_seen, dev_unseen = Counter(), Counter()
    dev_seen_correct, dev_unseen_correct = Counter(), Counter()
    for r, p in zip(dev, dev_preds):
        pred_set = {(s, e, l) for s, e, l in bio_to_spans(p)}
        for s, e, lbl in bio_to_spans(r["tags"]):
            surf = " ".join(r["tokens"][s:e])
            seen = surf in train_surfaces_per_label[lbl]
            hit = (s, e, lbl) in pred_set
            if seen:
                dev_seen[lbl] += 1
                if hit:
                    dev_seen_correct[lbl] += 1
            else:
                dev_unseen[lbl] += 1
                if hit:
                    dev_unseen_correct[lbl] += 1
    print(f"  {'label':<10} {'seen_n':>8} {'seen_rec':>10} {'unseen_n':>8} {'unseen_rec':>10}")
    for lbl in ("PERSON", "ORG", "LOCATION", "PROJ_N"):
        sn, un = dev_seen[lbl], dev_unseen[lbl]
        sr = dev_seen_correct[lbl] / max(sn, 1)
        ur = dev_unseen_correct[lbl] / max(un, 1)
        print(f"  {lbl:<10} {sn:>8} {sr:>10.4f} {un:>8} {ur:>10.4f}")


if __name__ == "__main__":
    main()
