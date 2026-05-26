// 마스킹/복원 서비스 — server/mask_service.py 의 JS 포팅.
//
// 흐름 (mask):
//   1. 정규식 1차 스팬 수집 (pii_regex)
//   2. NER 2차 스팬 수집 (Transformers.js 추론 → BIO 병합 + 문자 offset)
//   3. 스팬 머지 (정규식 우선, 겹치는 NER 제거)
//   4. AliasManager 로 alias 할당 (세션 일관성)
//   5. 텍스트 치환
//
// 흐름 (unmask):
//   각 alias 를 original 로 치환 (긴 alias 부터 처리해 부분 매치 회피).
//
// 토크나이저/모델은 생성자에 주입한다 (Node 테스트·브라우저 공용).

import { findRegexSpans } from "./pii_regex.js";

export class MaskService {
  /**
   * @param {object} opts
   * @param {object} opts.tokenizer  Transformers.js PreTrainedTokenizer
   * @param {object} opts.model      Transformers.js TokenClassification 모델
   * @param {object} opts.aliasManager  AliasManager 인스턴스
   */
  constructor({ tokenizer, model, aliasManager }) {
    this.tokenizer = tokenizer;
    this.model = model;
    this.aliasManager = aliasManager;
    this.id2label = model.config.id2label;
  }

  // ── WordPiece 토큰 → 원문 문자 offset 재구성 ──
  // 각 토큰 surface(앞 ## 제거)를 cursor 이후에서 찾아 [start,end) 부여.
  static alignOffsets(text, tokens) {
    const offsets = [];
    let cursor = 0;
    for (const t of tokens) {
      if (t === "[CLS]" || t === "[SEP]" || t === "[PAD]" || t === "[UNK]") {
        offsets.push(null);
        continue;
      }
      const surface = t.startsWith("##") ? t.slice(2) : t;
      const idx = text.indexOf(surface, cursor);
      if (idx === -1) { offsets.push(null); continue; }
      offsets.push([idx, idx + surface.length]);
      cursor = idx + surface.length;
    }
    return offsets;
  }

  // ── BIO 라벨열 → 엔티티 스팬 병합 ──
  // 확장 조건: 같은 라벨 AND (gap==0 [서브워드 연속] OR 현재 토큰이 I- [공백 넘는 연속]).
  // → 모델이 서브워드를 B- 로 잘못 찍어도(예: 단국/##대) 병합되고,
  //   서로 다른 엔티티(박지성과 손흥민)는 분리된다.
  static nerSpansFromLabels(text, tokens, labelIds, offsets, id2label) {
    const spans = [];
    let cur = null;
    for (let i = 0; i < tokens.length; i++) {
      const off = offsets[i];
      const label = id2label[labelIds[i]];
      if (!off || label === "O") {
        if (cur) { spans.push(cur); cur = null; }
        continue;
      }
      const [s, e] = off;
      const bio = label[0];        // B / I
      const ent = label.slice(2);  // PERSON ...
      if (cur && cur.label === ent && (bio === "I" || s === cur.end)) {
        cur.end = e; // 연속 → 확장
      } else {
        if (cur) spans.push(cur);
        cur = { start: s, end: e, label: ent };
      }
    }
    if (cur) spans.push(cur);
    return spans.map((sp) => ({ ...sp, text: text.slice(sp.start, sp.end) }));
  }

  // 모델 한도: RoBERTa max_position_embeddings=514 → 사용 가능 512 토큰.
  static MAX_MODEL_TOKENS = 512;   // 이하면 단일 추론(기존 경로)
  static CHUNK_TOKENS = 480;       // 초과 시 청크당 목표 토큰(경계 여유 포함)

  // 특수토큰([CLS]/[SEP]) 제외 토큰 수
  async _tokenCount(s) {
    if (!s) return 0;
    return (await this.tokenizer(s)).input_ids.data.length - 2;
  }

  // 기관 접미사 / 고정밀 행정구역 사전 — 모델이 놓친 ORG/LOC 재현율 보강.
  static GAZETTEER = [
    // 고정밀 기관 접미사만 (FP 큰 대학·의원·그룹·증권·연구원 제외)
    [/[가-힣A-Za-z0-9]{2,}\s?(?:대학교|주식회사|병원|은행|연구소)/g, "ORG"],
    [/(?:㈜|\(주\))\s?[가-힣A-Za-z0-9]{2,}|[가-힣A-Za-z0-9]{2,}\s?(?:㈜|\(주\))/g, "ORG"],
    [/[가-힣]{2,}(?:특별자치시|특별자치도|특별시|광역시)/g, "LOCATION"],
  ];

  // 사전 기반 ORG/LOC 스팬 (내부 중복은 긴 것 우선으로 제거)
  static gazetteerSpans(text) {
    const spans = [];
    for (const [re, label] of MaskService.GAZETTEER) {
      re.lastIndex = 0;
      for (const m of text.matchAll(re)) {
        spans.push({ start: m.index, end: m.index + m[0].length, label, text: m[0] });
      }
    }
    spans.sort((a, b) => (b.end - b.start) - (a.end - a.start));
    const out = [];
    for (const s of spans) {
      if (!out.some((o) => !(s.end <= o.start || s.start >= o.end))) out.push(s);
    }
    return out;
  }

  // ── NER 추론: 모델 스팬 + 가제티어 보강 병합 (겹치면 모델 우선) ──
  async nerSpans(text) {
    const merged = await this._modelSpans(text);
    for (const g of MaskService.gazetteerSpans(text)) {
      if (!merged.some((s) => !(g.end <= s.start || g.start >= s.end))) merged.push(g);
    }
    return merged;
  }

  // 모델 추론. 512토큰 초과 입력은 문장 경계로 청킹.
  async _modelSpans(text) {
    const enc = await this.tokenizer(text);
    const ids = Array.from(enc.input_ids.data).map(Number);
    if (ids.length <= MaskService.MAX_MODEL_TOKENS) {
      return this._runNer(text, enc, ids);  // 일반 경로 — 추가 비용 없음
    }
    // 장문: 청크별 NER 후 오프셋 보정 병합
    const all = [];
    for (const { text: ct, offset } of await this._chunk(text)) {
      const cenc = await this.tokenizer(ct);
      const cids = Array.from(cenc.input_ids.data).map(Number);
      for (const sp of await this._runNer(ct, cenc, cids)) {
        all.push({ start: sp.start + offset, end: sp.end + offset, label: sp.label, text: sp.text });
      }
    }
    return all;
  }

  // 토큰화·모델 추론·BIO 병합 (이미 토큰화된 enc/ids 재사용)
  async _runNer(text, enc, ids) {
    const tokens = this.tokenizer.model.convert_ids_to_tokens(ids);
    const offsets = MaskService.alignOffsets(text, tokens);

    const out = await this.model(enc);
    const logits = out.logits;          // [1, seq, num_labels]
    const [, seq, nl] = logits.dims;
    const data = logits.data;
    const labelIds = new Array(seq);
    for (let i = 0; i < seq; i++) {
      let best = 0, bestv = -Infinity;
      const base = i * nl;
      for (let j = 0; j < nl; j++) {
        const v = data[base + j];
        if (v > bestv) { bestv = v; best = j; }
      }
      labelIds[i] = best;
    }
    return MaskService.nerSpansFromLabels(text, tokens, labelIds, offsets, this.id2label);
  }

  // ── 문장 경계 기준 청킹. 각 청크 토큰 수 ≤ CHUNK_TOKENS, 원문 오프셋 보존 ──
  // 엔티티는 문장을 넘지 않으므로 문장 경계 분할은 엔티티를 쪼개지 않는다.
  // 한 문장이 한도를 넘으면 공백 → 글자 순으로 더 쪼개 어떤 입력도 한도 초과 없게 한다.
  async _chunk(text) {
    const fine = []; // {text, n}
    for (const seg of text.split(/(?<=[.!?。．…\n])/)) {
      if (!seg) continue;
      const n = await this._tokenCount(seg);
      if (n <= MaskService.CHUNK_TOKENS) { fine.push({ text: seg, n }); continue; }
      for (const w of seg.split(/(?<=\s)/)) {
        if (!w) continue;
        const wn = await this._tokenCount(w);
        if (wn <= MaskService.CHUNK_TOKENS) { fine.push({ text: w, n: wn }); continue; }
        for (let i = 0; i < w.length; i += 200) {       // 공백 없는 초장문(드묾)
          const piece = w.slice(i, i + 200);
          fine.push({ text: piece, n: await this._tokenCount(piece) });
        }
      }
    }
    const chunks = [];
    let buf = "", bufOff = 0, bufTok = 0, off = 0;
    for (const { text: seg, n } of fine) {
      const segOff = off; off += seg.length;
      if (buf && bufTok + n > MaskService.CHUNK_TOKENS) {
        chunks.push({ text: buf, offset: bufOff }); buf = ""; bufTok = 0;
      }
      if (!buf) bufOff = segOff;
      buf += seg; bufTok += n;
    }
    if (buf) chunks.push({ text: buf, offset: bufOff });
    return chunks;
  }

  // ── regex 우선 머지. 겹치는 NER 스팬 제거 ──
  static mergeRegexAndNer(text, regexSpans, nerSpans) {
    const merged = regexSpans.map((s) => ({
      start: s.start, end: s.end, label: s.token, original: s.text, src: "regex",
    }));
    const occupied = merged.map((m) => [m.start, m.end]);
    for (const ns of nerSpans) {
      const overlap = occupied.some(([a, b]) => !(ns.end <= a || ns.start >= b));
      if (overlap) continue;
      merged.push({ start: ns.start, end: ns.end, label: ns.label, original: ns.text, src: "ner" });
      occupied.push([ns.start, ns.end]);
    }
    merged.sort((a, b) => a.start - b.start);
    return merged;
  }

  /**
   * @returns {Promise<{maskedText:string, spans:Array, latency:object}>}
   */
  async mask(text, sessionId = "default") {
    const t0 = performance.now();
    const regexRaw = findRegexSpans(text);
    const t1 = performance.now();
    const ner = await this.nerSpans(text);
    const t2 = performance.now();

    const mergedRaw = MaskService.mergeRegexAndNer(text, regexRaw, ner);

    const spans = mergedRaw.map((m) => ({
      ...m,
      alias: this.aliasManager.getAlias(sessionId, m.label, m.original),
    }));

    // 텍스트 치환 (스팬은 start 오름차순)
    const parts = [];
    let cursor = 0;
    for (const sp of spans) {
      parts.push(text.slice(cursor, sp.start));
      parts.push(sp.alias);
      cursor = sp.end;
    }
    parts.push(text.slice(cursor));
    const maskedText = parts.join("");
    const t3 = performance.now();

    return {
      maskedText,
      spans,
      latency: {
        regex_ms: Math.round(t1 - t0),
        ner_ms: Math.round(t2 - t1),
        merge_replace_ms: Math.round(t3 - t2),
        total_ms: Math.round(t3 - t0),
      },
    };
  }

  // ── LLM 응답에서 alias → original 복원 ──
  // 긴 alias 부터 치환해 부분 매치 회피.
  static unmask(text, spans) {
    if (!spans || spans.length === 0) return text;
    const seen = new Set();
    const pairs = [];
    for (const sp of spans) {
      const k = sp.alias + " " + sp.original;
      if (seen.has(k)) continue;
      seen.add(k);
      if (sp.alias && sp.alias !== sp.original) pairs.push([sp.alias, sp.original]);
    }
    pairs.sort((a, b) => b[0].length - a[0].length);
    let out = text;
    for (const [alias, original] of pairs) {
      out = out.split(alias).join(original);
    }
    return out;
  }
}
