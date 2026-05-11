"""변환 스크립트 공통 유틸리티.

- 통합 포맷: JSONL, 각 줄에 {tokens, tags, source}
- 토큰화 방식: 화이트스페이스 분할 (word-level)
- 태깅: BIO ("B-PERSON", "I-PERSON", "O", ...)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs" / "label_mapping.yaml"
TARGET_LABELS = ("PERSON", "ORG", "LOCATION", "PROJ_N")


def load_label_mapping(path: Path = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def map_label(raw_label: str, mapping: Dict[str, str]) -> str:
    """원본 라벨 → 통합 라벨. 매핑이 없으면 'O'."""
    return mapping.get(raw_label, "O")


def normalize_bio(tags: List[str]) -> List[str]:
    """BIO 시퀀스에서 I-X 가 B-X/I-X(같은 라벨) 다음에 오지 않으면 B-X 로 강제 변환.

    원본 데이터셋에 종종 보이는 라벨링 잡음을 수정한다.
    """
    out: List[str] = []
    prev_label: str | None = None
    for t in tags:
        if t == "O":
            out.append("O")
            prev_label = None
            continue
        pos, _, lbl = t.partition("-")
        if pos == "I" and lbl != prev_label:
            out.append(f"B-{lbl}")
        else:
            out.append(t)
        prev_label = lbl
    return out


def bio(position: str, label: str) -> str:
    """('B', 'PERSON') → 'B-PERSON', ('I', 'O') → 'O'."""
    if label == "O" or label == "__REGEX__":
        return "O"
    if position not in ("B", "I"):
        raise ValueError(f"invalid BIO position: {position}")
    return f"{position}-{label}"


def char_bio_to_word_bio(
    sentence: str,
    char_tags: List[str],
    label_map: Dict[str, str],
) -> Tuple[List[str], List[str]]:
    """문자 단위 BIO → 어절(공백 기준) 단위 BIO 로 변환.

    - char_tags 는 sentence 와 동일 길이여야 한다 (공백 포함).
    - 어절의 첫 글자 태그를 어절 태그로 사용한다.
    - 라벨은 label_map 으로 통합 라벨로 매핑한다.
    """
    if len(sentence) != len(char_tags):
        raise ValueError(
            f"sentence length {len(sentence)} != char_tags length {len(char_tags)}"
        )

    words: List[str] = []
    tags: List[str] = []
    i = 0
    n = len(sentence)
    while i < n:
        if sentence[i].isspace():
            i += 1
            continue
        start = i
        first_tag = char_tags[i]
        while i < n and not sentence[i].isspace():
            i += 1
        word = sentence[start:i]
        if first_tag == "O" or first_tag == "":
            tags.append("O")
        else:
            position, _, raw_label = first_tag.partition("-")
            mapped = label_map.get(raw_label, "O")
            tags.append(bio(position, mapped))
        words.append(word)

    return words, normalize_bio(tags)


def spans_to_word_bio(
    sentence: str,
    spans: List[dict],
    label_map: Dict[str, str],
) -> Tuple[List[str], List[str]]:
    """엔티티 span 리스트 → 어절 단위 BIO.

    spans 항목: {'begin': int, 'end': int, 'label': str}
        - begin/end 는 sentence 의 문자 인덱스, 반열림 [begin, end)
        - label 은 원본 라벨 문자열

    label_map 에는 prefix 매핑도 허용 (NIKL 처럼 라벨이 PS_NAME 인 경우
    prefix='PS' 로 매핑).
    """
    char_tags = ["O"] * len(sentence)
    for s in spans:
        begin, end, raw = s["begin"], s["end"], s["label"]
        mapped = label_map.get(raw)
        if mapped is None:
            prefix = raw.split("_", 1)[0]
            mapped = label_map.get(prefix, "O")
        if mapped == "O" or mapped == "__REGEX__":
            continue
        for j in range(begin, min(end, len(sentence))):
            char_tags[j] = f"{'B' if j == begin else 'I'}-{mapped}"
    return char_bio_to_word_bio(sentence, char_tags, {lbl: lbl for lbl in TARGET_LABELS})


def write_jsonl(records: Iterable[dict], out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False))
            f.write("\n")
            count += 1
    return count


def read_jsonl(path: Path) -> Iterable[dict]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)
