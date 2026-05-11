"""데이터셋 검증 일괄 실행.

순서:
  1. stats.py    — 분포 통계
  2. bio_check.py — BIO 무결성
  3. conflict_check.py — 정규식 충돌

실행:
    python verification/verify_all.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import REPO_ROOT  # noqa: E402

from stats import summarize  # noqa: E402
from bio_check import check as bio_check  # noqa: E402
from conflict_check import run as conflict_run  # noqa: E402


def main() -> None:
    processed = REPO_ROOT / "data" / "processed"
    files = [
        processed / "train.jsonl",
        processed / "dev.jsonl",
        processed / "test.jsonl",
    ]
    files = [f for f in files if f.exists()]
    if not files:
        # fallback: 변환만 마친 파일들도 검증 대상에 포함
        files = sorted(processed.glob("*.jsonl"))
    if not files:
        raise SystemExit(f"검증할 JSONL 이 없습니다: {processed}")

    print("=" * 60)
    print("1) 통계")
    print("=" * 60)
    for f in files:
        summarize(f)

    print("\n" + "=" * 60)
    print("2) BIO 무결성")
    print("=" * 60)
    bio_total = 0
    for f in files:
        bio_total += bio_check(f)

    print("\n" + "=" * 60)
    print("3) 정규식 ↔ NER 충돌")
    print("=" * 60)
    conflict_total = 0
    for f in files:
        conflict_total += conflict_run(f, None)

    print("\n" + "=" * 60)
    print("종합")
    print("=" * 60)
    print(f"BIO 위반: {bio_total}")
    print(f"정규식 충돌: {conflict_total}")
    sys.exit(1 if bio_total > 0 else 0)


if __name__ == "__main__":
    main()
