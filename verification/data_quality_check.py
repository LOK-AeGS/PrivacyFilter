"""데이터셋 품질 평가 — 6가지 기준.

기준:
  C1) 라벨 일관성       — 같은 surface 가 여러 다른 라벨로 어노테이션됨? (annotation noise)
  C2) BIO 무결성 (확장)  — I-X 전이, 연속 B-X, 0-length 등
  C3) 경계/조사 일관성   — 같은 base 가 어떤 곳은 "서울에"(1어절 entity), 어떤 곳은 "서울" + "에"(2어절)?
  C4) 중복/leak          — train ∩ dev/test 동일 문장 존재?
  C5) source × 라벨 분포 — 라벨별 소스 편중 (예: PROJ_N 은 합성에만 존재)
  C6) 엔티티 길이 분포   — 비정상적으로 긴/짧은 엔티티? 0-length?

실행:
    python verification/data_quality_check.py
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import REPO_ROOT, read_jsonl  # noqa: E402

DATA = REPO_ROOT / "data" / "processed"
FILES = ["train.jsonl", "dev.jsonl", "test.jsonl"]


def strip_bio(tag: str) -> str:
    return "O" if tag == "O" else tag.partition("-")[2]


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


def load_all() -> dict:
    return {name: list(read_jsonl(DATA / name)) for name in FILES if (DATA / name).exists()}


def c1_label_consistency(records: list, label: str = None) -> dict:
    """C1: 같은 surface 가 여러 라벨로 어노테이션된 비율."""
    surface_labels: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        spans = bio_to_spans(r["tags"])
        for s, e, lbl in spans:
            surface = " ".join(r["tokens"][s:e])
            surface_labels[surface][lbl] += 1
    # 같은 surface 가 ≥2 종류 라벨로 등장한 경우
    inconsistent = {s: dict(c) for s, c in surface_labels.items() if len(c) >= 2}
    total_surfaces = len(surface_labels)
    return {
        "total_unique_surfaces": total_surfaces,
        "inconsistent_count": len(inconsistent),
        "inconsistency_rate": len(inconsistent) / max(total_surfaces, 1),
        "examples": dict(list(inconsistent.items())[:10]),
    }


def c2_bio_integrity_extended(records: list) -> dict:
    """C2: BIO 무결성 확장 — I-X without B-X, label switch within span, 0-length, etc."""
    i_without_b = 0
    label_switch = 0  # B-X I-Y 같은 케이스
    zero_length_entity = 0
    consecutive_b = 0  # B-X B-X (같은 라벨)

    for r in records:
        tags = r["tags"]
        prev_pos = None
        prev_lbl = None
        for t in tags:
            if t == "O":
                prev_pos = "O"
                prev_lbl = None
                continue
            pos, _, lbl = t.partition("-")
            if pos == "I" and (prev_pos not in ("B", "I") or prev_lbl != lbl):
                i_without_b += 1
            if pos == "I" and prev_pos == "B" and prev_lbl != lbl:
                label_switch += 1
            if pos == "B" and prev_pos == "B" and prev_lbl == lbl:
                consecutive_b += 1
            prev_pos = pos
            prev_lbl = lbl

    return {
        "i_without_b": i_without_b,
        "label_switch_in_span": label_switch,
        "consecutive_b_same_label": consecutive_b,
        "zero_length": zero_length_entity,
    }


def c3_boundary_particle_consistency(records: list) -> dict:
    """C3: 같은 entity 의 surface 가 조사 부착/분리로 변형됨?

    같은 base ('서울') 가 어떤 곳은 entity 가 '서울' 1어절, 어떤 곳은 '서울에' 1어절,
    또는 '서울' (entity) + '에' (O) 두 어절로 나뉘는 경우를 카운트.
    """
    # base = surface[0] 의 처음 (조사가 끝에 붙는 한국어 특성)
    # 같은 entity surface 의 끝 글자 분포를 본다.
    entity_endings: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        spans = bio_to_spans(r["tags"])
        for s, e, lbl in spans:
            words = r["tokens"][s:e]
            if not words:
                continue
            last_word = words[-1]
            # entity 마지막 어절의 마지막 글자가 어떤 글자인지
            last_char = last_word[-1] if last_word else ""
            # 라벨별로 어떤 끝글자가 자주 나오는지
            base = words[0]  # 첫 어절 (덜 변형됨)
            entity_endings[f"{lbl}|{base}"][last_char] += 1

    # 같은 (lbl, base) 가 2종 이상 끝글자로 나타난 경우
    inconsistent = {k: dict(c) for k, c in entity_endings.items() if len(c) >= 2}
    return {
        "total_lbl_base": len(entity_endings),
        "inconsistent_ending_count": len(inconsistent),
        "rate": len(inconsistent) / max(len(entity_endings), 1),
        "examples": dict(list(inconsistent.items())[:15]),
    }


def c4_duplicate_leak(all_records: dict) -> dict:
    """C4: train 과 dev/test 사이 동일 문장 존재?"""
    train_set = set(tuple(r["tokens"]) for r in all_records.get("train.jsonl", []))
    leaks = {}
    for name in ("dev.jsonl", "test.jsonl"):
        if name not in all_records:
            continue
        recs = all_records[name]
        dup = sum(1 for r in recs if tuple(r["tokens"]) in train_set)
        leaks[name] = {"total": len(recs), "duplicated_in_train": dup, "rate": dup / max(len(recs), 1)}
    return leaks


def c5_source_label_distribution(all_records: dict) -> dict:
    """C5: source × 라벨 분포."""
    out = {}
    for name, recs in all_records.items():
        src_lbl: dict[str, Counter] = defaultdict(Counter)
        for r in recs:
            src = r.get("source", "?")
            for t in r["tags"]:
                if t.startswith("B-"):
                    src_lbl[src][t[2:]] += 1
        out[name] = {s: dict(c) for s, c in src_lbl.items()}
    return out


def c6_entity_length_distribution(records: list) -> dict:
    """C6: 엔티티 길이(어절 수) 분포."""
    lengths_by_label: dict[str, Counter] = defaultdict(Counter)
    zero_len = 0
    extreme_long = 0
    for r in records:
        spans = bio_to_spans(r["tags"])
        for s, e, lbl in spans:
            length = e - s
            if length == 0:
                zero_len += 1
            elif length >= 10:
                extreme_long += 1
            lengths_by_label[lbl][length] += 1
    # 라벨별 평균/최대/p95
    stats = {}
    for lbl, c in lengths_by_label.items():
        items = []
        for length, cnt in c.items():
            items.extend([length] * cnt)
        items.sort()
        n = len(items)
        if n == 0:
            continue
        stats[lbl] = {
            "n": n,
            "mean": sum(items) / n,
            "median": items[n // 2],
            "p95": items[int(n * 0.95)],
            "max": items[-1],
            "distribution_top5": dict(c.most_common(5)),
        }
    return {"by_label": stats, "zero_length": zero_len, "length_ge_10": extreme_long}


def main() -> None:
    print("=" * 70)
    print("데이터 품질 평가 (C1~C6)")
    print("=" * 70)

    all_recs = load_all()
    for fname in FILES:
        if fname not in all_recs:
            print(f"[missing] {fname}")

    for fname, records in all_recs.items():
        print(f"\n--- {fname} (n={len(records)}) ---")

        print("\n[C1] 라벨 일관성 (같은 surface 가 여러 라벨로 등장)")
        r = c1_label_consistency(records)
        print(f"  unique surfaces: {r['total_unique_surfaces']:,}")
        print(f"  inconsistent: {r['inconsistent_count']:,} ({r['inconsistency_rate']*100:.2f}%)")
        if r["examples"]:
            print("  예시 (상위 10):")
            for s, c in list(r["examples"].items())[:10]:
                print(f"    '{s}' → {c}")

        print("\n[C2] BIO 무결성 (확장)")
        r = c2_bio_integrity_extended(records)
        for k, v in r.items():
            print(f"  {k}: {v}")

        print("\n[C3] 경계/조사 일관성 (같은 entity base 의 끝글자 변이)")
        r = c3_boundary_particle_consistency(records)
        print(f"  (lbl, base) 조합: {r['total_lbl_base']:,}")
        print(f"  변이 케이스: {r['inconsistent_ending_count']:,} ({r['rate']*100:.2f}%)")
        if r["examples"]:
            print("  예시 (상위 15):")
            for k, c in list(r["examples"].items())[:15]:
                print(f"    {k} → {c}")

        print("\n[C6] 엔티티 길이 분포")
        r = c6_entity_length_distribution(records)
        for lbl, st in r["by_label"].items():
            print(f"  {lbl}: n={st['n']:,}, mean={st['mean']:.2f}, median={st['median']}, p95={st['p95']}, max={st['max']}")
        if r["zero_length"]:
            print(f"  zero-length: {r['zero_length']}")
        if r["length_ge_10"]:
            print(f"  length ≥ 10: {r['length_ge_10']}")

    print("\n--- 전 분할 비교 ---")
    print("\n[C4] train ∩ dev/test 중복 (data leak)")
    r = c4_duplicate_leak(all_recs)
    for k, v in r.items():
        print(f"  {k}: {v['duplicated_in_train']}/{v['total']} ({v['rate']*100:.2f}%)")

    print("\n[C5] source × 라벨 분포")
    r = c5_source_label_distribution(all_recs)
    for fname, src_dict in r.items():
        print(f"  {fname}:")
        for src, cnt in src_dict.items():
            print(f"    {src}: {cnt}")


if __name__ == "__main__":
    main()
