"""발표 데모용 — 다양한 시나리오 입력에 마스킹 결과 일괄 생성.

모델을 한 번만 로드하고 여러 텍스트 처리.

실행:
    python scripts/demo_examples.py --model-dir models/klue_roberta_large_iter6
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pii_regex.patterns import find_regex_spans  # noqa: E402


@dataclass
class Span:
    start: int
    end: int
    token: str
    text: str
    src: str


SCENARIOS = [
    {
        "name": "학생 자기소개",
        "text": "안녕하세요, 저는 단국대학교 컴퓨터공학과 4학년 안균승입니다. 학번은 32212430이고, 이메일은 staran1227@dankook.ac.kr 입니다. 휴대폰은 010-1234-5678 이고, 사무실은 경기 용인시에 있습니다.",
    },
    {
        "name": "회사 업무 보고",
        "text": "삼성전자 DX부문의 김민수 책임이 오늘 오전 차세대 ERP 시스템 도입 프로젝트의 진행 상황을 발표했습니다. 회의는 서울 강남구 본사에서 진행됐고, 협력사인 LG CNS의 박서준 이사도 참석했습니다.",
    },
    {
        "name": "의료 상담 문의",
        "text": "안녕하세요, 환자 이름은 정유진이고 주민등록번호는 021227-2345678 입니다. 단국대학교병원에서 진료받았는데 청구서를 다시 받고 싶어요. 연락처는 02-3456-7890 또는 yujin@example.com 으로 부탁드립니다.",
    },
    {
        "name": "금융 거래 문의",
        "text": "고객센터에 문의합니다. 제 이름은 최도현이고, 신용카드번호 1234-5678-9012-3456 으로 결제한 내역이 잘못 청구된 것 같아요. 환불을 위해 국민은행 110-123-456789 계좌로 보내주세요. 카카오뱅크 앱에서도 확인했습니다.",
    },
    {
        "name": "개발 환경 코드 리뷰",
        "text": "안녕하세요, 한지원 연구원입니다. AI 챗봇 도입 사업의 백엔드 코드 리뷰 부탁드려요. 서버 IP는 192.168.0.42 이고, OpenAI API 키는 sk-proj-abcdefghijklmnopqrstuvwxyz0123456789 입니다. AWS 키는 AKIAIOSFODNN7EXAMPLE 이에요.",
    },
    {
        "name": "보안 사고 신고",
        "text": "보안팀에 사고를 신고합니다. 강태우 매니저의 노트북이 분실됐고, 그 안에 카카오의 옴니채널 통합 프로젝트 자료와 임직원 명단(주민번호 포함)이 들어있었습니다. 분실 위치는 부산 해운대구입니다. 추가 문의는 010-9876-5432.",
    },
    {
        "name": "캐주얼 대화 (마스킹 거의 없어야 함)",
        "text": "프로젝트 관리 방법론에 대해 알려줘. 애자일과 워터폴의 차이가 뭐야? 그리고 PMP 자격증 따려면 어떻게 해야 해?",
    },
]


def collect_ner_spans(text: str, pipe):
    """HuggingFace pipeline 의 aggregation_strategy='simple' 결과를 그대로 사용."""
    spans: List[Span] = []
    for e in pipe(text):
        spans.append(
            Span(
                start=int(e["start"]),
                end=int(e["end"]),
                token=e["entity_group"],
                text=text[int(e["start"]):int(e["end"])],
                src="ner",
            )
        )
    return spans


def merge_adjacent_same_label(spans: List[Span], max_gap: int = 1) -> List[Span]:
    """인접한 같은 라벨의 spans 를 합침. sub-word 분리 후처리."""
    if not spans:
        return spans
    spans = sorted(spans, key=lambda s: s.start)
    merged = [spans[0]]
    for s in spans[1:]:
        last = merged[-1]
        if s.token == last.token and (s.start - last.end) <= max_gap and s.src == last.src:
            merged[-1] = Span(last.start, s.end, last.token, last.text + s.text, last.src)
        else:
            merged.append(s)
    return merged


def merge_spans(regex_spans: List[Span], ner_spans: List[Span]) -> List[Span]:
    merged: List[Span] = list(regex_spans)
    occupied: List[Tuple[int, int]] = [(s.start, s.end) for s in regex_spans]
    for s in ner_spans:
        if any(not (s.end <= a or s.start >= b) for a, b in occupied):
            continue
        merged.append(s)
        occupied.append((s.start, s.end))
    merged.sort(key=lambda s: s.start)
    return merged


def apply_masking(text: str, spans: List[Span]) -> str:
    out: List[str] = []
    cursor = 0
    for s in spans:
        out.append(text[cursor : s.start])
        out.append(f"[{s.token}]")
        cursor = s.end
    out.append(text[cursor:])
    return "".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    args = parser.parse_args()

    print(f"모델 로딩 중: {args.model_dir}")
    from transformers import pipeline
    pipe = pipeline(
        "token-classification",
        model=args.model_dir,
        tokenizer=args.model_dir,
        aggregation_strategy="simple",
    )
    print("로딩 완료\n")

    print("=" * 75)
    print("PrivacyFilter 데모 — 다양한 시나리오 실제 결과")
    print("=" * 75)

    for i, sc in enumerate(SCENARIOS, 1):
        text = sc["text"]
        # 1차 정규식
        regex_raw = find_regex_spans(text)
        regex_spans = [Span(s.start, s.end, s.token, s.text, "regex") for s in regex_raw]
        # 2차 NER
        ner_spans = collect_ner_spans(text, pipe)
        ner_spans = merge_adjacent_same_label(ner_spans)
        # 머지
        merged = merge_spans(regex_spans, ner_spans)
        masked = apply_masking(text, merged)

        print(f"\n[{i}] {sc['name']}")
        print(f"입력 : {text}")
        print(f"출력 : {masked}")
        print("적용 스팬:")
        for s in merged:
            tag = f"[{s.src:5}]"
            print(f"  {tag} [{s.token:8}] '{s.text}'")


if __name__ == "__main__":
    main()
