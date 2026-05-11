# PrivacyFilter

한국어 LLM 프롬프트의 민감정보(개인정보·기업기밀)를 실시간으로 탐지·마스킹하는 Chrome 확장 프로그램.

## 개요

ChatGPT / Gemini / Claude 등 외부 LLM 서비스로 프롬프트가 전송되기 직전, 정규식 + NER 모델 2단계로 민감정보를 마스킹 토큰으로 치환한다.

```
[사용자 입력]
   ↓
[1차: 정규식 마스킹]   ← 패턴이 명확한 PII
   ↓
[2차: NER 모델 마스킹]  ← 문맥이 필요한 개체명
   ↓
[LLM 서버로 전송]
```

## 마스킹 토큰 (총 11종)

### 1차 정규식 (패턴 기반)
| 토큰 | 대상 |
|---|---|
| `[RRN]` | 주민등록번호 |
| `[PHONE]` | 휴대폰·일반전화 |
| `[EMAIL]` | 이메일 주소 |
| `[CARD]` | 신용카드 번호 |
| `[ACCOUNT]` | 은행 계좌번호 |
| `[IP]` | IPv4 주소 |
| `[API_KEY]` | API 키·시크릿 토큰 |

### 2차 NER 모델 (문맥 기반)
| 토큰 | 대상 |
|---|---|
| `[PERSON]` | 인명 |
| `[ORG]` | 기관·회사명 |
| `[LOCATION]` | 주소·지명 |
| `[PROJ_N]` | 프로젝트·시스템·사업명 |

## 디렉터리 구조

```
PrivacyFilter/
├── configs/
│   └── label_mapping.yaml      # 데이터셋별 원본 라벨 → 통합 토큰 매핑
├── data/
│   ├── raw/                    # 원본 다운로드 (gitignored)
│   ├── processed/              # BIO 태깅 통합 포맷
│   └── synthetic/              # [PROJ_N] 합성 데이터
├── regex/
│   └── patterns.py             # 1차 정규식 패턴
├── scripts/
│   ├── convert_klue.py         # KLUE-NER → 통합 포맷
│   ├── convert_naver.py        # 네이버+창원대 NER → 통합 포맷
│   ├── convert_nikl.py         # 국립국어원 말뭉치 → 통합 포맷
│   ├── convert_aihub.py        # AI-Hub PII → 통합 포맷
│   ├── generate_proj.py        # [PROJ_N] 합성 데이터 생성
│   └── merge_and_split.py      # 통합 + train/dev/test 분할
├── verification/
│   ├── stats.py                # 라벨 분포·개수 통계
│   ├── bio_check.py            # BIO 태깅 무결성
│   └── conflict_check.py       # 정규식 ↔ NER 충돌 검증
└── requirements.txt
```

## 사용 데이터셋

| 데이터셋 | 출처 | 다운로드 |
|---|---|---|
| KLUE-NER | KLUE Benchmark | HuggingFace `klue/klue` (subset `ner`) |
| 네이버+창원대 NER | NLP Challenge 2018 | https://github.com/naver/nlp-challenge |
| 국립국어원 개체명 말뭉치 | 모두의 말뭉치 | https://corpus.korean.go.kr (신청 필요) |
| AI-Hub 개인정보 비식별화 | AI-Hub | https://aihub.or.kr (신청 필요) |

## 평가 지표

- **마스킹 정확도**: F1-score / Recall (KLUE-NER 벤치마크)
- **응답 품질**: BERTScore (마스킹 전/후 LLM 응답 비교, GPT·Gemini·Claude)
- **처리 지연**: 마스킹 전/후 전송 시간 비교

## 일정

| 주차 | 작업 |
|---|---|
| 9 | 데이터셋 전처리 |
| 9~10 | NER 모델 학습 |
| 10~11 | 마스킹 성능 평가 (F1/Recall), BERTScore 평가 |
| 11~13 | Chrome 확장 프로그램 개발 |
| 13~14 | 처리 지연 시간 평가, 최종 보고서 |
