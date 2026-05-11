"""KLUE-NER → 통합 BIO JSONL.

HuggingFace `datasets` 를 통해 자동 다운로드한다. 별도 raw 데이터 배치 불필요.

원본 라벨: B-DT, I-DT, B-LC, I-LC, B-OG, I-OG, B-PS, I-PS, B-QT, I-QT, B-TI, I-TI, O
원본 tokens: 문자 단위 (sentence == "".join(tokens))

실행:
    python scripts/convert_klue.py
출력:
    data/processed/klue_train.jsonl
    data/processed/klue_dev.jsonl
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from common import (
    REPO_ROOT,
    char_bio_to_word_bio,
    load_label_mapping,
    write_jsonl,
)


def convert_split(split, label_names: List[str], label_map: dict) -> list:
    records = []
    for example in split:
        # KLUE-NER 의 tokens 는 문자 단위. sentence 는 공식 필드가 있으면 사용,
        # 없으면 tokens 를 그대로 join.
        tokens = example.get("tokens") or list(example.get("sentence", ""))
        tag_ids = example["ner_tags"]
        if len(tokens) != len(tag_ids):
            # 정합성 깨진 행은 스킵
            continue
        sentence = "".join(tokens)
        char_tags = [label_names[i] for i in tag_ids]
        words, word_tags = char_bio_to_word_bio(sentence, char_tags, label_map)
        if not words:
            continue
        records.append({"tokens": words, "tags": word_tags, "source": "klue"})
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "data" / "processed",
    )
    args = parser.parse_args()

    try:
        from datasets import load_dataset
    except ImportError as e:
        raise SystemExit(
            "datasets 패키지가 필요합니다. `pip install -r requirements.txt`"
        ) from e

    mapping = load_label_mapping()
    label_map = mapping["klue"]

    print("KLUE-NER 다운로드 중...")
    ds = load_dataset("klue", "ner")
    label_names = ds["train"].features["ner_tags"].feature.names
    print(f"원본 라벨 클래스: {label_names}")

    for split_name, file_name in [("train", "klue_train.jsonl"), ("validation", "klue_dev.jsonl")]:
        records = convert_split(ds[split_name], label_names, label_map)
        out = args.out_dir / file_name
        n = write_jsonl(records, out)
        print(f"[{split_name}] {n} 문장 → {out}")


if __name__ == "__main__":
    main()
