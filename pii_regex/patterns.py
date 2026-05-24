"""1차 마스킹: 패턴이 명확한 한국어 PII 정규식.

각 패턴은 (token, compiled_regex) 튜플 리스트로 관리되며, 우선순위는 리스트 순서를 따른다.
긴 매치를 먼저 잡도록 RRN/CARD/PHONE 같은 자릿수 큰 패턴을 상위에 둔다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

REGEX_TOKENS: Tuple[str, ...] = (
    "RRN",
    "CARD",
    "DRIVER_LICENSE",
    "BIZ_NUM",
    "PASSPORT",
    "PHONE",
    "EMAIL",
    "IP",
    "API_KEY",
    "ACCOUNT",
)


# 주민등록번호: YYMMDD-NNNNNNN (구분자 -, 공백, 또는 없음)
# 월(01-12), 일(01-31), 성별코드 1-8 검사
_RRN = re.compile(
    r"(?<!\d)"
    r"\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])"
    r"[-\s]?"
    r"[1-8]\d{6}"
    r"(?!\d)"
)

# 신용카드: 4자리씩 4그룹, 구분자 -, 공백, 또는 없음 (총 16자리)
_CARD = re.compile(
    r"(?<!\d)"
    r"\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}"
    r"(?!\d)"
)

# 계좌번호: 은행마다 포맷이 달라 보수적으로 캡처.
# 형식: 3~6자리 - 2~6자리 - 2~8자리 (3그룹)
# 또는: 6~14자리 연속 숫자 + '계좌', '입금', '계좌번호' 키워드 인접 (오탐 줄이기 위해 그룹 패턴만 사용)
_ACCOUNT = re.compile(
    r"(?<!\d)"
    r"\d{3,6}-\d{2,6}-\d{2,8}"
    r"(?!\d)"
)

# 전화번호:
#   - 휴대폰: 010|011|016|017|018|019 - 3~4자리 - 4자리
#   - 지역번호: 02 또는 0XX(3자리) - 3~4자리 - 4자리
#   - 대표/특수: 15XX-XXXX, 16XX-XXXX, 18XX-XXXX
_PHONE = re.compile(
    r"(?<!\d)"
    r"(?:"
    r"01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}"          # 휴대폰
    r"|0(?:2|[3-6][1-5]|70)[-.\s]?\d{3,4}[-.\s]?\d{4}"  # 지역번호
    r"|1[5-9]\d{2}[-.\s]?\d{4}"                       # 1588-XXXX 류
    r")"
    r"(?!\d)"
)

# 이메일: RFC 간이 버전
_EMAIL = re.compile(
    r"(?i)\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b"
)

# IPv4: 0~255 검증 포함
_IP = re.compile(
    r"(?<!\d)"
    r"(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
    r"(?!\d)"
)

# API 키 / 시크릿 토큰: 주요 벤더별 prefix + JWT
_API_KEY = re.compile(
    r"(?:"
    r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}"          # OpenAI
    r"|ghp_[A-Za-z0-9]{30,}"                      # GitHub Personal Access Token
    r"|github_pat_[A-Za-z0-9_]{60,}"              # GitHub fine-grained PAT
    r"|gho_[A-Za-z0-9]{30,}"                      # GitHub OAuth
    r"|AKIA[0-9A-Z]{16}"                          # AWS Access Key ID
    r"|ASIA[0-9A-Z]{16}"                          # AWS STS
    r"|AIza[0-9A-Za-z_\-]{35}"                    # Google API Key
    r"|xox[abpr]-[A-Za-z0-9\-]{10,}"              # Slack token
    r"|sk_(?:live|test)_[A-Za-z0-9]{20,}"         # Stripe
    r"|eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"  # JWT
    r")"
)

# 여권번호: 영문 1자(M/S/R/G/D 등) + 숫자 8자
_PASSPORT = re.compile(r"(?<![A-Za-z0-9])[MSRGDOP]\d{8}(?![A-Za-z0-9])")

# 운전면허번호: 2-2-6-2 (예: 11-22-333333-44)
_DRIVER_LICENSE = re.compile(r"(?<!\d)\d{2}-\d{2}-\d{6}-\d{2}(?!\d)")

# 사업자등록번호: 3-2-5 (예: 123-45-67890)
_BIZ_NUM = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{5}(?!\d)")


REGEX_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("RRN", _RRN),
    ("CARD", _CARD),
    ("DRIVER_LICENSE", _DRIVER_LICENSE),
    ("BIZ_NUM", _BIZ_NUM),
    ("PASSPORT", _PASSPORT),
    ("PHONE", _PHONE),
    ("EMAIL", _EMAIL),
    ("IP", _IP),
    ("API_KEY", _API_KEY),
    # ACCOUNT는 가장 마지막. 자릿수 패턴이 느슨해서 PHONE/CARD/BIZ_NUM 와 충돌할 수 있어
    # 위 패턴들이 먼저 잡고 남은 영역에서만 매치되도록 우선순위를 낮춤.
    ("ACCOUNT", _ACCOUNT),
]


@dataclass
class RegexSpan:
    start: int
    end: int
    token: str
    text: str


def find_regex_spans(text: str) -> List[RegexSpan]:
    """텍스트에서 모든 정규식 매치를 찾아 (시작, 끝, 토큰, 원문) 으로 반환.

    중복 매치가 있을 경우 더 긴 매치를 우선하고, 길이가 같으면 우선순위 리스트
    순서를 따른다.
    """
    candidates: List[RegexSpan] = []
    for token, pattern in REGEX_PATTERNS:
        for m in pattern.finditer(text):
            candidates.append(RegexSpan(m.start(), m.end(), token, m.group(0)))

    # 더 긴 span 우선, 같은 길이면 등록 순서(낮은 인덱스) 우선
    priority = {tok: i for i, (tok, _) in enumerate(REGEX_PATTERNS)}
    candidates.sort(key=lambda s: (-(s.end - s.start), priority[s.token], s.start))

    selected: List[RegexSpan] = []
    occupied: List[Tuple[int, int]] = []
    for span in candidates:
        if any(not (span.end <= s or span.start >= e) for s, e in occupied):
            continue
        selected.append(span)
        occupied.append((span.start, span.end))

    selected.sort(key=lambda s: s.start)
    return selected


def apply_regex_masking(text: str) -> Tuple[str, List[RegexSpan]]:
    """텍스트에 1차 마스킹을 적용하고, 마스킹된 텍스트와 적용된 span 리스트를 반환."""
    spans = find_regex_spans(text)
    if not spans:
        return text, []

    out_parts: List[str] = []
    cursor = 0
    for span in spans:
        out_parts.append(text[cursor : span.start])
        out_parts.append(f"[{span.token}]")
        cursor = span.end
    out_parts.append(text[cursor:])
    return "".join(out_parts), spans


# ---------------------------------------------------------------------------
# 개발용 스모크 테스트
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    samples = [
        ("주민등록번호 021227-3456789 입니다.", "RRN"),
        ("내 번호는 010-1234-5678 이야.", "PHONE"),
        ("문의: 02-3456-7890 으로 연락주세요.", "PHONE"),
        ("고객센터 1588-1234 입니다.", "PHONE"),
        ("이메일: staran1227@dankook.ac.kr", "EMAIL"),
        ("카드번호 1234-5678-9012-3456 를 등록", "CARD"),
        ("계좌 110-123-456789 로 입금", "ACCOUNT"),
        ("서버 IP 192.168.0.1 접근", "IP"),
        ("OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz0123456789", "API_KEY"),
        ("AWS키 AKIAIOSFODNN7EXAMPLE 노출", "API_KEY"),
        ("여권번호 M12345678 확인", "PASSPORT"),
        ("운전면허 11-22-333333-44 갱신", "DRIVER_LICENSE"),
        ("사업자등록번호 123-45-67890 입니다", "BIZ_NUM"),
        ("토큰 eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N", "API_KEY"),
        ("그냥 평범한 문장입니다.", None),
    ]
    print(f"{'expected':<10} | {'masked':<6} | result")
    print("-" * 80)
    for text, expected in samples:
        masked, spans = apply_regex_masking(text)
        got = spans[0].token if spans else None
        ok = "OK" if got == expected else "FAIL"
        print(f"{str(expected):<10} | {str(got):<6} | [{ok}] {masked}")
