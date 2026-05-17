"""통합 데이터의 마스킹 카테고리 매핑 검증.

5가지 기준:
  M1) 라벨 공간 무결성   — 모든 BIO 태그가 9종(O + 4×B/I)에 속하는지
  M2) 소스별 라벨 분포    — KLUE/Naver/synthetic 각 소스가 어느 라벨에 기여하는지
  M3) 샘플 엔티티 점검    — 라벨별 surface 무작위 추출하여 사람이 봐도 맞는지
  M4) 소스 간 라벨 충돌   — 같은 surface 가 소스별 다른 라벨로 학습되는지
  M5) 경계 일관성 across sources — KLUE vs Naver 의 entity 경계 (조사 부착 등) 차이
  M6) PROJ_N 보호        — PROJ_N 이 KLUE/Naver entity 와 겹치지 않는지

실행:
    python verification/category_mapping_check.py
"""

from __future__ import annotations

import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import REPO_ROOT, read_jsonl  # noqa: E402

DATA = REPO_ROOT / "data" / "processed"
TARGET = ("PERSON", "ORG", "LOCATION", "PROJ_N")
VALID_TAGS = {"O"} | {f"B-{l}" for l in TARGET} | {f"I-{l}" for l in TARGET}


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


def main() -> None:
    train_file = DATA / "train.jsonl"
    if not train_file.exists():
        raise SystemExit(f"파일 없음: {train_file}")
    records = list(read_jsonl(train_file))
    print(f"검증 대상: {train_file.name} ({len(records):,} 문장)\n")

    # ---------- M1) 라벨 공간 무결성 ----------
    print("=" * 70)
    print("[M1] 라벨 공간 무결성 — 모든 태그가 9종(O + 4×B/I) 에 속하는지")
    print("=" * 70)
    all_tags: Counter = Counter()
    invalid_tags: Counter = Counter()
    for r in records:
        for t in r["tags"]:
            all_tags[t] += 1
            if t not in VALID_TAGS:
                invalid_tags[t] += 1
    print(f"  고유 태그 수: {len(all_tags)} (예상 9)")
    for t in sorted(VALID_TAGS):
        print(f"    {t:<14} {all_tags.get(t, 0):>10,}")
    if invalid_tags:
        print(f"  ⚠️  잘못된 태그: {dict(invalid_tags)}")
    else:
        print("  ✅ 모든 태그가 허용 범주.")

    # ---------- M2) 소스별 라벨 분포 ----------
    print("\n" + "=" * 70)
    print("[M2] 소스별 라벨 분포 — 각 소스가 어느 라벨에 기여")
    print("=" * 70)
    by_source: dict[str, Counter] = defaultdict(Counter)
    by_source_sentence: Counter = Counter()
    for r in records:
        src = r.get("source", "?")
        by_source_sentence[src] += 1
        for s, e, lbl in bio_to_spans(r["tags"]):
            by_source[src][lbl] += 1
    print(f"  {'source':<12} {'sent':>10} {'PERSON':>10} {'ORG':>10} {'LOCATION':>10} {'PROJ_N':>10}")
    for src in sorted(by_source):
        n_sent = by_source_sentence[src]
        cells = [by_source[src].get(l, 0) for l in TARGET]
        print(f"  {src:<12} {n_sent:>10,} " + " ".join(f"{c:>10,}" for c in cells))

    # ---------- M3) 라벨별 샘플 엔티티 ----------
    print("\n" + "=" * 70)
    print("[M3] 라벨별 무작위 샘플 (사람 검수용)")
    print("=" * 70)
    by_label_surfaces: dict[str, list] = defaultdict(list)
    for r in records:
        for s, e, lbl in bio_to_spans(r["tags"]):
            src = r.get("source", "?")
            surface = " ".join(r["tokens"][s:e])
            by_label_surfaces[lbl].append((surface, src))
    rng = random.Random(42)
    for lbl in TARGET:
        print(f"\n  --- {lbl} (총 {len(by_label_surfaces[lbl]):,} 인스턴스) ---")
        sampled = rng.sample(by_label_surfaces[lbl], min(15, len(by_label_surfaces[lbl])))
        for s, src in sampled:
            print(f"    [{src:<10}] '{s}'")

    # ---------- M4) 소스 간 라벨 충돌 ----------
    print("\n" + "=" * 70)
    print("[M4] 소스 간 라벨 충돌 — 같은 surface 가 소스 따라 다른 라벨")
    print("=" * 70)
    surf_label_by_src: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    # surf_label_by_src[surface][label][src] = count
    for r in records:
        src = r.get("source", "?")
        for s, e, lbl in bio_to_spans(r["tags"]):
            surface = " ".join(r["tokens"][s:e])
            surf_label_by_src[surface][lbl][src] += 1
    # 충돌: 같은 surface 가 ≥2 라벨, 그리고 각 라벨이 서로 다른 dominant source 일 때
    conflicts = []
    for surf, label_dict in surf_label_by_src.items():
        if len(label_dict) < 2:
            continue
        # 라벨별 dominant source
        sources_per_label = {}
        for lbl, src_cnt in label_dict.items():
            dom_src = src_cnt.most_common(1)[0][0]
            sources_per_label[lbl] = dom_src
        if len(set(sources_per_label.values())) >= 2:
            # 라벨 다른 소스에서 옴
            total = sum(sum(c.values()) for c in label_dict.values())
            conflicts.append((total, surf, dict((l, dict(s)) for l, s in label_dict.items())))
    conflicts.sort(key=lambda x: -x[0])
    print(f"  소스 간 충돌 surface: {len(conflicts):,}")
    print(f"  예시 (상위 15, 총 등장 수 내림차순):")
    for total, surf, breakdown in conflicts[:15]:
        print(f"    '{surf}' total={total}: {breakdown}")

    # ---------- M5) 경계 일관성 across sources ----------
    print("\n" + "=" * 70)
    print("[M5] 경계 일관성 — KLUE vs Naver entity 끝글자 패턴 비교")
    print("=" * 70)
    end_chars_by_src_label: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for r in records:
        src = r.get("source", "?")
        for s, e, lbl in bio_to_spans(r["tags"]):
            words = r["tokens"][s:e]
            if not words:
                continue
            last = words[-1]
            if not last:
                continue
            end_chars_by_src_label[src][lbl][last[-1]] += 1
    # 라벨별 상위 끝글자 비교
    for lbl in ("PERSON", "ORG", "LOCATION"):
        print(f"\n  --- {lbl} 끝글자 분포 (상위 10) ---")
        for src in ("klue", "naver", "synthetic"):
            cnt = end_chars_by_src_label[src][lbl]
            if not cnt:
                continue
            top = cnt.most_common(10)
            total = sum(cnt.values())
            line = ", ".join(f"'{c}':{n}({n/total*100:.0f}%)" for c, n in top)
            print(f"    [{src}] {line}")

    # ---------- M6) PROJ_N 보호 ----------
    print("\n" + "=" * 70)
    print("[M6] PROJ_N 보호 — PROJ_N surface 가 다른 소스의 entity 와 겹치는지")
    print("=" * 70)
    proj_surfaces = set()
    for r in records:
        if r.get("source", "?") != "synthetic":
            continue
        for s, e, lbl in bio_to_spans(r["tags"]):
            if lbl == "PROJ_N":
                proj_surfaces.add(" ".join(r["tokens"][s:e]))
    # 같은 surface 가 KLUE/Naver 에서 다른 라벨로 나타나는지
    leak = []
    for r in records:
        if r.get("source", "?") == "synthetic":
            continue
        for s, e, lbl in bio_to_spans(r["tags"]):
            surface = " ".join(r["tokens"][s:e])
            if surface in proj_surfaces:
                leak.append((surface, lbl, r.get("source", "?")))
    print(f"  PROJ_N surface 종류: {len(proj_surfaces):,}")
    print(f"  KLUE/Naver 에서도 등장한 동일 surface: {len(leak):,}")
    if leak:
        print(f"  예시 (상위 10):")
        for surf, lbl, src in leak[:10]:
            print(f"    '{surf}' (KLUE/Naver=[{src}:{lbl}], synthetic=PROJ_N)")
    else:
        print("  ✅ PROJ_N surface 가 다른 소스 entity 와 겹치지 않음.")


if __name__ == "__main__":
    main()
