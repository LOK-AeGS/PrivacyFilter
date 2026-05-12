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
│   ├── datasets.yaml             # ⭐ 데이터셋 레지스트리 (선언적)
│   └── label_mapping.yaml        # 데이터셋별 라벨 → 통합 토큰 매핑
├── data/
│   ├── raw/                      # 원본 다운로드 (gitignored)
│   ├── processed/                # 빌드 산출물 (train/dev/test/label_list/manifest)
│   └── synthetic/                # [PROJ_N] 합성 데이터 (템플릿, 사전)
├── pii_regex/
│   └── patterns.py               # 1차 정규식 (※ 디렉터리명 — 서드파티 regex 패키지 회피)
├── scripts/
│   ├── build_dataset.py          # ⭐ 데이터셋 통합·빌드 메인 엔트리
│   ├── filters/                  # ⭐ Plug-and-play 필터
│   │   ├── quality.py            # URL/특수문자/길이/조사 정리
│   │   └── label.py              # 라벨 노이즈 정제 (배치/per-record)
│   ├── convert_*.py              # 데이터셋별 컨버터
│   ├── generate_proj.py          # PROJ_N 합성 생성
│   ├── stratified_sample.py      # 소스별 표본 추출
│   ├── augment_entity.py         # 엔티티 치환 증강 (실험적, 효과 작음)
│   ├── clean_label_noise.py      # 단독 노이즈 정제 (build_dataset 외부에서 사용)
│   ├── train_ner.py              # HuggingFace 기반 NER 학습
│   ├── eval_ner.py               # 학습된 모델 평가
│   ├── ensemble_eval.py          # 다중 모델 로짓 평균 앙상블
│   ├── error_analysis.py         # 라벨별 오류 카테고리 분류
│   ├── task_eval.py              # entity-F1 / token-F1 / mask-coverage 3중 평가
│   └── infer_ner.py              # 정규식 + NER 2단계 마스킹 데모
├── verification/
│   ├── stats.py                  # 라벨 분포·개수
│   ├── bio_check.py              # BIO 무결성
│   ├── conflict_check.py         # 정규식 ↔ NER 충돌
│   ├── verify_all.py             # 일괄 검증
│   ├── data_quality_check.py     # 데이터 품질 6기준 감사
│   ├── hypothesis_check.py       # 모델 저성능 가설 검증
│   └── category_mapping_check.py # 통합 데이터 카테고리 매핑 검증
├── results/                      # 실험 결과 문서
└── requirements.txt
```

## 데이터셋 추가 — 선언적 워크플로

본 repo 는 `configs/datasets.yaml` 기반의 **선언적 데이터셋 빌드** 구조를 제공한다.
새 데이터셋(예: KMOU, KoBEST 등)을 추가하려면 4단계만:

### 1. 컨버터 작성 (`scripts/convert_<NAME>.py`)
- 원본 → 통합 JSONL 포맷 `{"tokens": [...], "tags": ["B-X", "I-X", "O", ...], "source": "<NAME>"}`
- 어절 단위 BIO. 기존 컨버터 (`convert_klue.py`, `convert_naver.py`) 참고.

### 2. 라벨 매핑 추가 (`configs/label_mapping.yaml`)
```yaml
my_new_source:
  ORIGINAL_PERSON_LABEL: PERSON
  ORIGINAL_ORG_LABEL: ORG
  # 매핑 안 된 라벨은 자동으로 O
```

### 3. 데이터셋 레지스트리 등록 (`configs/datasets.yaml`)
```yaml
sources:
  my_new_source:
    enabled: true
    converter: scripts/convert_my_new_source.py
    single_file: data/processed/my_new_source.jsonl
    split_ratios: { train: 0.8, dev: 0.1, test: 0.1 }
    filters:
      - drop_url_entities
      - drop_excessive_special_chars
    weight: 1
```

### 4. 빌드 실행
```bash
python scripts/convert_my_new_source.py       # raw → JSONL
python scripts/build_dataset.py               # 통합 → train/dev/test
python verification/category_mapping_check.py # 검증
```

`build_dataset.py` 가 자동으로:
- 각 source 의 변환된 파일 로드
- 선언된 필터 체인 적용 (per-source)
- split_ratios / 사전분할 정책에 따라 train/dev/test 분배
- 라벨 노이즈 정제 (train 만, dev/test 보존)
- 최종 산출 + manifest.json 생성

### 필터 추가
`scripts/filters/quality.py` 또는 `label.py` 에 함수 작성 → `scripts/filters/__init__.py` 의 `FILTERS` dict 에 이름 등록 → `datasets.yaml` 에서 참조.

## 사용 데이터셋

| 데이터셋 | 출처 | 다운로드 | 사용 |
|---|---|---|---|
| KLUE-NER | KLUE Benchmark | HuggingFace `klue/klue` | ✅ |
| 네이버+창원대 NER | NLP Challenge 2018 | https://github.com/naver/nlp-challenge | ✅ |
| 국립국어원 개체명 말뭉치 | 모두의 말뭉치 | https://corpus.korean.go.kr (신청 필요) | ⏳ 옵션 |
| AI-Hub 개인정보 비식별화 | AI-Hub | https://aihub.or.kr (신청 필요) | ⏳ 옵션 |

`data/raw/README.md` 에 각 데이터셋별 신청·다운로드 가이드 있음.

## 빠른 시작

```bash
# 1) 의존성 설치
pip install -r requirements.txt

# 2) 원본 데이터 준비 (KLUE 는 자동, 나머지는 data/raw/README.md 참고)
python scripts/convert_klue.py
python scripts/convert_naver.py
python scripts/generate_proj.py --n 3500

# 3) 통합 데이터셋 빌드 (configs/datasets.yaml 기반)
python scripts/build_dataset.py

# 4) 검증
python verification/verify_all.py
python verification/data_quality_check.py
python verification/category_mapping_check.py

# 5) 학습
python scripts/train_ner.py \
    --train data/processed/train.jsonl \
    --dev   data/processed/dev.jsonl \
    --epochs 2 --batch-size 16 --lr 2e-5 \
    --model klue/roberta-large \
    --out-dir models/my_model

# 6) 평가 (entity-F1 / token-F1 / mask-coverage)
python scripts/task_eval.py --model-dir models/my_model \
    --data data/processed/dev.jsonl

# 7) 추론 데모
python scripts/infer_ner.py --model-dir models/my_model \
    --text "내 이름은 김민수, 010-1234-5678 으로 연락주세요."
```

## 학습 결과

자세한 실험 기록은 [`results/`](results/) 참조.

### 최종 baseline (RoBERTa-large, 단일 모델)
| 라벨 | entity-F1 | token-F1 | mask-cov |
|---|---:|---:|---:|
| PROJ_N | 0.999 | 1.000 | 1.000 |
| PERSON | 0.961 | 0.976 | 0.972 |
| ORG | 0.870 | 0.906 | 0.875 |
| LOCATION | 0.862 | 0.942 | 0.921 |
| **micro** | **0.921** | — | — |

### Iteration 비교 (entity-F1)
| Iter | 구성 | F1 | ORG | LOC |
|---|---|---:|---:|---:|
| 1 | BERT-base 2ep | 0.910 | 0.861 | 0.842 |
| 2 | RoBERTa-base 3ep | 0.916 | 0.870 | 0.850 |
| 3 | + 엔티티 증강 (실패) | 0.908 ↓ | 0.852 | 0.838 |
| 4 | Ensemble BERT+RoBERTa | 0.917 | 0.869 | 0.852 |
| 5 | warm-start +3ep (plateau) | 0.911 | 0.860 | 0.845 |
| 6 | **RoBERTa-large 2ep** | **0.921** | 0.870 | 0.862 |

자세한 분석:
- [`results/FINAL_ANALYSIS.md`](results/FINAL_ANALYSIS.md) — 6 iteration 종합
- [`results/data_audit_and_hypothesis.md`](results/data_audit_and_hypothesis.md) — 데이터 품질·가설 검증

## 평가 지표

- **마스킹 정확도**: entity-F1 (seqeval, 엄격) / token-F1 (라벨만, 부분점수) / masking coverage (privacy recall)
- **응답 품질**: BERTScore (마스킹 전/후 LLM 응답 비교, GPT·Gemini·Claude)
- **처리 지연**: 마스킹 전/후 전송 시간 비교

## 일정

| 주차 | 작업 |
|---|---|
| 9 | 데이터셋 전처리 |
| 9~10 | NER 모델 학습 |
| 10~11 | 마스킹 성능 평가, BERTScore 평가 |
| 11~13 | Chrome 확장 프로그램 개발 |
| 13~14 | 처리 지연 시간 평가, 최종 보고서 |

---

## 🛠️ Trouble Shooting

본 프로젝트 진행 중 발생한 문제와 해결 방법.

### TS-01. `transformers 5.x` Trainer API 변경 — `tokenizer` → `processing_class`

**증상**:
```
TypeError: Trainer.__init__() got an unexpected keyword argument 'tokenizer'
```

**원인**: transformers 5.x 부터 `Trainer.__init__` 의 `tokenizer` 인자가 `processing_class` 로 이름 변경됨.

**해결**: `scripts/train_ner.py` 에서 4.x/5.x 호환을 위해 try/except 으로 분기.
```python
try:
    trainer = Trainer(..., processing_class=tokenizer, ...)
except TypeError:
    trainer = Trainer(..., tokenizer=tokenizer, ...)
```

### TS-02. `regex/` 디렉터리가 서드파티 `regex` 패키지 가림

**증상**:
```
AttributeError: module 'regex' has no attribute 'compile'
```
transformers 임포트 시 발생.

**원인**: 프로젝트 루트의 `regex/` 디렉터리가 PyPI 의 `regex` 패키지를 shadow. transformers 가 `import regex as re` 하는 부분에서 잘못된 모듈을 가져옴.

**해결**: 디렉터리명을 `regex/` → `pii_regex/` 로 변경. 모든 import 업데이트.

### TS-03. Windows 콘솔 cp949 인코딩 에러

**증상**:
```
UnicodeEncodeError: 'cp949' codec can't encode character '—'
```
한글·em-dash 출력 시 발생.

**해결**: 실행 전 환경변수 설정.
```bash
PYTHONIOENCODING=utf-8 python <script>
```
또는 PowerShell:
```powershell
$env:PYTHONIOENCODING="utf-8"
```

### TS-04. KLUE-NER char-level → word-level 변환 시 BIO 무결성 깨짐

**증상**: `I-X` 가 `B-X` 없이 시작되는 케이스 발견 (3000+ 건).

**원인**: KLUE-NER 은 문자 단위 BIO 인데, 어절(공백 분할) 단위로 환원할 때 첫 글자 태그만 보면 entity 가 어절 경계에 걸쳤을 때 anomaly 발생.

**해결**: `scripts/common.py` 에 `normalize_bio()` 헬퍼 추가. `I-X` 가 같은 라벨의 `B-X`/`I-X` 다음에 오지 않으면 `B-X` 로 강제 변환.

### TS-05. KLUE-BERT 체크포인트 LayerNorm beta/gamma 키 워닝

**증상**:
```
There were unexpected keys in the checkpoint:
  bert.embeddings.LayerNorm.beta, ..LayerNorm.gamma, ...
There were missing keys: ..LayerNorm.weight, ..LayerNorm.bias
```

**원인**: 구 KLUE 체크포인트는 TF 스타일 키명(`beta`/`gamma`), HuggingFace 5.x 는 PyTorch 표준(`weight`/`bias`) 기대.

**해결**: 워닝은 **무해**. 학습/평가 정상 동작. transformers 가 내부적으로 키 매핑 처리. 워닝 무시 가능.

### TS-06. 엔티티 치환 증강이 오히려 성능 하락

**증상**: iter3 에서 같은 라벨의 surface 를 무작위로 치환 → F1 0.916 → 0.908 회귀.

**원인**: KLUE 어노테이션은 문맥 의존적 ("한국" = ORG 또는 LOC 문맥). 무작위 치환이 문맥-라벨 정합을 파괴.
예: "한국은 6월 17일 브라질에서 경기" → "충남 부여군 가이아나의" 같이 의미 붕괴.

**해결**: 단순 surface 치환 증강은 KLUE 같은 문맥 의존 데이터셋에 부적합. 대신:
- Curriculum learning (large corpus → small clean corpus)
- 컨텍스트 보존 paraphrase
- 데이터 증강 대신 더 큰 corpus 추가가 더 효과적.

### TS-07. 네이버 NER 포맷이 표준 BIO 와 다름

**증상**: `convert_naver.py` 가 변환 후 모든 태그가 `O` 가 됨.

**원인**: 네이버 NER 은 `LABEL_B` / `LABEL_I` / `-` 포맷 (KLUE 는 `B-LABEL` / `I-LABEL` / `O`).

**해결**: `convert_naver.py` 의 `remap_tag()` 에 두 포맷 모두 지원.
```python
if "_" in tag and tag.rsplit("_", 1)[-1] in ("B", "I"):
    raw, pos = tag.rsplit("_", 1)         # 네이버
elif "-" in tag and tag.split("-", 1)[0] in ("B", "I"):
    pos, _, raw = tag.partition("-")      # 표준
```

### TS-08. KLUE-NER 의 surface-level 라벨 노이즈

**증상**: 같은 어절 surface 가 train 에서 여러 라벨로 어노테이션됨.
- `'한국'` → LOC 170회, ORG 5회 (3% 노이즈)
- `'북한의'` → ORG 47, LOC 25 (35% — inherent ambiguity)
- `'한국은'` → ORG 15, LOC 14 (50% — 완전 모호)

**영향**: 노이즈 surface 위 dev recall 0.85 vs 클린 surface 0.92 (-6.85%p).

**해결**: `scripts/clean_label_noise.py` 로 보수적 정제. minority < 15% AND count >= 5 인 surface 만 majority 라벨로 통일. 50:50 같은 합법적 ambiguity 는 보존.

### TS-09. 네이버 entity 에 URL · 특수문자 노이즈 포함

**증상**: 네이버 NER 의 일부 entity surface 가 매우 노이즈 함.
- `'메카트로닉스공학과(www.mydaily.co.kr)'` (ORG)
- `'야스퍼스자@전자신문,'` (PERSON)
- `'공화국ㅣ강진=김태석'` (LOCATION)

**해결**: `scripts/filters/quality.py` 에 필터 추가:
- `drop_url_entities`: URL/도메인/이메일 포함 entity 를 O 로
- `drop_excessive_special_chars`: 특수문자 비율 50% 초과 entity 를 O 로
- `drop_too_long_entities`: 10어절 초과 entity 를 O 로
- `strip_trailing_punctuation`: entity 끝 어절의 trailing 구두점 strip

`configs/datasets.yaml` 에서 source 별 적용.

### TS-10. Train/Dev 분포 mismatch (도메인 shift)

**현재 상태**: train 79% Naver, dev 93% KLUE — Naver 추가 시 도메인 shift 위험.

**증상 (예측)**: Naver 스타일 학습이 KLUE 평가에서 손해.

**완화 방안**:
- Naver 의 일부를 dev 에도 포함시키지 말 것 (dev 보존)
- 단계적 fine-tuning (curriculum): 1) 대규모 코퍼스로 일반화 학습 → 2) KLUE+합성으로 정밀 조정
- 평가지표 다양화: entity-F1 외 token-F1 / mask-coverage 함께 보기

### TS-11. KLUE 의 organization↔location 본질적 모호성

**증상**: "한국", "북한", "러시아" 같은 국가명이 KLUE 에서 ORG/LOC 동시 라벨.

**원인**: KLUE 어노테이션 규칙: 국가가 "행위주체" 일 때 ORG, "지리" 일 때 LOC. 문맥 의존이라 모델이 학습 어려움.

**영향**: KLUE-NER 의 ORG/LOC entity-F1 천장 ~0.87/0.86. KLUE 공식 RoBERTa-large 도 macro 0.914 로 동일 영역.

**완화**: token-F1 / mask-coverage 같이 boundary 부분점수 주는 지표에선 LOC 0.94, ORG 0.91 로 개선. 마스킹 task 본질에 더 가까움.

### TS-12. PyYAML 의존 추가 누락

**증상**: 초기 `requirements.txt` 에 `pyyaml` 없어 `configs/*.yaml` 로드 실패.

**해결**: `requirements.txt` 에 `pyyaml>=6.0` 추가.

---

## 라이선스

학부 캡스톤 프로젝트. KLUE / 네이버 NER / 국립국어원 / AI-Hub 데이터는 각 출처 라이선스 준수.
