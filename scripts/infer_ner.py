"""학습된 NER 모델로 텍스트 추론 + 마스킹.

설계:
    1) 원문에 정규식을 적용해 (start, end, REGEX_TOKEN) 스팬 수집.
    2) 원문에 NER 모델을 적용해 (start, end, NER_LABEL) 스팬 수집.
    3) 두 스팬 리스트를 머지 — 겹치면 정규식 우선(패턴이 더 정확).
    4) 한 번에 마스킹 적용.

정규식 마스킹된 텍스트를 NER 에 다시 입력하면 자리표시자(`[PHONE]` 등)가 다시 NER 에
재분류되는 문제가 있어 원문 기반 머지 방식이 더 안전하다.

실행:
    python scripts/infer_ner.py --model-dir models/klue_bert_ner_balanced \
        --text "내 이름은 김민수, 010-1234-5678."
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pii_regex.patterns import find_regex_spans  # noqa: E402


@dataclass
class Span:
    start: int
    end: int
    token: str
    text: str
    src: str  # "regex" or "ner"


def collect_ner_spans(text: str, model_dir: str) -> List[Span]:
    from transformers import pipeline

    pipe = pipeline(
        "token-classification",
        model=model_dir,
        tokenizer=model_dir,
        aggregation_strategy="simple",
    )
    out: List[Span] = []
    for e in pipe(text):
        out.append(
            Span(
                start=int(e["start"]),
                end=int(e["end"]),
                token=e["entity_group"],
                text=text[int(e["start"]) : int(e["end"])],
                src="ner",
            )
        )
    return out


def merge_spans(regex_spans: List[Span], ner_spans: List[Span]) -> List[Span]:
    """정규식 우선으로 머지. 겹치는 NER 스팬은 제거."""
    merged: List[Span] = list(regex_spans)
    occupied: List[Tuple[int, int]] = [(s.start, s.end) for s in regex_spans]
    for s in ner_spans:
        if any(not (s.end <= a or s.start >= b) for a, b in occupied):
            continue
        merged.append(s)
        occupied.append((s.start, s.end))
    merged.sort(key=lambda s: s.start)
    return merged


def apply_masking(text: str, spans: List[Span]) -> str:
    out: List[str] = []
    cursor = 0
    for s in spans:
        out.append(text[cursor : s.start])
        out.append(f"[{s.token}]")
        cursor = s.end
    out.append(text[cursor:])
    return "".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--text", required=True)
    args = parser.parse_args()

    text = args.text
    print(f"원문: {text}")

    regex_raw = find_regex_spans(text)
    regex_spans = [
        Span(s.start, s.end, s.token, s.text, "regex") for s in regex_raw
    ]

    ner_spans = collect_ner_spans(text, args.model_dir)

    merged = merge_spans(regex_spans, ner_spans)
    masked = apply_masking(text, merged)

    print(f"마스킹 결과: {masked}")
    print("적용 스팬:")
    for s in merged:
        print(f"  [{s.src:5}] [{s.token:8}] {s.text!r}")


if __name__ == "__main__":
    main()
