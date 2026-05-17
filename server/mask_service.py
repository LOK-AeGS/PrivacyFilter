"""마스킹/복원 서비스.

흐름:
  mask(text, session_id):
    1. 정규식 1차 스팬 수집 (RRN, PHONE, EMAIL, CARD, ACCOUNT, IP, API_KEY)
    2. NER 2차 스팬 수집 (PERSON, ORG, LOCATION, PROJ_N)
    3. 스팬 머지 (정규식 우선, 겹치는 NER 제거)
    4. AliasManager 로 alias 할당 (세션 일관성)
    5. 텍스트 치환 (역방향 정렬 후 substring 교체)

  unmask(text, spans):
    각 alias 를 original 로 치환. 어절 경계 무시한 단순 치환 + 조사 보존.
"""

from __future__ import annotations

import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pii_regex.patterns import find_regex_spans  # noqa: E402
from server.alias_manager import AliasManager  # noqa: E402


@dataclass
class Span:
    start: int
    end: int
    label: str
    original: str
    alias: str
    src: str  # "regex" or "ner"


class MaskService:
    def __init__(self, model_dir: str, alias_manager: AliasManager):
        self._alias_manager = alias_manager
        self._model_dir = model_dir
        self._pipe = None  # lazy load

    def _ensure_model(self):
        if self._pipe is None:
            print(f"[MaskService] Loading NER model: {self._model_dir}", flush=True)
            from transformers import pipeline
            self._pipe = pipeline(
                "token-classification",
                model=self._model_dir,
                tokenizer=self._model_dir,
                aggregation_strategy="simple",
            )
            print("[MaskService] Model loaded.", flush=True)

    def _ner_spans(self, text: str) -> List[Tuple[int, int, str, str]]:
        """transformers pipeline 결과를 (start, end, label, original) 리스트로."""
        self._ensure_model()
        ents = self._pipe(text)
        spans: List[Tuple[int, int, str, str]] = []
        for e in ents:
            s, ed = int(e["start"]), int(e["end"])
            spans.append((s, ed, e["entity_group"], text[s:ed]))
        return self._merge_adjacent(spans)

    @staticmethod
    def _merge_adjacent(spans: List[Tuple[int, int, str, str]], max_gap: int = 1) -> List[Tuple[int, int, str, str]]:
        """인접한 같은 라벨의 sub-word 스팬 병합."""
        if not spans:
            return spans
        spans = sorted(spans, key=lambda s: s[0])
        out = [spans[0]]
        for s in spans[1:]:
            last = out[-1]
            if s[2] == last[2] and (s[0] - last[1]) <= max_gap:
                out[-1] = (last[0], s[1], last[2], last[3] + s[3] if s[0] == last[1] else last[3] + " " + s[3])
            else:
                out.append(s)
        # original 텍스트 재계산 (text 가 필요한데 여기선 spans 만 받음 → 호출 측에서 재구성)
        return out

    def _merge_regex_and_ner(self, text: str, regex_raw, ner_spans):
        """regex 우선으로 머지. 겹치는 ner 스팬은 제거."""
        merged = [(s.start, s.end, s.token, s.text, "regex") for s in regex_raw]
        occupied = [(s, e) for s, e, _, _, _ in merged]
        for s, e, lbl, _orig, *_ in ner_spans:
            if any(not (e <= a or s >= b) for a, b in occupied):
                continue
            merged.append((s, e, lbl, text[s:e], "ner"))
            occupied.append((s, e))
        merged.sort(key=lambda x: x[0])
        return merged

    def mask(self, text: str, session_id: str) -> Tuple[str, List[Span], dict]:
        t0 = time.time()

        # 1. 정규식 스팬
        regex_raw = find_regex_spans(text)
        t1 = time.time()

        # 2. NER 스팬
        ner_pre = self._ner_spans(text)
        t2 = time.time()

        # 3. 머지
        merged_raw = self._merge_regex_and_ner(text, regex_raw, ner_pre)

        # 4. Alias 할당 + Span dataclass 생성
        spans: List[Span] = []
        for s, e, lbl, orig, src in merged_raw:
            alias = self._alias_manager.get_alias(session_id, lbl, orig)
            spans.append(Span(start=s, end=e, label=lbl, original=orig, alias=alias, src=src))

        # 5. 텍스트 치환 (역방향 정렬해서 인덱스 안 깨지게)
        out_parts: List[str] = []
        cursor = 0
        for sp in spans:
            out_parts.append(text[cursor : sp.start])
            out_parts.append(sp.alias)
            cursor = sp.end
        out_parts.append(text[cursor:])
        masked_text = "".join(out_parts)

        t3 = time.time()
        latency = {
            "regex_ms": int((t1 - t0) * 1000),
            "ner_ms": int((t2 - t1) * 1000),
            "merge_replace_ms": int((t3 - t2) * 1000),
            "total_ms": int((t3 - t0) * 1000),
        }
        return masked_text, spans, latency

    @staticmethod
    def unmask(text: str, spans: List[Span]) -> str:
        """LLM 응답에서 alias 를 original 로 복원.

        단순 string replace (긴 alias 부터 처리해서 부분 매치 회피).
        """
        if not spans:
            return text
        # alias 길이 내림차순 (긴 것 먼저 — 예: '서울시' 가 '서울' 보다 먼저)
        ordered = sorted(set((sp.alias, sp.original) for sp in spans), key=lambda x: -len(x[0]))
        out = text
        for alias, original in ordered:
            if alias and alias != original:
                out = out.replace(alias, original)
        return out
