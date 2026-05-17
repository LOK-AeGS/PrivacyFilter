# PrivacyFilter Chrome 확장 — 아키텍처 설계

**작성일**: 2026-05-17 (Phase 0)
**대상 LLM 사이트**: ChatGPT (chat.openai.com / chatgpt.com) — 1차 / Gemini / Claude — 후속

---

## 1. 사용자 시나리오 (UX)

```
1. 사용자가 Chrome 에 PrivacyFilter 확장 설치
2. ChatGPT 페이지 접속 → 확장 자동 활성화 (사이트 아이콘 표시)
3. 입력창에 평소처럼 프롬프트 작성
   예: "안녕하세요, 단국대학교 김민수입니다. 차세대 ERP 시스템 도입 일정을 알려주세요."
4. 전송 버튼 클릭
   ┌─ (확장이 가로채서) ────────────────────────┐
   │ 자동 마스킹:                                │
   │ "안녕하세요, 강원대학교 이지수입니다.       │
   │  프로젝트 A 일정을 알려주세요."             │
   │                                            │
   │ 매핑 보관 (로컬 메모리):                    │
   │   단국대학교 ↔ 강원대학교 (ORG)             │
   │   김민수 ↔ 이지수 (PERSON)                 │
   │   차세대 ERP 시스템 도입 ↔ 프로젝트 A (PROJ_N)│
   └────────────────────────────────────────────┘
5. ChatGPT 응답 도착
   원본 (LLM 출력): "이지수님, 프로젝트 A 의 일정은 ..."
   ┌─ (확장이 후처리) ───────────────────────────┐
   │ 자동 복원:                                  │
   │ "김민수님, 차세대 ERP 시스템 도입 의 일정은 ..."│
   └────────────────────────────────────────────┘
6. 사용자 화면엔 복원된 응답이 표시됨
```

→ **사용자는 마스킹 사실을 인지하지 않아도 자연스러운 대화**.

## 2. 컴포넌트 다이어그램

```
┌─────────────────────────────────────────────────────────────────┐
│ Chrome Browser (ChatGPT page)                                   │
│ ┌───────────────────────────────────────────────────────────┐  │
│ │ Content Script (extension/content.js)                      │  │
│ │  ├─ DOM 감지 (input area, send button, message container) │  │
│ │  ├─ fetch/XHR 인터셉트 (전송 직전 마스킹)                 │  │
│ │  ├─ 응답 텍스트 후처리 (복원)                              │  │
│ │  └─ background script 와 message 통신                     │  │
│ └───────────────┬───────────────────────────────────────────┘  │
│                 │                                                │
│ ┌───────────────▼───────────────────────────────────────────┐  │
│ │ Background Service Worker (extension/background.js)        │  │
│ │  ├─ 매핑 보관 (chrome.storage.session — 탭별)              │  │
│ │  ├─ Local Server 호출 (fetch http://localhost:8000)        │  │
│ │  └─ Alias pool 관리 (chrome.storage.local)                 │  │
│ └───────────────┬───────────────────────────────────────────┘  │
└─────────────────┼───────────────────────────────────────────────┘
                  │
                  │ HTTP (localhost:8000)
                  │
┌─────────────────▼───────────────────────────────────────────────┐
│ FastAPI Local Server (server/main.py)                           │
│  ├─ POST /mask    : text → masked + span 매핑                  │
│  ├─ POST /unmask  : text + span → 원본 복원                    │
│  ├─ POST /healthz : 서버 상태 확인                             │
│  │                                                              │
│  ├─ Regex Pipeline (pii_regex/patterns.py)                     │
│  └─ NER Model (models/klue_roberta_large_iter10)               │
└─────────────────────────────────────────────────────────────────┘
```

## 3. API 명세

### POST /mask

```http
POST /mask
Content-Type: application/json

{
  "text": "안녕하세요, 단국대학교 김민수입니다. 차세대 ERP 시스템 도입 일정을 알려주세요.",
  "session_id": "tab-12345"   // 같은 세션 내 일관된 가명 위해
}
```

응답:
```json
{
  "masked_text": "안녕하세요, 강원대학교 이지수입니다. 프로젝트 A 일정을 알려주세요.",
  "spans": [
    {"original": "단국대학교", "alias": "강원대학교", "label": "ORG", "start": 7, "end": 12},
    {"original": "김민수", "alias": "이지수", "label": "PERSON", "start": 13, "end": 16},
    {"original": "차세대 ERP 시스템 도입", "alias": "프로젝트 A", "label": "PROJ_N", "start": 21, "end": 35}
  ],
  "latency_ms": 87
}
```

### POST /unmask

```http
POST /unmask
Content-Type: application/json

{
  "text": "이지수님, 프로젝트 A 의 일정은 ...",
  "spans": [...]  // /mask 응답의 spans 그대로 전달
}
```

응답:
```json
{
  "restored_text": "김민수님, 차세대 ERP 시스템 도입 의 일정은 ..."
}
```

## 4. 가명(Alias) 풀 설계

### 정책
- **자연스러운 한국어 가명** (LLM 응답 품질 보존)
- **일관된 매핑** (같은 세션 내 같은 entity = 같은 alias)
- **레이블별 별도 풀** (PERSON 풀, ORG 풀, LOC 풀, PROJ_N 풀)
- **정규식 대상은 더미 값** (PHONE → 010-0000-0000, EMAIL → user@example.com 등)

### 라벨별 alias 풀

**PERSON (한국 일반 이름)**:
```
이지수, 박철호, 김민서, 정수아, 최예준, 한도윤, 윤채원,
강시우, 조하은, 임서진, ...
```
→ 약 30~50 개. 성별 mix.

**ORG (가상 기관·회사)**:
```
강원대학교, 동해전자, 새한금융, 푸른솔연구원, ABC 솔루션즈,
가람물류, 한빛에너지, ...
```
→ 약 20~30 개.

**LOCATION (한국 지명)**:
```
서울시, 부산시, 대전시, 광주시, 경기 안양시,
강원 춘천시, 충북 청주시, ...
```
→ 약 20 개.

**PROJ_N (가상 프로젝트명)**:
```
프로젝트 A, 프로젝트 B, ... 또는
신규 플랫폼 구축, 차세대 시스템 개발, 디지털 혁신 사업, ...
```
→ 약 15 개.

**정규식 토큰 (더미 값)**:
| 토큰 | 더미 값 |
|---|---|
| `[PHONE]` | `010-0000-0000` |
| `[EMAIL]` | `user1@example.com` (번호 증가) |
| `[RRN]` | `900101-1000000` |
| `[CARD]` | `0000-0000-0000-0000` |
| `[ACCOUNT]` | `000-0000-000000` |
| `[IP]` | `127.0.0.1` |
| `[API_KEY]` | `sk-dummy-XXXX...` |

### 일관성 매핑

세션 내 같은 entity 가 여러 번 등장하면 같은 alias:
- 첫 등장: "김민수" → "이지수"
- 두 번째 등장: "김민수" → "이지수" (재사용)
- 다른 사람: "박서준" → "박철호" (별개 alias)

서버 내 `session_id` 별 매핑 사전 보관.

## 5. 데이터 흐름 (상세)

### 송신 (마스킹)
```
사용자 입력 (textarea)
    ↓
content.js: textarea 값 read
    ↓
content.js → background.js: { action: "mask", text, session_id }
    ↓
background.js → FastAPI /mask: HTTP POST
    ↓
FastAPI:
    1. Regex 1차 마스킹 (PHONE, EMAIL, RRN 등 → 더미 값)
    2. NER 모델 추론 (PERSON, ORG, LOC, PROJ_N)
    3. Alias 매핑 (entity → alias, 일관성 유지)
    4. 결과 반환
    ↓
background.js: 매핑 저장 (chrome.storage.session)
    ↓
content.js: textarea 값 → masked_text 로 교체
    ↓
사용자가 보던 그대로 ChatGPT 에 전송
```

### 수신 (복원)
```
ChatGPT 응답 (DOM 추가)
    ↓
content.js: MutationObserver 로 새 메시지 감지
    ↓
content.js → background.js: { action: "unmask", text, session_id }
    ↓
background.js: 저장된 매핑 조회
    ↓
background.js → FastAPI /unmask: HTTP POST
    ↓
FastAPI:
    - text 내 모든 alias 를 original 로 치환
    - 더미 정규식 값(`010-0000-0000` 등)도 원본으로 복원
    ↓
content.js: DOM 의 응답 텍스트 → restored_text 로 교체
```

## 6. 보안·프라이버시 고려

| 항목 | 처리 |
|---|---|
| 매핑 데이터 위치 | **로컬만** (chrome.storage.session, FastAPI 프로세스 메모리) |
| 외부 전송 | **없음** (서버는 localhost:8000) |
| 매핑 영구 저장 | **세션 종료 시 삭제** (chrome.storage.session 특성) |
| 모델 추론 | 로컬 PC CPU (외부 API 호출 X) |
| OPENAI 등 LLM 으로 전송 | **마스킹된 텍스트만** |

## 7. 핵심 기술 결정

### Manifest V3 사용
- Chrome 공식 최신 표준 (2024+ MV2 deprecated)
- Service Worker 기반 background script

### Localhost 서버 방식
- 모델 추론을 Chrome 확장 내부에서 직접 하는 것은 불가능 (성능·메모리)
- 별도 FastAPI 서버를 백엔드로 사용
- 사용자가 PC 부팅 시 서버 자동 실행 권장 (Windows 시작 프로그램)

### Fetch 인터셉트 vs DOM 감시
- **권장**: 둘 다. fetch 인터셉트(가능 시) + 입력 textarea 직접 수정 (fallback)
- ChatGPT 는 fetch (`POST /backend-api/conversation`) 로 전송 → window.fetch 오버라이드
- DOM 입력 방식이 더 안정적일 수 있음 (사이트 업데이트 시 fetch URL 바뀜)

### 복원 시 LLM 응답의 alias 매칭
- 단순 string replace (alias → original)
- LLM 이 alias 를 약간 변형해도 (예: "이지수씨" → "이지수 씨") 대응 위해 **느슨한 매칭** (조사 무시)

## 8. 구현 우선순위

| Phase | 산출물 | 기능 |
|---|---|---|
| **1** | FastAPI 서버 | /mask /unmask /healthz |
| **1** | alias pool YAML | configs/aliases.yaml |
| **2** | manifest.json | MV3 + permissions |
| **2** | content.js | DOM hook, textarea 가로채기 |
| **2** | background.js | server 호출 + 매핑 보관 |
| **3** | fetch interceptor | ChatGPT API 가로채기 |
| **3** | response observer | 응답 DOM 후처리 |
| **4** | 검증 스크립트 | latency + BERTScore |
| **5** | 통합 테스트 | ChatGPT/Gemini/Claude 시연 |

## 9. 디렉터리 구조 (예정)

```
PrivacyFilter/
├── server/                       # Phase 1
│   ├── main.py                   # FastAPI app
│   ├── mask_service.py           # 마스킹/복원 로직
│   ├── alias_manager.py          # alias 풀 + 세션 매핑
│   └── requirements.txt          # fastapi, uvicorn 추가
├── extension/                    # Phase 2~3
│   ├── manifest.json             # MV3
│   ├── background.js             # service worker
│   ├── content.js                # DOM hook
│   ├── interceptor.js            # fetch override (injected)
│   ├── popup.html                # 옵션 UI
│   ├── popup.js
│   ├── icons/
│   └── ARCHITECTURE.md           # 본 문서
├── configs/
│   └── aliases.yaml              # alias 풀 정의
└── verification/                 # Phase 4
    └── latency_bench.py          # 처리 지연 시간 측정
```

## 10. 검증 계획 (Phase 4)

### Latency 측정
- 정규식 단계: 평균/p95/p99 ms
- NER 추론 단계: 평균/p95/p99 ms
- 네트워크 (Chrome ↔ FastAPI): 평균/p95/p99 ms
- 전체 E2E (사용자 입력 → 전송 직전): 평균/p95/p99 ms

목표: **E2E < 500ms** (사용자 체감 자연스러움)

### BERTScore 응답 품질
1. 평가 입력 50 개 (다양한 시나리오)
2. 각 입력 → GPT-4 / Gemini / Claude 응답 받기 (마스킹 X)
3. 같은 입력 마스킹 적용 → 같은 LLM 응답 받기 (마스킹 O)
4. 마스킹 응답을 unmask 한 결과 vs 미마스킹 응답 BERTScore 계산

목표: **BERTScore F1 ≥ 0.90** (응답 품질 보존)

---

다음 단계 (Phase 1):
- FastAPI 서버 구현
- /mask, /unmask, /healthz 엔드포인트
- aliases.yaml 작성 (PERSON/ORG/LOC/PROJ_N + 정규식 더미)
- iter10 모델 로딩 + 추론
- localhost:8000 에서 동작 확인
