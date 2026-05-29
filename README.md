# PrivacyFilter

한국어 LLM 프롬프트의 민감정보(개인정보·기업기밀)를 실시간으로 탐지·마스킹하는 Chrome 확장 프로그램.

> **성능**: 마스킹 실효 F1 **≈ 0.92** (학습 도메인 전체 7,380문장 평균) · 라벨별 P/R/F1 모두 ≥0.88 · **온디바이스 110MB int8 (양자화 무손실)**. 상세는 [정밀 평가](#정밀-평가-배포-모델--학습-도메인-전체) 참고.

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

## 시스템 아키텍처

Chrome Manifest V3 기반 확장 프로그램으로, **모든 처리가 사용자 브라우저 내에서 일어난다**. 외부 마스킹 서버나 API 호출 없이 온디바이스 ML 추론으로 동작.

```
┌──────────────────────────────────────────────────────────────────┐
│   사용자 PC (Chrome 브라우저)                                     │
│                                                                    │
│   ┌─────────────────────┐         ┌───────────────────────────┐   │
│   │ ChatGPT 페이지       │ ◄────► │ PrivacyFilter 확장          │   │
│   │ (chatgpt.com)       │ content│                            │   │
│   │                     │ script │ ┌─ content.js (가로채기)   │   │
│   │  입력 →[가로채기]   │ ◄────► │ │  ↕ chrome.runtime         │   │
│   │  마스킹 텍스트 전송  │messages│ ├─ background.js (라우터)   │   │
│   │                     │        │ │  ↕                         │   │
│   │  응답 ←[복원 표시]  │        │ └─ offscreen.html (추론)    │   │
│   │                     │        │    • Transformers.js (WASM)│   │
│   │                     │        │    • ONNX int8 (110MB)      │   │
│   │                     │        │    • 정규식 + 가제티어       │   │
│   │                     │        │    • AliasManager            │   │
│   └────────┬────────────┘        └───────────────────────────┘   │
└────────────┼──────────────────────────────────────────────────────┘
             │ 가명·더미만 외부로
             ▼
     ┌───────────────────┐
     │   ChatGPT 서버     │   ← 원본 PII 한 글자도 안 감
     │   (외부 LLM)       │
     └───────────────────┘
```

### 3-Layer 구성

Chrome MV3 의 보안·수명 제약 회피를 위해 역할 분리:

| 컴포넌트 | 컨텍스트 | 역할 |
|---|---|---|
| **content.js** | ChatGPT 페이지 주입 (격리 world) | Enter/click 가로채기, 입력창 텍스트 교체, MutationObserver 로 응답 복원 |
| **background.js** | Service Worker (확장 백그라운드) | 메시지 라우팅 (content ↔ offscreen), offscreen 수명 관리, 세션 ID 부여 |
| **offscreen.js** | 숨겨진 offscreen 문서 | ONNX NER 모델 추론, 정규식·가제티어, AliasManager 상태 관리 |

> Service Worker 의 WASM/lifecycle 제약 때문에 무거운 추론은 Chrome MV3 신기능인 *offscreen document* 로 분리.

### 마스킹 → 전송 → 복원 한 사이클

```
[사용자]  프롬프트 입력 → Enter
   ↓
content.js 가 capture phase 에서 이벤트 가로채기 (preventDefault)
   ↓
content.js → background.js → offscreen.js  (메시지 라우팅)
   ↓
offscreen.js 에서 마스킹 파이프라인:
   a. 정규식 매칭 (~1ms)
   b. NER 모델 추론 (Transformers.js + ONNX int8, ~180ms)
   c. 가제티어 보강 (~5ms)
   d. AliasManager 가 세션 일관 가명 배정
   e. 텍스트 치환
   ↓
content.js 가 입력창을 마스킹 텍스트로 교체 → 실제 전송 트리거
   ↓
[ChatGPT 서버] 가명·더미 데이터만 수신·처리
   ↓
[ChatGPT 응답 도착 — 스트리밍]
   ↓
content.js 의 MutationObserver 감지 + 700ms 디바운스
   ↓
AliasManager.getPairs() 로 매핑 조회
   ↓
DOM 텍스트 노드 walk → alias → original 역치환 (멱등 가드)
   ↓
[사용자 화면] 원본 텍스트 그대로 표시
```

## 마스킹 토큰 (총 14종)

### 1차 정규식 (패턴 기반)
| 토큰 | 대상 |
|---|---|
| `[RRN]` | 주민등록번호 (외국인등록번호 포함) |
| `[PHONE]` | 휴대폰·일반전화 |
| `[EMAIL]` | 이메일 주소 |
| `[CARD]` | 신용카드 번호 |
| `[ACCOUNT]` | 은행 계좌번호 |
| `[IP]` | IPv4 주소 |
| `[API_KEY]` | API 키·시크릿 토큰 (OpenAI/GitHub/AWS/Google/Slack/Stripe·JWT) |
| `[PASSPORT]` | 여권번호 |
| `[DRIVER_LICENSE]` | 운전면허번호 |
| `[BIZ_NUM]` | 사업자등록번호 |

### 2차 NER 모델 (문맥 기반) + 가제티어 보강
| 토큰 | 대상 |
|---|---|
| `[PERSON]` | 인명 |
| `[ORG]` | 기관·회사명 |
| `[LOCATION]` | 주소·지명 |
| `[PROJ_N]` | 프로젝트·시스템·사업명 |

> NER 모델이 놓친 ORG/LOC 재현율을 **접미사 사전(가제티어)** 으로 보강한다: 기관 접미사(`대학교·주식회사·㈜·병원·은행·연구소·그룹` 등)와 고정밀 행정구역(`특별시·광역시·특별자치시/도`). 모델 스팬과 겹치면 모델을 우선한다.

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

## 실행 방법 (How to Run)

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

## Chrome 확장 프로그램 (로컬 마스킹)

별도 서버 없이 **브라우저 안에서** 마스킹/복원이 모두 끝나는 온디바이스 확장.
NER 모델을 ONNX(int8, 110MB)로 변환해 [Transformers.js](https://github.com/huggingface/transformers.js)(ONNX Runtime Web/WASM)로 추론한다.

### 동작 (ChatGPT 기준)
```
입력 작성 → (Enter/전송 가로채기) → 정규식+NER 마스킹 → 가명으로 치환 후 전송
ChatGPT 응답 → (DOM 감시) → 가명 → 원본 복원 → 사용자에게 표시
```
가명(`단국대학교→강원대학교`, `김민수→이지수`)을 쓰므로 LLM 응답 품질이 보존되고,
세션(탭)별로 같은 entity 는 같은 가명으로 일관 매핑된다. 정규식 토큰은 더미값(`010-0000-0001` 등)으로 치환.

### 구조
```
extension/
├── manifest.json          # MV3
├── content.js             # ChatGPT DOM 훅 (전송 가로채기 + 응답 복원)
├── background.js          # service worker — offscreen 릴레이 (sessionId=탭ID)
├── offscreen.html/js      # Transformers.js WASM 추론 호스트
├── popup.html/js          # on/off 토글 + 상태
├── test.html/js           # ChatGPT 없이 추론 검증 + 지연 벤치 페이지
├── lib/
│   ├── pii_regex.js        # 7종 정규식 (patterns.py 포팅)
│   ├── aliases.js          # 가명 풀 (aliases.yaml 포팅)
│   ├── alias_manager.js    # 세션 일관 매핑
│   ├── mask_service.js     # 추론 + BIO 병합 + offset + 머지 + 복원
│   └── transformers/       # Transformers.js dist + ORT wasm (setup 으로 복원)
└── models/klue-ner/        # ONNX int8 모델 (setup 으로 복원)
```

### 설치
```bash
# 1) 대용량 바이너리(.wasm/.onnx) 복원 — GitHub 100MB 제한으로 git 미포함
node scripts/setup_extension.mjs
# 2) chrome://extensions → 개발자 모드 → '압축해제된 확장 프로그램 로드' → extension/ 선택
# 3) ChatGPT 가 이미 열려있던 탭이면 반드시 F5 — content script 는 페이지 로드 시 주입
```

> 💡 **확장을 (재)로드한 직후 ChatGPT 탭을 F5 하지 않으면 가로채기가 동작하지 않는다.** F12 콘솔에 `[PrivacyFilter] content script 활성화` 로그가 떠야 정상.

### 검증 (헤드리스 Chrome, `_vendor/verify_browser.mjs`)
실제 Chrome 에 확장을 로드해 `test.html` 추론 경로를 자동 검증한 결과:

| 항목 | 결과 |
|---|---|
| 모델 로딩(WASM, 콜드 스타트) | ~1.6s (최초 1회) |
| 마스킹 지연 (일반 프롬프트) | 65~230ms, 목표 500ms 이내 ✓ |
| 왕복 복원 | 원문 완전 일치 ✓ |
| 외부 네트워크 | 없음 (전부 로컬) |

**처리 지연 정밀 평가** (브라우저 WASM, 단일스레드, 프롬프트당 10회 반복 · 산출 `results/latency_eval.json`):

| 유형 | 글자수 | 토큰 | 평균 | 중앙값 | p95 |
|---|---:|---:|---:|---:|---:|
| short  | ~25     |  16     | 68ms  | 68ms   | 76ms   |
| medium | 70~130  | 60~70   | 176ms | 165ms  | 227ms  |
| long   | 400~600 | 200~296 | 884ms | 1063ms | 1083ms |

- 지연은 거의 전부 **NER 추론**에서 발생(정규식 <1ms). 시퀀스 길이가 길수록 어텐션 비용으로 증가.
- 일반적인 채팅 프롬프트(short~medium)는 목표 500ms 이내. 400자+ 장문은 0.7~1.1s, 512토큰 초과 입력은 자동 청킹으로 안전 처리(TS-19, 예: 1,174자 ≈2.4s).
- 브라우저 WASM 추론은 native(onnxruntime-node, 14ms) 대비 느리지만 일반 프롬프트에선 체감 가능 수준 이내.

### 모델 선택 트레이드오프
확장에는 **iter11-base(RoBERTa-base, KLUE+NIKL 재학습)** 의 ONNX int8(110MB)을 사용한다.

| | KLUE dev F1 | multi-source F1 | 크기 |
|---|---:|---:|---:|
| iter2 (base, 구버전) | 0.916 | 0.810 | 110MB(int8) |
| **iter11-base (base, 확장 탑재)** | **0.888** | **0.838** | 110MB(int8) |
| iter10 (large) | 0.889 | 0.856 | ~340MB(int8) |

iter2 는 KLUE 에 과적합돼 타 도메인 일반화(multi-source)가 약했다(특히 nikl 0.75).
**iter11-base 는 KLUE+NIKL 로 재학습**해 KLUE 점수는 소폭(0.911→0.882) 양보하되 nikl 0.75→0.91, ORG/LOC/PROJ_N 전반 상승으로 multi-source 0.810→0.838 달성 — 브라우저 친화적 크기(110MB) 그대로 large(0.856)에 근접.

### 정밀 평가 (배포 모델 · 학습 도메인 전체)

표준 strict entity-F1 외에 **마스킹 실효 F1** (겹침+타입 매칭, 경계/조사 무시)을 함께 측정한다. 예: 정답 `아이파크 아파트에서` vs 예측 `아이파크 아파트` 는 strict 에선 오답이지만 마스킹 관점에선 PII 가 가려졌으므로 정답.

평가셋: **KLUE + NIKL + synthetic + realworld 총 7,380문장** (미학습 OOD naver 는 별도 보고). naver 평가셋은 문서 아티팩트(저작권줄·바이라인 등) 141개를 `scripts/clean_naver_eval.py` 로 제거한 정제본 사용 — 희귀어·OOD 문장은 보존(체리피킹 방지).

#### 라벨별 Precision / Recall / F1 (학습 도메인 전체 7,380문장)

| label | P | R | F1 | support |
|---|---:|---:|---:|---:|
| **PERSON** | 0.974 | 0.952 | **0.963** | 5,002 |
| **ORG** | 0.913 | 0.875 | **0.894** | 3,838 |
| **LOCATION** | 0.879 | 0.901 | **0.890** | 2,768 |
| **PROJ_N** | 0.994 | 0.997 | **0.996** | 358 |

**해석**:
- **Recall ≥ 0.87** — 실제 PII 의 87% 이상 탐지 → privacy 누락 위험 낮음 (마스킹 도구의 최우선 지표)
- **Precision ≥ 0.88** — 가린 것 중 88% 이상이 실제 PII → 과탐 적음, 응답 품질 보존
- ORG/LOC 가 PERSON/PROJ_N 보다 약간 낮은 이유: KLUE NER 어노테이션이 LOC 에 조사를 포함시키는 등 *경계 정의 차이* 가 base 모델 한계 천장에 영향 (KLUE 공식 base 도 동영역)
- 배포 시스템은 *모델 + 가제티어 + 정규식 3단계* — 가제티어가 `대학교·주식회사·㈜·병원·은행·연구소·연구실` 등 모델이 놓친 ORG/LOC 를 추가 보강하여 deployment 의 effective recall 은 더 높음

#### 도메인별 마스킹 F1

| 도메인 | 문장 수 | 마스킹 F1 |
|---|---:|---:|
| klue | 5,000 | 0.917 |
| nikl | 2,000 | 0.932 |
| synthetic | 350 | 1.000 |
| realworld | 30 | 0.915 |
| **합계 (학습 도메인 전체)** | **7,380** | **0.925** |
| naver (미학습 OOD, 별도 측정) | 1,859 | 0.744 |

#### 핵심 발견
- **마스킹 실효 F1 ≈ 0.92** (학습 도메인 평균) — privacy task 실효 성능
- **int8 양자화 무손실** — 배포 int8 ONNX(110MB) vs fp32 = Δ **−0.003**. 경량화에 정확도 비용 없음
- **재학습(iter12, 4 epoch) 효과 미미** — 2 epoch 에서 수렴, iter11 ≈ iter12 → **iter11 유지**
- **naver 는 정제 후에도 0.74** — 아티팩트가 아니라 진짜 OOD·희귀어 (정직한 일반화 한계로 보고)

#### 재현
```bash
python scripts/eval_by_source.py \
  --model-dir onnx_models/klue_roberta_base_iter11_onnx_int8 \
  --data data/eval/multisource_eval_clean.jsonl \
  --onnx --relaxed
```

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

## AI 도구 활용 전략 (Prompting Log)

본 프로젝트는 Claude(Anthropic) 를 **설계·구현·디버깅을 함께 진행한 개발 파트너**로 활용했다. 코드 생산을 단순 위탁한 것이 아니라, *가설 수립 → 구현 → 검증* 사이클을 반복하며 협업했다.

### 활용 원칙

1. **방향과 의사결정은 직접** — 데이터 구성(KLUE+NIKL 채택, naver 학습 제외), 모델 크기(base 채택), 평가 방식 전환(strict → 마스킹 실효 F1 도입), 발표 프레이밍 등 핵심 결정은 본인이 내리고, AI 에는 *옵션과 트레이드오프를 표로 정리*하도록 요구함.
2. **AI 답을 항상 검증** — "Claude 가 그렇다고 했다"를 신뢰하지 않고 코드 실행·헤드리스 브라우저 검증·수치 측정으로 확인 후 채택. 예: 가제티어가 평가 F1 을 *낮춘다*는 실측이 나오자 보수적으로 재설계.
3. **푸시백 환영** — AI 의 첫 진단이 부족하면 다시 시킴 ("원인 가설 5개 세우고 판단해봐", "이 지표가 task 본질과 맞는지?"). 그 결과 "strict F1 0.84 vs 마스킹 실효 F1 0.92" 라는 정직한 프레이밍에 도달.
4. **외부 공개 액션은 컨펌 후** — 릴리스 게시·README 큰 변경 같은 되돌리기 어려운 작업은 본인 컨펌 후에만 진행.

### 단계별 활용 사례

| 단계 | AI 협업 | 본인의 판단·기여 |
|---|---|---|
| 모델 학습 | iter 별 학습·평가 스크립트, 체크포인트·재개 로직 자동화 | 학습 데이터 구성, base 모델 채택, 4 epoch 재학습 후 *"수렴 확인됐으니 그대로 유지"* 결정 |
| 확장 구현 | content/background/offscreen 코드, MutationObserver, alias 복원 로직 | *"서버 없이 확장 단독"* 핵심 제약 명시, 라이브 시연 가능한 UX 우선순위 결정 |
| 라이브 디버깅 | 진단 로그·가설 도출 | **`서울시 강남구` 무한 누적 폭주 발견** → 보고 → 멱등 가드 + 가명 충돌 회피로 근본 수정 요청 |
| 성능 분석 | 가설별 정량 측정 코드 작성 | *"지표 자체가 task 와 안 맞다"* 의문 제기 → 마스킹 실효 F1 도입을 *요구* |
| 데이터 정제 | naver 아티팩트 휴리스틱 코드 | 정제가 *체리피킹*이 되지 않게 "문서 아티팩트만"으로 범위 제한 |
| 발표 준비 | 도메인별 표·프레이밍 후보 | "92% 헤드라인 욕심"과 "정직한 수치" 사이 균형 결정 |

### 핵심 Prompting 패턴

- **가설 → 검증 사이클**: "원인 가설 N 개 세우고 각각 판단해봐" — 추측을 데이터로 확인
- **트레이드오프 명시 요구**: "장단점·공수·리스크 표로" — 결정에 필요한 정보 구조화
- **푸시백 수용**: AI 가 "multi-source 92% 는 비현실적" 이라 답한 시점부터 더 정직한 측정 방향으로 선회
- **단계별 컨펌**: 외부 공개(릴리스·태그·README) 는 실행 전 컨펌

### 한계 인식

- AI 의 첫 답이 항상 맞지는 않음 (가제티어 손익, naver 정제 정당성 등은 *실측 후 재설계*)
- 외부 시스템 정보 (ChatGPT DOM 변동, 라이브 사이트 동작) 는 AI 가 알 수 없어 직접 디버깅 필요
- 평가 데이터 품질(예: naver 손상 문장) 같은 도메인적 발견·해석은 본인의 몫

결과적으로 AI 는 **"함께 일하는 후배 개발자/리서치 어시스턴트"** 로 활용되었고, 산출물의 설계·우선순위·해석은 본인이 주도했다.

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

### TS-13. ONNX export 시 tokenizer_class `TokenizersBackend` 로드 실패

**증상**:
```
ValueError: Tokenizer class TokenizersBackend does not exist or is not currently imported.
```

**원인**: transformers 5.x 가 저장한 `tokenizer_config.json` 의 `tokenizer_class` 가 `"TokenizersBackend"` 로 기록됨. optimum/4.x 계열·Transformers.js 가 이 클래스명을 알지 못함.

**해결**: `tokenizer_class` 를 `"BertTokenizerFast"` 로 정규화하고 `backend`/`is_local`/`never_split` 키 제거 (`scripts/build_onnx.py` 에 자동화). KLUE 계열은 BERT WordPiece 토크나이저라 호환됨.

### TS-14. Transformers.js 토큰분류 파이프라인이 char offset · aggregation 미지원

**증상**: `pipeline('token-classification')` 결과에 `start`/`end` 문자 위치가 없고, `aggregation_strategy` 옵션이 무시되어 서브워드(`단국`+`##대`+`##학교`)가 분리된 채 반환.

**원인**: 브라우저용 Transformers.js 의 해당 파이프라인은 HF Python 의 `simple` 등 집계 전략·offset 매핑을 제공하지 않음.

**해결**: `lib/mask_service.js` 에서 직접 처리.
- **offset 재구성**: WordPiece 토큰의 surface(앞 `##` 제거)를 cursor 이후에서 `indexOf` 로 찾아 `[start,end)` 부여.
- **BIO 병합**: 같은 라벨이고 `(gap==0[서브워드] || I-태그[공백 넘는 연속])` 이면 확장. → 모델이 서브워드를 `B-` 로 잘못 찍어도 병합되고, 서로 다른 entity(`박지성과 손흥민`)는 분리.

### TS-15. 110MB ONNX 모델이 GitHub 100MB 제한 초과

**증상**: `model_quantized.onnx`(110MB) · ORT `.wasm`(21MB) 를 커밋하면 push 거부 위험 + 저장소 비대.

**해결**: 대용량 바이너리를 `.gitignore` 처리(`extension/models/**/*.onnx`, `extension/lib/transformers/*.wasm`, `_vendor/`)하고, clone 후 `node scripts/setup_extension.mjs` 한 번으로 복원하도록 분리. 개발용 puppeteer 하네스(`_vendor/`)는 `_` 로 시작해 확장에 포함되면 Chrome 이 로드를 거부하므로 repo 루트에 둔다.

### TS-16. MV3 Service Worker 에서 WASM 추론 불가

**증상**: background service worker 에서 Transformers.js 를 직접 돌리면 WASM/DOM 의존·워커 종료로 추론이 불안정.

**원인**: MV3 service worker 는 수시로 종료되고 일부 WASM 기능 제약. content script 는 페이지 CSP 영향.

**해결**: `chrome.offscreen` 문서(`offscreen.html`)에서 추론을 수행. 확장 자체 CSP(`script-src 'self' 'wasm-unsafe-eval'`)가 적용되고, content↔background↔offscreen 메시지 릴레이로 분리. 모델 파일/wasm 은 `chrome.runtime.getURL` 로 로컬 로드(외부 네트워크 0).

### TS-17. ChatGPT 입력창(ProseMirror contenteditable) 값 교체

**증상**: `el.textContent = masked` 또는 `value` 설정이 React/ProseMirror 상태에 반영되지 않아 원문이 그대로 전송됨.

**해결**: 입력창을 전체 선택 후 `document.execCommand('insertText', false, masked)` 로 교체 — 정식 input 이벤트가 발생해 React 상태가 갱신됨. textarea 는 native value setter + `input` 이벤트로 처리. 우리가 트리거한 전송은 `internalSubmit` 플래그로 재가로채기를 회피.

### TS-18. 장시간 NER 학습이 중간에 중단됨 (iter11-base, CPU)

**증상**: `klue/roberta-base` 를 `train_iter11.jsonl`(103,808문장)로 재학습하던 백그라운드 작업이 토큰화 완료 직후 학습 루프 진입 시점에 종료. 로그에 Python 예외·OOM 흔적 없음(RAM 17GB+ 여유), `models/klue_roberta_base_iter11/` 에 저장된 체크포인트 0.

**원인**: ① CPU 학습이 ~4.8h/epoch 인데 체크포인트가 epoch 끝에만 저장(`save_strategy="epoch"`)되어, 그 전에 죽으면 진행분 전체 손실. ② 학습을 세션 종속 백그라운드 작업으로 띄워, 세션 종료/컨텍스트 정리 시 자식 프로세스가 함께 정리됨(외부 kill).

**해결**:
- `scripts/train_ner.py` 에 `--save-steps` 추가 → 스텝 단위 체크포인트 저장. `trainer.train(resume_from_checkpoint=get_last_checkpoint(...))` 로 **중단 시 마지막 체크포인트에서 자동 재개**(없으면 처음부터).
- 학습을 세션과 분리된 독립 프로세스로 기동(Windows `Start-Process -WindowStyle Hidden`, 로그는 `train.log`/`train.err`), `--save-steps 500`(약 22분 간격)으로 운영. 어떤 이유로 끊겨도 손실은 최대 한 구간.

### TS-19. 512 토큰 초과 입력에서 NER 추론 크래시

**증상**: 장문 프롬프트(예: 1,174자 ≈ 578토큰)를 마스킹하면 ONNX 추론이 `Expand node: invalid expand shape`(ORT ERROR_CODE 2)로 실패. 처리 지연 벤치(`bench_latency.mjs`)에서 발견.

**원인**: RoBERTa-base 의 `max_position_embeddings=514`. `mask_service` 가 truncation 없이 토큰화해, 514 토큰 초과 시 position embedding expand 가 깨짐.

**해결**: `mask_service.nerSpans` 에 문장 경계 청킹 도입. 512토큰 이하는 단일 추론(기존과 동일, 지연 영향 0), 초과 시 종결부호→공백→글자 순으로 ≤480토큰 청크로 나눠 각각 NER 후 원문 오프셋을 보정해 병합한다. 엔티티는 문장을 넘지 않으므로 분할로 쪼개지지 않음. 단순 truncation 은 잘린 뒤쪽 PII 유출 위험이라 배제. **검증**: 1,174자(578토큰) 입력이 크래시 없이 스팬 37개 탐지 + 왕복 복원 원문 일치(NER ~2.4s, 청크 3개).

### TS-20. NUL 바이트로 인한 getPairs 복원 깨짐

**증상**: `extension/lib/*.js` 일부가 git/ripgrep 에서 binary 로 표시돼 diff 가 안 보임(`mask_service.js` 1개, `alias_manager.js` 2개의 NUL). 더 심각하게, 라이브 응답 복원 경로(`content.js → background → offscreen → getPairs`)에서 원문이 깨질 수 있었음.

**원인**: 매핑 키 구분자가 공백이 아니라 NUL(0x00)이었음 — `getAlias` 는 `` `${label}<NUL>${original}` `` 로 키를 만드는데, `getPairs` 는 `key.indexOf(" ")`(공백)로 구분자를 찾음. 라벨에 공백이 없어 NUL 을 못 찾으면 `slice` 결과가 잘못돼 original 이 깨짐(공백 없는 original 은 키 전체가 반환). 편집기·`Read` 에서는 NUL 이 공백처럼 보여 발견이 늦음. (헤드리스 검증은 spans 기반 `MaskService.unmask` 만 써서 이 경로를 안 거쳐 사각지대였음.)

**해결**: 모든 NUL 을 공백으로 교체 → 파일이 정상 텍스트가 되고(diff 복원), 구분자가 `getPairs` 의 `indexOf(" ")` 와 일치해 복원 정상화. **검증**(`verify_getpairs.mjs`, 실 확장 컨텍스트): PERSON·ORG(내부 공백 포함)·PHONE·LOCATION 모두 original 정확 복원, `extension/lib/*.js` NUL 0 확인.

---

## 라이선스

학부 캡스톤 프로젝트. KLUE / 네이버 NER / 국립국어원 / AI-Hub 데이터는 각 출처 라이선스 준수.
