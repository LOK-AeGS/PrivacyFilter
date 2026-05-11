"""[PROJ_N] 합성 학습 데이터 생성기.

일반 공개 NER 데이터셋에는 프로젝트명 라벨이 존재하지 않으므로, 템플릿 + 사전 기반
합성 데이터를 만들어 학습한다.

입력:
    data/synthetic/proj_names.txt   — 프로젝트명 사전
    data/synthetic/person_names.txt — 인명 풀
    data/synthetic/orgs.txt         — 기관명 풀
    data/synthetic/locations.txt    — 지명 풀
    data/synthetic/templates.txt    — <TAG>...</TAG> 마크업 템플릿

출력:
    data/processed/proj_synthetic.jsonl

각 출력 라인:
    {"tokens": [...], "tags": ["B-PROJ_N", "I-PROJ_N", "O", ...], "source": "synthetic"}

규칙:
- 어절은 화이트스페이스 분할. 한국어 조사가 엔티티 끝에 붙은 경우, 해당 어절은 I-X 태그를 유지한다.
- 첫 토큰이 B-X, 나머지 엔티티 토큰은 I-X.
- 마크업 태그명: PROJ → PROJ_N, PER → PERSON, ORG → ORG, LOC → LOCATION.
"""

from __future__ import annotations

import argparse
import random
import re
from pathlib import Path
from typing import Dict, List, Tuple

from common import REPO_ROOT, write_jsonl

TAG_TO_LABEL = {
    "PROJ": "PROJ_N",
    "PER": "PERSON",
    "ORG": "ORG",
    "LOC": "LOCATION",
}

ENTITY_RE = re.compile(r"<(PROJ|PER|ORG|LOC)>(.*?)</\1>")
SLOT_RE = re.compile(r"\{(proj|person|org|loc)\}")


def load_lines(path: Path) -> List[str]:
    lines: List[str] = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            s = raw.rstrip("\n").rstrip("\r").strip()
            if not s or s.startswith("#"):
                continue
            lines.append(s)
    return lines


def parse_marked(text: str) -> Tuple[List[str], List[str]]:
    """<TAG>...</TAG> 마크업 텍스트 → (어절 리스트, BIO 태그 리스트)."""
    # 1) 마크업 제거하고, 문자 단위로 엔티티 영역을 기록
    spans: List[Tuple[int, int, str]] = []  # (begin_char, end_char, label)
    cleaned_parts: List[str] = []
    cursor = 0
    out_pos = 0
    for m in ENTITY_RE.finditer(text):
        pre = text[cursor : m.start()]
        cleaned_parts.append(pre)
        out_pos += len(pre)
        tag = m.group(1)
        content = m.group(2)
        label = TAG_TO_LABEL[tag]
        spans.append((out_pos, out_pos + len(content), label))
        cleaned_parts.append(content)
        out_pos += len(content)
        cursor = m.end()
    cleaned_parts.append(text[cursor:])
    full = "".join(cleaned_parts)

    char_tags = ["O"] * len(full)
    for s, e, lbl in spans:
        for i in range(s, e):
            char_tags[i] = f"{'B' if i == s else 'I'}-{lbl}"

    # 2) 어절(공백 분할) 단위로 합치기. 어절의 첫 글자 태그를 어절 태그로 사용.
    words: List[str] = []
    tags: List[str] = []
    i = 0
    while i < len(full):
        if full[i].isspace():
            i += 1
            continue
        start = i
        first = char_tags[i]
        while i < len(full) and not full[i].isspace():
            i += 1
        words.append(full[start:i])
        tags.append(first)
    return words, tags


def fill_slots(template: str, pools: Dict[str, List[str]], rng: random.Random) -> str:
    def repl(m: re.Match) -> str:
        slot = m.group(1)
        return rng.choice(pools[slot])

    return SLOT_RE.sub(repl, template)


def generate(
    pools: Dict[str, List[str]],
    templates: List[str],
    n: int,
    seed: int,
) -> List[dict]:
    rng = random.Random(seed)
    records = []
    seen = set()
    attempts = 0
    while len(records) < n and attempts < n * 10:
        attempts += 1
        tpl = rng.choice(templates)
        filled = fill_slots(tpl, pools, rng)
        if filled in seen:
            continue
        seen.add(filled)
        tokens, tags = parse_marked(filled)
        if not tokens:
            continue
        records.append({"tokens": tokens, "tags": tags, "source": "synthetic"})
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=1500, help="생성할 문장 수")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--out-path",
        type=Path,
        default=REPO_ROOT / "data" / "processed" / "proj_synthetic.jsonl",
    )
    args = parser.parse_args()

    base = REPO_ROOT / "data" / "synthetic"
    pools = {
        "proj": load_lines(base / "proj_names.txt"),
        "person": load_lines(base / "person_names.txt"),
        "org": load_lines(base / "orgs.txt"),
        "loc": load_lines(base / "locations.txt"),
    }
    templates = load_lines(base / "templates.txt")

    for k, v in pools.items():
        if not v:
            raise SystemExit(f"풀이 비어있습니다: {k}")
    if not templates:
        raise SystemExit("템플릿이 비어있습니다.")

    records = generate(pools, templates, args.n, args.seed)
    n = write_jsonl(records, args.out_path)
    print(f"{n} 합성 문장 → {args.out_path}")

    # 통계 출력
    from collections import Counter
    cnt = Counter()
    for r in records:
        for t in r["tags"]:
            if t != "O":
                cnt[t] += 1
    print("BIO 태그 분포:")
    for k, v in sorted(cnt.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
