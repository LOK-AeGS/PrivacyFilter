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
├── pii_regex/
│   └── patterns.py             # 1차 정규식 패턴 (디렉터리명: 서드파티 regex 패키지와 충돌 회피)
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

## 데이터셋 빌드 & 학습 워크플로

```bash
# 1) 데이터셋 변환 (KLUE 는 자동 다운로드, 나머지는 data/raw/ 에 사전 배치 필요)
python scripts/convert_klue.py
python scripts/convert_naver.py     # data/raw/naver/train.tsv 필요
python scripts/convert_nikl.py      # data/raw/nikl/*.json 필요
python scripts/convert_aihub.py     # data/raw/aihub/* 필요

# 2) [PROJ_N] 합성 데이터 생성
python scripts/generate_proj.py --n 1500

# 3) 통합 + 분할
python scripts/merge_and_split.py

# 4) 검증
python verification/verify_all.py

# 5) 학습 (klue/bert-base 백본)
python scripts/train_ner.py \
    --train data/processed/train.jsonl \
    --dev   data/processed/dev.jsonl \
    --labels data/processed/label_list.txt \
    --out-dir models/klue_bert_ner \
    --epochs 3 --batch-size 32 --lr 5e-5

# 6) 추론 (정규식 + NER 2단계 마스킹)
python scripts/infer_ner.py --model-dir models/klue_bert_ner \
    --text "내 이름은 김민수, 010-1234-5678."
```

## 1차 학습 결과 (KLUE-BERT-base, CPU)

**설정**
- 백본: `klue/bert-base`
- Train: KLUE 3,000 + 합성 PROJ_N 1,200 = **4,200 문장** (`scripts/stratified_sample.py` 로 균형 추출)
- Dev: 전체 5,150 문장 (KLUE 5,000 + 합성 150)
- Epochs: 3, batch 16, lr 5e-5
- 학습 시간: **26분 22초** (CPU 20코어, ~8 samples/sec)

**Dev F1 (entity-level, seqeval)**
| 라벨 | F1 | Support |
|---|---|---|
| **PROJ_N** | **0.9834** | 148 |
| PERSON | 0.9380 | 4,188 |
| ORG | 0.8235 | 2,032 |
| LOCATION | 0.8039 | 1,513 |
| **micro avg** | **0.8829** | 7,881 |

**균형 학습 효과** — KLUE-편향 3,000 vs balanced 4,200:
| 실험 | 전체 F1 | PROJ_N F1 |
|---|---|---|
| KLUE-biased | 0.870 | **0.000** |
| Balanced | **0.883** | **0.983** |

**End-to-end 마스킹 예시**
```
원문:  안녕하세요. 저는 단국대학교 컴퓨터공학과 김민수입니다.
       차세대 인사관리시스템 프로젝트의 PM을 맡고 있고, 사무실은 서울 강남구입니다.
       문의는 010-1234-5678 또는 minsu@example.com 으로 주세요.

마스킹: 안녕하세요. 저는 [ORG] 컴퓨터공학과 [PERSON]입니다.
       [PROJ_N]의 PM을 맡고 있고, 사무실은 [LOCATION]입니다.
       문의는 [PHONE] 또는 [EMAIL] 으로 주세요.
```

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
