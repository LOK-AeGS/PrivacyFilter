"""AI-Hub 개인정보 비식별화 → 통합 BIO JSONL.

용도: 정규식 토큰(RRN, PHONE, EMAIL, ...) 검증·평가용 보조 데이터셋.
NER 학습 본세트에는 포함하지 않는다 (정규식이 1차로 처리하므로).

원본 포맷은 하위 도메인(의료/금융 등)에 따라 상이하므로, 본 스크립트는
다음 두 가지 표준 변형을 지원한다.

(A) JSON-span 포맷:
{
  "data": [
    {"text": "...", "entities": [{"begin": 0, "end": 3, "type": "NAME"}, ...]},
    ...
  ]
}

(B) JSONL 포맷:
{"text": "...", "entities": [{"begin": 0, "end": 3, "type": "NAME"}, ...]}

준비:
    AI-Hub(https://aihub.or.kr) 에서 신청·다운로드한 데이터를 위 두 포맷 중 하나로
    정규화하여 data/raw/aihub/ 에 둔다.

실행:
    python scripts/convert_aihub.py
출력:
    data/processed/aihub.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterator, List, Tuple

from common import REPO_ROOT, load_label_mapping, spans_to_word_bio, write_jsonl


def iter_records(root: Path) -> Iterator[Tuple[str, list]]:
    paths: List[Path] = []
    if root.is_file():
        paths = [root]
    else:
        paths = sorted(list(root.rglob("*.json")) + list(root.rglob("*.jsonl")))

    for fp in paths:
        if fp.suffix == ".jsonl":
            with open(fp, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    text = obj.get("text") or obj.get("sentence")
                    entities = obj.get("entities") or obj.get("ne") or []
                    if text and entities:
                        yield text, entities
        else:
            with open(fp, encoding="utf-8") as f:
                obj = json.load(f)
            for r in obj.get("data") or obj.get("documents") or []:
                text = r.get("text") or r.get("sentence")
                entities = r.get("entities") or r.get("ne") or []
                if text and entities:
                    yield text, entities


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--in-dir",
        type=Path,
        default=REPO_ROOT / "data" / "raw" / "aihub",
    )
    parser.add_argument(
        "--out-path",
        type=Path,
        default=REPO_ROOT / "data" / "processed" / "aihub.jsonl",
    )
    args = parser.parse_args()

    if not args.in_dir.exists():
        raise SystemExit(
            f"원본 디렉터리가 없습니다: {args.in_dir}\n"
            "AI-Hub 에서 받은 데이터를 표준 JSON/JSONL 로 정규화하여 위 경로에 두세요."
        )

    label_map = load_label_mapping()["aihub"]

    records = []
    for text, entities in iter_records(args.in_dir):
        spans = []
        for e in entities:
            t = e.get("type") or e.get("label")
            b = e.get("begin", e.get("start"))
            ed = e.get("end")
            if t is None or b is None or ed is None:
                continue
            spans.append({"begin": b, "end": ed, "label": t})
        words, tags = spans_to_word_bio(text, spans, label_map)
        if not words:
            continue
        records.append({"tokens": words, "tags": tags, "source": "aihub"})

    n = write_jsonl(records, args.out_path)
    print(f"{n} 문장 → {args.out_path}")


if __name__ == "__main__":
    main()
