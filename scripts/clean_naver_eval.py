"""multisource_eval.jsonl 의 naver 도메인에서 문서 아티팩트를 제거해 정제본 생성.

naver(NAVER x 창원대) 원천에는 저작권 표시줄·사진 캡션·바이라인·짧은 조각문이
섞여 있다. 이는 NER 평가 대상이 아닌 문서 노이즈이므로 제거한다. (희귀어·OOD
문장은 '어려운 예시' 라 제거하지 않음 — 체리피킹 방지.) naver 외 source 는 그대로 통과.

원본(multisource_eval.jsonl)은 보존하고 multisource_eval_clean.jsonl 을 생성한다.

실행: python scripts/clean_naver_eval.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
IN = REPO / "data" / "eval" / "multisource_eval.jsonl"
OUT = REPO / "data" / "eval" / "multisource_eval_clean.jsonl"

# 문서 아티팩트 신호 (저작권·캡션·인코딩 기호)
MARKERS = ("ⓒ", "ⓝ", "Copyrights", "copyright", "저작권", "무단전재", "재배포",
           "＜", "＞", "【", "】", "▶", "◀", "☞")


def is_artifact(tokens) -> bool:
    text = " ".join(tokens)
    if any(m in text for m in MARKERS):          # 저작권줄/캡션
        return True
    if len(tokens) < 4:                          # 조각문(헤더·단편)
        return True
    if "@" in text and len(tokens) < 6:          # 이메일 포함 짧은 바이라인
        return True
    return False


def main() -> None:
    kept, removed = [], []
    for line in open(IN, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("source") == "naver" and is_artifact(r["tokens"]):
            removed.append(r)
        else:
            kept.append(r)

    with open(OUT, "w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    total = len(kept) + len(removed)
    nav_before = sum(1 for r in kept + removed if r.get("source") == "naver")
    print(f"전체 {total} → {len(kept)} (제거 {len(removed)})")
    print(f"naver {nav_before} → {nav_before - len(removed)}")
    print(f"저장: {OUT.relative_to(REPO)}")
    print("\n제거 예시(문서 아티팩트):")
    for r in removed[:12]:
        print("  ", " ".join(r["tokens"])[:72])


if __name__ == "__main__":
    main()
