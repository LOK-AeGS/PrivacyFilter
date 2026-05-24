// 세션별 alias 매핑 관리 — alias_manager.py 의 JS 포팅.
// 같은 세션(=탭) 내 같은 entity 텍스트는 같은 alias 를 받는다.
// 정규식 토큰은 더미 템플릿 + 등장 순번을 부여한다.

import { ALIAS_POOLS, REGEX_DUMMY } from "./aliases.js";

const REGEX_LABELS = new Set(["PHONE", "EMAIL", "RRN", "CARD", "ACCOUNT", "IP", "API_KEY"]);
const NER_LABELS = new Set(["PERSON", "ORG", "LOCATION", "PROJ_N"]);

class SessionState {
  constructor() {
    this.mapping = new Map();      // "label original" -> alias
    this.nerCursor = new Map();    // label -> 다음 풀 index
    this.regexCursor = new Map();  // label -> 다음 순번(1부터)
  }
}

export class AliasManager {
  constructor() {
    this._sessions = new Map(); // sessionId -> SessionState
  }

  _session(sessionId) {
    let s = this._sessions.get(sessionId);
    if (!s) {
      s = new SessionState();
      this._sessions.set(sessionId, s);
    }
    return s;
  }

  /**
   * (label, original) → alias. 같은 세션에서 재등장하면 같은 alias 반환.
   */
  getAlias(sessionId, label, original) {
    const state = this._session(sessionId);
    const key = `${label} ${original}`;
    if (state.mapping.has(key)) return state.mapping.get(key);

    let alias;
    if (REGEX_LABELS.has(label)) {
      const idx = state.regexCursor.get(label) ?? 1;
      alias = REGEX_DUMMY[label](idx);
      state.regexCursor.set(label, idx + 1);
    } else if (NER_LABELS.has(label)) {
      const pool = ALIAS_POOLS[label];
      let cursor = state.nerCursor.get(label) ?? 0;
      // 가명이 원문의 부분문자열(또는 그 반대)이면 복원 시 무한 치환 위험
      // (예: 원문 "서울시 강남구" ⊃ 가명 "서울시") → 충돌 없는 다음 후보 선택.
      let tries = 0;
      do {
        alias = pool[cursor % pool.length];
        cursor += 1;
        tries += 1;
      } while (tries < pool.length && (original.includes(alias) || alias.includes(original)));
      state.nerCursor.set(label, cursor);
    } else {
      alias = `[${label}]`; // 알 수 없는 라벨 fallback
    }

    state.mapping.set(key, alias);
    return alias;
  }

  /**
   * 세션의 모든 (alias, original) 쌍 반환 (unmask 용).
   * key 는 "LABEL original" 형식이라 첫 공백 이후를 original 로 본다.
   */
  getPairs(sessionId) {
    const s = this._sessions.get(sessionId);
    if (!s) return [];
    const pairs = [];
    for (const [key, alias] of s.mapping) {
      const original = key.slice(key.indexOf(" ") + 1);
      if (alias !== original) pairs.push({ alias, original });
    }
    return pairs;
  }

  clearSession(sessionId) {
    if (sessionId === "*") {
      const had = this._sessions.size > 0;
      this._sessions.clear();
      return had;
    }
    return this._sessions.delete(sessionId);
  }

  stats() {
    let total = 0;
    for (const s of this._sessions.values()) total += s.mapping.size;
    return { activeSessions: this._sessions.size, totalMappings: total };
  }
}
