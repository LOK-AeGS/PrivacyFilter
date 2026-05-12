"""품질 필터 — entity surface 노이즈 제거.

각 필터:
  - record 가 변경되면 새 record(dict) 반환
  - 변경 없으면 원본 반환
  - record 가 완전히 버려져야 하면 None 반환
  - entity 만 제거(O 로 변경) 하는 경우는 record 유지

entity 만 제거하면 tokens 는 유지되고 tags 만 O 로 바뀐다.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple


def bio_to_spans(tags: List[str]) -> List[Tuple[int, int, str]]:
    spans: List[Tuple[int, int, str]] = []
    cur: Tuple[int, int, str] | None = None
    for i, t in enumerate(tags):
        if t == "O":
            if cur:
                spans.append(cur)
                cur = None
            continue
        pos, _, lbl = t.partition("-")
        if pos == "B" or (cur and cur[2] != lbl):
            if cur:
                spans.append(cur)
            cur = (i, i + 1, lbl)
        else:
            cur = (cur[0], i + 1, lbl) if cur else (i, i + 1, lbl)
    if cur:
        spans.append(cur)
    return spans


def _clear_span(tags: List[str], s: int, e: int) -> None:
    for i in range(s, e):
        tags[i] = "O"


# ----------------------------------------------------------------------------
# URL / 도메인 포함 entity 제거
# ----------------------------------------------------------------------------
_URL_RE = re.compile(
    r"(https?://|www\.|\(www|\.(com|org|net|kr|co\.kr|or\.kr|go\.kr|ac\.kr)|@\w+\.\w+)"
)


def drop_url_entities(record: dict) -> Optional[dict]:
    """entity surface 안에 URL/도메인/이메일 패턴이 포함되면 그 entity 를 O 로."""
    tokens = record["tokens"]
    tags = list(record["tags"])
    changed = False
    for s, e, _lbl in bio_to_spans(tags):
        surface = " ".join(tokens[s:e])
        if _URL_RE.search(surface):
            _clear_span(tags, s, e)
            changed = True
    if not changed:
        return record
    return {**record, "tags": tags}


# ----------------------------------------------------------------------------
# 특수문자 비율 과다 entity 제거
# ----------------------------------------------------------------------------
def _is_letter_or_digit(c: str) -> bool:
    # 한글 음절: 0xAC00 ~ 0xD7AF
    if 0xAC00 <= ord(c) <= 0xD7AF:
        return True
    return c.isalnum()


def drop_excessive_special_chars(record: dict, threshold: float = 0.5) -> Optional[dict]:
    """entity surface 의 특수문자 비율이 threshold 초과면 O."""
    tokens = record["tokens"]
    tags = list(record["tags"])
    changed = False
    for s, e, _lbl in bio_to_spans(tags):
        surface = "".join(tokens[s:e])  # 어절 공백 제외하고 글자만
        if len(surface) == 0:
            continue
        non_letter = sum(1 for c in surface if not _is_letter_or_digit(c))
        if non_letter / len(surface) > threshold:
            _clear_span(tags, s, e)
            changed = True
    if not changed:
        return record
    return {**record, "tags": tags}


# ----------------------------------------------------------------------------
# 비정상적으로 긴 entity 제거
# ----------------------------------------------------------------------------
def drop_too_long_entities(record: dict, max_words: int = 10) -> Optional[dict]:
    """entity 가 max_words 어절 이상이면 O. (KLUE/Naver 어절 단위 기준)"""
    tags = list(record["tags"])
    changed = False
    for s, e, _lbl in bio_to_spans(tags):
        if e - s > max_words:
            _clear_span(tags, s, e)
            changed = True
    if not changed:
        return record
    return {**record, "tags": tags}


# ----------------------------------------------------------------------------
# 너무 짧은 entity (단일 글자) 제거 — 옵션
# ----------------------------------------------------------------------------
def drop_short_entities(record: dict, min_chars: int = 1) -> Optional[dict]:
    """entity surface 의 글자 수가 min_chars 미만이면 O.

    기본값 1 — entity 가 빈 surface 인 경우만 제거.
    예) min_chars=2 면 한 글자 entity 모두 제거.
    """
    tokens = record["tokens"]
    tags = list(record["tags"])
    changed = False
    for s, e, _lbl in bio_to_spans(tags):
        surface = "".join(tokens[s:e])
        if len(surface) < min_chars:
            _clear_span(tags, s, e)
            changed = True
    if not changed:
        return record
    return {**record, "tags": tags}


# ----------------------------------------------------------------------------
# entity 끝 어절의 trailing 구두점 strip
# ----------------------------------------------------------------------------
_TRAIL = re.compile(r"[,\.\?!\)\]\}>\s]+$")


def strip_trailing_punctuation(record: dict) -> Optional[dict]:
    """entity 마지막 어절 끝의 구두점 strip. 어절 자체는 유지.

    예) "삼성전자," → "삼성전자" 로 어절을 줄임. 다른 어절은 영향 없음.
    """
    tokens = list(record["tokens"])
    tags = record["tags"]
    spans = bio_to_spans(tags)
    changed = False
    for s, e, _lbl in spans:
        last_idx = e - 1
        word = tokens[last_idx]
        new_word = _TRAIL.sub("", word)
        if new_word and new_word != word:
            tokens[last_idx] = new_word
            changed = True
    if not changed:
        return record
    return {**record, "tokens": tokens}
