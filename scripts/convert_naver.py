"""네이버+창원대 NER (NLP Challenge 2018) → 통합 BIO JSONL.

원본 포맷 (TSV, 어절 단위):
    1  비토리오  PER_B
    2  양일      DAT_B
    3  만에      -
    ...
    (빈 줄로 문장 구분)

태그 형식: `LABEL_B` / `LABEL_I` / `-` (= O)
원본 라벨: PER, ORG, LOC, CVL, DAT, TIM, NUM, AFW, ANM, PLT, MAT, EVT, FLD, TRM

준비:
    https://github.com/naver/nlp-challenge 의 NER 데이터 (train.tsv) 를
    data/raw/naver/train.tsv 로 배치한다.

실행:
    python scripts/convert_naver.py
출력:
    data/processed/naver_train.jsonl
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterator, List, Tuple

from common import REPO_ROOT, bio, load_label_mapping, normalize_bio, write_jsonl


def iter_sentences(path: Path) -> Iterator[Tuple[List[str], List[str]]]:
    tokens: List[str] = []
    tags: List[str] = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n").rstrip("\r")
            if not line.strip():
                if tokens:
                    yield tokens, tags
                    tokens, tags = [], []
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                # 일부 dump 는 'token\ttag' 두 칼럼만 있는 경우도 있음
                if len(parts) == 2:
                    token, tag = parts
                else:
                    continue
            else:
                _, token, tag = parts[0], parts[1], parts[2]
            tokens.append(token)
            tags.append(tag)
    if tokens:
        yield tokens, tags


def remap_tag(tag: str, label_map: dict) -> str:
    """tag 가 'PER_B' (네이버), 'B-PER' (표준), 'O', '-' 형태 모두 지원."""
    if tag == "O" or tag == "-":
        return "O"
    if "_" in tag and tag.rsplit("_", 1)[-1] in ("B", "I"):
        # 네이버 포맷: LABEL_B / LABEL_I
        raw, pos = tag.rsplit("_", 1)
    elif "-" in tag and tag.split("-", 1)[0] in ("B", "I"):
        # 표준 BIO: B-LABEL / I-LABEL
        pos, _, raw = tag.partition("-")
    else:
        return "O"
    mapped = label_map.get(raw, "O")
    return bio(pos, mapped) if mapped != "O" else "O"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--in-path",
        type=Path,
        default=REPO_ROOT / "data" / "raw" / "naver" / "train.tsv",
    )
    parser.add_argument(
        "--out-path",
        type=Path,
        default=REPO_ROOT / "data" / "processed" / "naver_train.jsonl",
    )
    args = parser.parse_args()

    if not args.in_path.exists():
        raise SystemExit(
            f"원본 파일이 없습니다: {args.in_path}\n"
            "https://github.com/naver/nlp-challenge 에서 train.tsv 를 받아 위 경로에 두세요."
        )

    label_map = load_label_mapping()["naver"]

    records = []
    for tokens, tags in iter_sentences(args.in_path):
        new_tags = normalize_bio([remap_tag(t, label_map) for t in tags])
        records.append({"tokens": tokens, "tags": new_tags, "source": "naver"})

    n = write_jsonl(records, args.out_path)
    print(f"{n} 문장 → {args.out_path}")


if __name__ == "__main__":
    main()
