"""학습된 NER 모델로 텍스트 추론 + 마스킹.

파이프라인:
    1) pii_regex.patterns 로 1차 정규식 마스킹
    2) NER 모델로 2차 엔티티 마스킹

실행:
    python scripts/infer_ner.py --model-dir models/klue_bert_ner --text "내 이름은 김민수, 010-1234-5678."
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pii_regex.patterns import apply_regex_masking  # noqa: E402


def mask_with_ner(text: str, model_dir: str) -> Tuple[str, list]:
    from transformers import pipeline

    pipe = pipeline(
        "token-classification",
        model=model_dir,
        tokenizer=model_dir,
        aggregation_strategy="simple",
    )
    ents = pipe(text)

    out_parts: List[str] = []
    cursor = 0
    for e in ents:
        s, end_ = int(e["start"]), int(e["end"])
        out_parts.append(text[cursor:s])
        out_parts.append(f"[{e['entity_group']}]")
        cursor = end_
    out_parts.append(text[cursor:])
    return "".join(out_parts), ents


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--text", required=True)
    args = parser.parse_args()

    print(f"원문: {args.text}")
    after_regex, regex_spans = apply_regex_masking(args.text)
    print(f"1차 정규식: {after_regex}")
    print(f"  적용 토큰: {[s.token for s in regex_spans]}")

    masked, ents = mask_with_ner(after_regex, args.model_dir)
    print(f"2차 NER: {masked}")
    print(f"  적용 엔티티: {[(e['entity_group'], e['word']) for e in ents]}")


if __name__ == "__main__":
    main()
