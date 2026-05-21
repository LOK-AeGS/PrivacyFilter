// 1차 마스킹: 패턴이 명확한 한국어 PII 정규식.
// pii_regex/patterns.py 의 JS 포팅. 우선순위는 PATTERN_ORDER 순서를 따른다.
//
// Python → JS 주의점:
//  - (?<!\d) 룩비하인드: Chrome(V8) 지원.
//  - (?i) 인라인 플래그 미지원 → EMAIL 은 'i' 플래그로 컴파일.
//  - finditer → 'g' 플래그 + matchAll.

// 주민등록번호: YYMMDD-NNNNNNN (구분자 -, 공백, 또는 없음)
const RRN = /(?<!\d)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[-\s]?[1-8]\d{6}(?!\d)/g;

// 신용카드: 4자리씩 4그룹 (총 16자리)
const CARD = /(?<!\d)\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}(?!\d)/g;

// 계좌번호: 3~6 - 2~6 - 2~8 (3그룹). 보수적으로 캡처.
const ACCOUNT = /(?<!\d)\d{3,6}-\d{2,6}-\d{2,8}(?!\d)/g;

// 전화번호: 휴대폰 / 지역번호 / 1588-XXXX 류
const PHONE = /(?<!\d)(?:01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}|0(?:2|[3-6][1-5]|70)[-.\s]?\d{3,4}[-.\s]?\d{4}|1[5-9]\d{2}[-.\s]?\d{4})(?!\d)/g;

// 이메일: RFC 간이 버전
const EMAIL = /\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b/gi;

// IPv4: 0~255 검증 포함
const IP = /(?<!\d)(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?!\d)/g;

// API 키 / 시크릿 토큰: 주요 벤더별 prefix 기반
const API_KEY = /(?:sk-(?:proj-)?[A-Za-z0-9_\-]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{60,}|gho_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{35}|xox[abpr]-[A-Za-z0-9\-]{10,}|sk_(?:live|test)_[A-Za-z0-9]{20,})/g;

// 우선순위 리스트 (긴 자릿수 패턴이 위, ACCOUNT 는 느슨해서 마지막)
const REGEX_PATTERNS = [
  ["RRN", RRN],
  ["CARD", CARD],
  ["PHONE", PHONE],
  ["EMAIL", EMAIL],
  ["IP", IP],
  ["API_KEY", API_KEY],
  ["ACCOUNT", ACCOUNT],
];

export const REGEX_TOKENS = REGEX_PATTERNS.map(([t]) => t);

const PRIORITY = Object.fromEntries(REGEX_PATTERNS.map(([t], i) => [t, i]));

/**
 * 텍스트에서 모든 정규식 매치를 찾아 {start,end,token,text} 로 반환.
 * 겹치면 더 긴 매치 우선, 길이 같으면 우선순위 리스트 순서.
 */
export function findRegexSpans(text) {
  const candidates = [];
  for (const [token, pattern] of REGEX_PATTERNS) {
    pattern.lastIndex = 0; // 'g' 정규식 재사용 시 상태 초기화
    for (const m of text.matchAll(pattern)) {
      candidates.push({ start: m.index, end: m.index + m[0].length, token, text: m[0] });
    }
  }

  // 더 긴 span 우선, 같으면 등록 순서, 그 다음 start
  candidates.sort((a, b) => {
    const la = a.end - a.start;
    const lb = b.end - b.start;
    if (la !== lb) return lb - la;
    if (PRIORITY[a.token] !== PRIORITY[b.token]) return PRIORITY[a.token] - PRIORITY[b.token];
    return a.start - b.start;
  });

  const selected = [];
  const occupied = [];
  for (const span of candidates) {
    const overlap = occupied.some(([s, e]) => !(span.end <= s || span.start >= e));
    if (overlap) continue;
    selected.push(span);
    occupied.push([span.start, span.end]);
  }

  selected.sort((a, b) => a.start - b.start);
  return selected;
}
