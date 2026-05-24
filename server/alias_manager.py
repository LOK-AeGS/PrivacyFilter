"""세션별 alias 매핑 관리.

같은 세션 내 같은 entity 텍스트는 같은 alias 받도록 보장.
정규식 토큰(PHONE 등)은 더미 값 + 등장 순서 번호 부여.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ALIASES_PATH = REPO_ROOT / "configs" / "aliases.yaml"

# NER 라벨 → aliases.yaml 키 매핑
NER_KEY_MAP = {
    "PERSON": "person",
    "ORG": "org",
    "LOCATION": "location",
    "PROJ_N": "proj_n",
}

# 정규식 토큰
REGEX_LABELS = ("PHONE", "EMAIL", "RRN", "CARD", "ACCOUNT", "IP", "API_KEY",
                "PASSPORT", "DRIVER_LICENSE", "BIZ_NUM")


@dataclass
class SessionState:
    """단일 세션의 entity → alias 매핑."""
    # (label, original) → alias
    mapping: Dict[tuple, str] = field(default_factory=dict)
    # 라벨별 다음 풀 index
    ner_cursor: Dict[str, int] = field(default_factory=dict)
    # 정규식 라벨별 다음 순번 (1부터)
    regex_cursor: Dict[str, int] = field(default_factory=lambda: {l: 1 for l in REGEX_LABELS})
    last_access: float = field(default_factory=time.time)


class AliasManager:
    """세션별 alias 매핑 매니저 (thread-safe).

    동작:
      get_alias(session_id, label, original_text) -> alias
        - 같은 (label, original) 이 같은 세션에서 다시 들어오면 같은 alias
        - 새 entity 면 풀에서 다음 alias 할당 (순환)
        - 정규식 라벨은 더미 템플릿에 번호를 채워 반환
    """

    def __init__(self, aliases_path: Path = ALIASES_PATH):
        with open(aliases_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        self._pools: Dict[str, list] = {
            "PERSON": cfg["person"],
            "ORG": cfg["org"],
            "LOCATION": cfg["location"],
            "PROJ_N": cfg["proj_n"],
        }
        self._regex_dummies: Dict[str, str] = cfg["regex_dummies"]
        self._sessions: Dict[str, SessionState] = {}
        self._lock = threading.Lock()

    def get_alias(self, session_id: str, label: str, original: str) -> str:
        key = (label, original)
        with self._lock:
            state = self._sessions.setdefault(session_id, SessionState())
            state.last_access = time.time()
            if key in state.mapping:
                return state.mapping[key]

            if label in REGEX_LABELS:
                template = self._regex_dummies[label]
                idx = state.regex_cursor[label]
                alias = template.format(i=idx)
                state.regex_cursor[label] = idx + 1
            elif label in NER_KEY_MAP:
                pool = self._pools[label]
                cursor = state.ner_cursor.get(label, 0)
                alias = pool[cursor % len(pool)]
                state.ner_cursor[label] = cursor + 1
            else:
                # 알 수 없는 라벨은 placeholder 로 fallback
                alias = f"[{label}]"

            state.mapping[key] = alias
            return alias

    def clear_session(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def gc(self, max_age_seconds: float = 3600.0) -> int:
        """오래된 세션 garbage collection (1시간 이상 미사용)."""
        now = time.time()
        removed = 0
        with self._lock:
            for sid in list(self._sessions.keys()):
                if now - self._sessions[sid].last_access > max_age_seconds:
                    del self._sessions[sid]
                    removed += 1
        return removed

    def stats(self) -> dict:
        with self._lock:
            return {
                "active_sessions": len(self._sessions),
                "total_mappings": sum(len(s.mapping) for s in self._sessions.values()),
            }
