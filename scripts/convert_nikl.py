"""국립국어원 개체명 말뭉치 → 통합 BIO JSONL.

원본 포맷 (모두의 말뭉치 NER, JSON):
{
  "document": [
    {
      "sentence": [
        {
          "form": "...",          # 원문 문장
          "NE": [
            {"form": "이순신", "label": "PS_NAME", "begin": 0, "end": 3},
            ...
          ]
        }, ...
      ]
    }, ...
  ]
}

원본 라벨 (세분화): PS_*, OGG_*, LCP_*, LCG_*, AF_*, DT_*, TI_*, QT_*, EV_*, ...
→ prefix(2~3글자) 단위로 매핑한다.

준비:
    국립국어원 모두의말뭉치(https://corpus.korean.go.kr) 에서 NER 말뭉치를 신청해 받은
    JSON 파일들을 data/raw/nikl/ 에 둔다 (여러 파일 가능).

실행:
    python scripts/convert_nikl.py
출력:
    data/processed/nikl.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterator, Tuple

from common import REPO_ROOT, load_label_mapping, spans_to_word_bio, write_jsonl


def iter_files(root: Path) -> Iterator[Path]:
    if root.is_file():
        yield root
        return
    yield from sorted(root.rglob("*.json"))


def iter_sentences(path: Path) -> Iterator[Tuple[str, list]]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    documents = data.get("document") or data.get("documents") or []
    for doc in documents:
        for sent in doc.get("sentence") or doc.get("sentences") or []:
            form = sent.get("form") or sent.get("text")
            ne = sent.get("NE") or sent.get("ne") or []
            if not form or not ne:
                continue
            spans = [
                {"begin": e["begin"], "end": e["end"], "label": e["label"]}
                for e in ne
                if "begin" in e and "end" in e and "label" in e
            ]
            yield form, spans


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--in-dir",
        type=Path,
        default=REPO_ROOT / "data" / "raw" / "nikl",
    )
    parser.add_argument(
        "--out-path",
        type=Path,
        default=REPO_ROOT / "data" / "processed" / "nikl.jsonl",
    )
    args = parser.parse_args()

    if not args.in_dir.exists():
        raise SystemExit(
            f"원본 디렉터리가 없습니다: {args.in_dir}\n"
            "https://corpus.korean.go.kr 에서 NER 말뭉치(JSON)를 받아 위 경로에 두세요."
        )

    label_map = load_label_mapping()["nikl_prefix"]

    records = []
    files = list(iter_files(args.in_dir))
    if not files:
        raise SystemExit(f"JSON 파일을 찾지 못함: {args.in_dir}")

    for fp in files:
        for sentence, spans in iter_sentences(fp):
            words, tags = spans_to_word_bio(sentence, spans, label_map)
            if not words:
                continue
            records.append({"tokens": words, "tags": tags, "source": "nikl"})

    n = write_jsonl(records, args.out_path)
    print(f"{n} 문장 (총 {len(files)} 파일) → {args.out_path}")


if __name__ == "__main__":
    main()
