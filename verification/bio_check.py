"""BIO 태깅 무결성 검증.

검사 항목:
  1. tokens 길이 == tags 길이
  2. 태그 형식이 'O' 또는 'B-X' / 'I-X'
  3. X 는 TARGET_LABELS 에 속해야 함
  4. I-X 앞에 B-X 또는 I-X 가 와야 함 (sequence transition 검사)
  5. 빈 문장 없음

실패하면 종료코드 1, 첫 50건의 위반 사례를 출력.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import TARGET_LABELS, read_jsonl  # noqa: E402

VALID_LABELS = set(TARGET_LABELS)
MAX_REPORT = 50


def check(path: Path) -> int:
    violations = []
    n = 0
    for idx, r in enumerate(read_jsonl(path)):
        n += 1
        tokens = r.get("tokens", [])
        tags = r.get("tags", [])

        if len(tokens) != len(tags):
            violations.append((idx, "length_mismatch", f"{len(tokens)} vs {len(tags)}"))
            continue
        if len(tokens) == 0:
            violations.append((idx, "empty", ""))
            continue

        prev_label = None
        for ti, tag in enumerate(tags):
            if tag == "O":
                prev_label = None
                continue
            if "-" not in tag:
                violations.append((idx, "bad_format", f"pos {ti}: '{tag}'"))
                prev_label = None
                continue
            pos, _, lbl = tag.partition("-")
            if pos not in ("B", "I"):
                violations.append((idx, "bad_position", f"pos {ti}: '{tag}'"))
                prev_label = None
                continue
            if lbl not in VALID_LABELS:
                violations.append((idx, "unknown_label", f"pos {ti}: '{tag}'"))
                prev_label = None
                continue
            if pos == "I" and lbl != prev_label:
                violations.append(
                    (idx, "I_without_B", f"pos {ti}: '{tag}' (prev label={prev_label})")
                )
            prev_label = lbl

    print(f"\n=== {path.name} ===")
    print(f"문장 {n}, 위반 {len(violations)}건")
    for v in violations[:MAX_REPORT]:
        print(f"  line {v[0]}: {v[1]} {v[2]}")
    if len(violations) > MAX_REPORT:
        print(f"  ... (+{len(violations) - MAX_REPORT}건 생략)")
    return len(violations)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()

    total = 0
    for p in args.paths:
        if not p.exists():
            print(f"[skip] {p} 없음")
            continue
        total += check(p)

    if total > 0:
        sys.exit(1)
    print("\nOK: 무결성 위반 없음")


if __name__ == "__main__":
    main()
