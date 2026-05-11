"""정규식 ↔ NER 충돌 검증.

학습 데이터 안에 1차 정규식(이메일/전화번호/주민번호/IP/카드/API 키)이 NER 엔티티로
잡혀 있으면, 추론 시 정규식이 먼저 마스킹해서 NER 학습 효과가 떨어질 수 있다.

본 스크립트는:
  - 각 어절을 정규식에 통과시켜 매치되는지 확인
  - 동일 어절이 NER 라벨(B-/I-)을 가지고 있으면 충돌로 보고

옵션:
  --report-only   : 충돌 카운트만 출력
  --fix <out>     : 충돌난 어절을 'O' 로 강제 변경한 새 JSONL 을 저장
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import read_jsonl  # noqa: E402
from pii_regex.patterns import REGEX_PATTERNS  # noqa: E402

MAX_REPORT = 30


def detect_regex_token(word: str) -> str | None:
    for token, pattern in REGEX_PATTERNS:
        if pattern.search(word):
            return token
    return None


def run(path: Path, fix_path: Path | None) -> int:
    conflicts = Counter()
    samples = []
    out_records = []
    for r in read_jsonl(path):
        tokens = r["tokens"]
        tags = list(r["tags"])
        modified = False
        for i, w in enumerate(tokens):
            tok = detect_regex_token(w)
            if tok is None:
                continue
            if tags[i] != "O":
                conflicts[f"{tok} <-> {tags[i]}"] += 1
                if len(samples) < MAX_REPORT:
                    samples.append((w, tags[i], tok))
                if fix_path is not None:
                    tags[i] = "O"
                    modified = True
        if fix_path is not None:
            new_r = dict(r)
            if modified:
                new_r["tags"] = tags
            out_records.append(new_r)

    print(f"\n=== {path.name} ===")
    print(f"충돌 총 {sum(conflicts.values())}건")
    for k, v in conflicts.most_common():
        print(f"  {k}: {v}")
    if samples:
        print("샘플:")
        for w, t, tok in samples:
            print(f"  word='{w}' tag={t} regex={tok}")

    if fix_path is not None:
        fix_path.parent.mkdir(parents=True, exist_ok=True)
        with open(fix_path, "w", encoding="utf-8") as f:
            for r in out_records:
                f.write(json.dumps(r, ensure_ascii=False))
                f.write("\n")
        print(f"\n수정본 → {fix_path}")

    return sum(conflicts.values())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument(
        "--fix",
        type=Path,
        default=None,
        help="충돌난 NER 태그를 O 로 만든 결과를 이 경로에 저장 (단일 입력에만 적용)",
    )
    args = parser.parse_args()

    if args.fix and len(args.paths) != 1:
        raise SystemExit("--fix 옵션은 단일 입력 파일에만 사용 가능")

    total = 0
    for p in args.paths:
        if not p.exists():
            print(f"[skip] {p} 없음")
            continue
        total += run(p, args.fix)

    print(f"\n총 충돌: {total}")


if __name__ == "__main__":
    main()
