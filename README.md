# PrivacyFilter

한국어 LLM 프롬프트의 민감정보(개인정보·기업기밀)를 사용자 PC 내에서 실시간 탐지·마스킹하는 Chrome 확장 프로그램.

> **성능**: 마스킹 실효 F1 ≈ 0.92 (학습 도메인 전체 7,380문장 평균) · 라벨별 P/R/F1 모두 ≥ 0.88 · **온디바이스 110MB int8 (양자화 무손실)**

---

## 프로젝트 개요

ChatGPT·Gemini·Claude 등 외부 LLM 서비스를 사용할 때, 사용자는 자신도 모르게 민감한 개인정보(이름·연락처·소속·계좌번호·API 키 등)를 외부 서버에 전송하게 된다. 한번 전송된 정보는 회수가 불가능하며, 모델 학습 데이터로 재활용될 가능성도 있다. 기존 솔루션(Prεεmpt, LLM-Guard, GPT-Guard 등)은 대부분 *외부 API 의존* 또는 *영어 전용* 으로, 한국어 PII 를 진정한 의미의 로컬 환경에서 보호하지 못한다.

**본 프로젝트는 사용자 브라우저 내에서만 동작하면서, 기존 ChatGPT 사용 흐름을 그대로 유지하고, 입력이 서버로 전송되기 직전 자동으로 민감정보를 마스킹하는 온디바이스 Chrome 확장 프로그램을 구현한다.**

### 핵심 특징

- **온디바이스 동작**: 외부 마스킹 서버나 API 호출 없이 사용자 브라우저 내에서 모든 처리. 원본 PII 가 사용자 PC 를 벗어나지 않음.
- **2-단계 마스킹**: 정규식(패턴 기반, 10종) + NER 모델(문맥 기반, 4종) → 총 **14종의 한국어 민감정보** 자동 탐지·치환.
- **자연스러운 가명 사용**: `[REDACTED]` placeholder 가 아닌 가짜 이름·번호로 치환 → LLM 응답 품질 보존.
- **양방향 처리**: 전송 직전 마스킹 + 응답 도착 시 alias → 원본 자동 복원 → 사용자는 평소와 동일한 경험.
- **경량 모델**: RoBERTa-base 의 ONNX int8 양자화(110MB) + WebAssembly 추론. 양자화 손실 ≈ −0.003 (사실상 무손실).

### 마스킹 토큰 (총 14종)

| 1차 정규식 (10종) | 2차 NER 모델 (4종) |
|---|---|
| RRN(주민등록번호) · PHONE · EMAIL · CARD(신용카드) · ACCOUNT(계좌) · IP · API_KEY · PASSPORT(여권) · DRIVER_LICENSE(운전면허) · BIZ_NUM(사업자등록) | PERSON · ORG(기관) · LOCATION(지명) · PROJ_N(프로젝트명) |

---

## 시스템 아키텍처

Chrome Manifest V3 기반 확장 프로그램으로, **모든 처리가 사용자 브라우저 내에서 일어난다**.

```
┌──────────────────────────────────────────────────────────────────┐
│   사용자 PC (Chrome 브라우저)                                     │
│                                                                    │
│   ┌─────────────────────┐         ┌───────────────────────────┐   │
│   │ ChatGPT 페이지       │ ◄────► │ PrivacyFilter 확장          │   │
│   │ (chatgpt.com)       │ content│                            │   │
│   │                     │ script │ ┌─ content.js (가로채기)   │   │
│   │  입력 → [가로채기]  │ ◄────► │ │  ↕ chrome.runtime         │   │
│   │  마스킹 텍스트 전송  │messages│ ├─ background.js (라우터)   │   │
│   │                     │        │ │  ↕                         │   │
│   │  응답 ← [복원 표시]  │        │ └─ offscreen.html (추론)    │   │
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
   c. 가제티어 보강 (~5ms) — 모델이 놓친 ORG/LOC 접미사 기반 추가 탐지
   d. AliasManager 가 세션 일관 가명 배정 (가명⊂원본 충돌 회피)
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

---

## AI 도구 활용 전략 (Prompting Log)

본 프로젝트는 Claude(Anthropic) 를 **설계·구현·디버깅을 함께 진행한 개발 파트너**로 활용했다. 코드 생산을 단순 위탁한 것이 아니라, *가설 수립 → 구현 → 검증* 사이클을 반복하며 협업했다.

### 활용 원칙

1. **방향과 의사결정은 직접** — 데이터 구성(KLUE+NIKL 채택, naver 학습 제외), 모델 크기(base 채택), 평가 방식 전환(strict → 마스킹 실효 F1 도입), 발표 프레이밍 등 핵심 결정은 본인이 내리고, AI 에는 *옵션과 트레이드오프를 표로 정리* 하도록 요구함.
2. **AI 답을 항상 검증** — "Claude 가 그렇다고 했다"를 신뢰하지 않고 코드 실행·헤드리스 브라우저 검증·수치 측정으로 확인 후 채택. 예: 가제티어가 평가 F1 을 *낮춘다*는 실측이 나오자 보수적으로 재설계.
3. **푸시백 환영** — AI 의 첫 진단이 부족하면 다시 시킴 ("원인 가설 5개 세우고 판단해봐", "이 지표가 task 본질과 맞는지?"). 그 결과 "strict F1 0.84 vs 마스킹 실효 F1 0.92" 라는 정직한 프레이밍에 도달.
4. **외부 공개 액션은 컨펌 후** — 릴리스 게시·README 큰 변경 같은 되돌리기 어려운 작업은 본인 컨펌 후에만 진행.

### 단계별 활용 사례

| 단계 | AI 협업 | 본인의 판단·기여 |
|---|---|---|
| 모델 학습 | iter 별 학습·평가 스크립트 자동화, 체크포인트·재개 로직 구현 | 학습 데이터 구성, base 모델 채택, 4 epoch 재학습 후 *"수렴 확인됐으니 그대로 유지"* 결정 |
| 확장 구현 | content/background/offscreen 코드, MutationObserver, alias 복원 로직 | *"서버 없이 확장 단독"* 핵심 제약 명시, 라이브 시연 가능한 UX 우선순위 결정 |
| 라이브 디버깅 | 진단 로그 추가·가설 도출 | **`서울시 강남구` 무한 누적 폭주 발견** → 보고 → 멱등 가드 + 가명 충돌 회피로 근본 수정 요청 |
| 성능 분석 | 가설별 정량 측정 코드 작성 | *"지표 자체가 task 와 안 맞다"* 의문 제기 → 마스킹 실효 F1 도입을 *요구* |
| 데이터 정제 | naver 아티팩트 휴리스틱 코드 | 정제가 *체리피킹* 이 되지 않게 "문서 아티팩트만" 으로 범위 제한 |
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

## 실행 방법 (How to Run)

### 방법 A — 일반 사용자 (Chrome 확장 설치)

**1. 릴리스 ZIP 다운로드**

[GitHub Releases](https://github.com/LOK-AeGS/PrivacyFilter/releases) 페이지에서 최신 릴리스의 `PrivacyFilter-extension.zip` 을 받는다 (NER 모델·WASM 바이너리 포함, 약 73MB).

> ⚠️ GitHub 의 *Source code (zip)* 가 아니라 **릴리스에 첨부된 ZIP** 을 받아야 함. 소스 ZIP 에는 GitHub 100MB 제한으로 모델·WASM 이 빠져 있어 동작하지 않는다.

**2. 압축 해제**

다운받은 ZIP 을 풀면 `extension/` 폴더가 생긴다. 내부에 `manifest.json` 이 보이는지 확인.

**3. Chrome 에 로드**

1. 주소창에 `chrome://extensions` 입력
2. 우측 상단 **개발자 모드** 토글 ON
3. **압축해제된 확장 프로그램 로드** 클릭
4. 압축 푼 `extension/` 폴더 선택
5. 목록에 **PrivacyFilter** 카드가 뜨면 설치 완료

**4. 사용**

1. `chatgpt.com` 접속 후 로그인
2. **확장을 새로 로드한 직후** 이미 열려있던 ChatGPT 탭은 **F5 새로고침** (content script 가 페이지 로드 시 주입되므로 필수)
3. 평소처럼 프롬프트 입력 후 전송 — 자동으로 민감정보가 가명·더미로 치환되어 ChatGPT 에 전송된다
4. 응답에는 가명이 자동으로 원본으로 복원되어 표시

**(선택) 디버그 토글**

툴바의 PrivacyFilter 아이콘 클릭 → **"디버그 로그 (F12 콘솔)"** 스위치 ON.

→ F12 콘솔에 마스킹 항목 표, 전송된 텍스트, ChatGPT 응답 지연(마스킹 오버헤드 % 포함) 까지 표시. 시연·디버깅에 유용.

---

### 방법 B — 개발자 (소스에서 빌드 및 학습)

**의존성 설치**

```bash
git clone https://github.com/LOK-AeGS/PrivacyFilter.git
cd PrivacyFilter
pip install -r requirements.txt   # Python 3.11+
```

**대용량 바이너리 복원 (모델·WASM 은 gitignore)**

```bash
node scripts/setup_extension.mjs
```

→ `@huggingface/transformers` npm 패키지에서 WASM·JS dist 복사 + 이전 학습 모델의 ONNX int8 을 `extension/models/klue-ner/` 로 복원.

**Chrome 확장 로드 (개발 모드)**

`chrome://extensions` → 개발자 모드 → **압축해제된 확장 프로그램 로드** → `extension/` 폴더 선택.

코드 수정 후엔 `chrome://extensions` 의 PrivacyFilter 카드에서 ↻ (새로고침) 한 번 + ChatGPT 탭 F5.

**(선택) 모델 재학습**

```bash
# 1) 데이터셋 빌드 (configs/datasets.yaml 기반)
python scripts/build_dataset.py

# 2) 학습 (CPU 기준 ~8h / 2 epoch)
python scripts/train_ner.py \
  --model klue/roberta-base \
  --train data/processed/train.jsonl \
  --dev   data/processed/dev.jsonl \
  --labels data/processed/label_list.txt \
  --out-dir models/my_model \
  --epochs 2 --batch-size 16 --lr 5e-5 --save-steps 500

# 3) ONNX int8 변환 (확장 배포본 생성)
python scripts/build_onnx.py \
  --model-dir models/my_model \
  --out-dir onnx_models/my_model_onnx
```

**평가**

```bash
# strict + 마스킹 실효 F1 (도메인별)
python scripts/eval_by_source.py \
  --model-dir onnx_models/klue_roberta_base_iter11_onnx_int8 \
  --data data/eval/multisource_eval_clean.jsonl \
  --onnx --relaxed
```

**확장 자체 테스트 (헤드리스 Chrome)**

```bash
cd _vendor
npm install
node verify_browser.mjs   # 모델 로드 + 마스킹 + 왕복 복원 검증
node verify_chunk.mjs     # 장문(512+토큰) 청킹 검증
node bench_latency.mjs    # 처리 지연 분포 측정
```

---

## 라이선스

학부 캡스톤 프로젝트. KLUE / 네이버 NER / 국립국어원 / AI-Hub 데이터는 각 출처 라이선스 준수.
