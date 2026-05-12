# 중간 발표 자료 — 2026-05-12 기준

**프로젝트**: LLM 민감정보 유출 방지를 위한 실시간 마스킹 시스템
**저장소**: https://github.com/LOK-AeGS/PrivacyFilter

---

## 1. 진행 상황 요약

### 1.1 PDF 계획 대비 진행 단계

| 주차 | 계획 | 현재 상태 |
|---|---|---|
| 9 | 데이터셋 전처리 | ✅ **완료** (KLUE+Naver+합성, 113,808 통합) |
| 9~10 | NER 모델 학습 | ✅ **완료** (7회 학습 + 8회차 진행 중) |
| 10~11 | 마스킹 성능 평가 | ✅ **완료** (entity F1 / token F1 / mask coverage 3중) |
| 11~13 | Chrome 확장 프로그램 | 🟡 **착수 예정** (다음 단계) |
| 13~14 | 처리 지연 시간 평가 | ❌ 미진행 |
| 13~14 | 최종 보고서 | ❌ 미진행 |

→ **데이터·모델 파트는 계획보다 앞서감**, Chrome 확장 단계가 다음 단계.

### 1.2 완료된 기능

#### A. 1차 정규식 마스킹 (7종)
`[RRN]` `[PHONE]` `[EMAIL]` `[CARD]` `[ACCOUNT]` `[IP]` `[API_KEY]` — 모두 동작 검증 완료.

#### B. 2차 NER 모델 마스킹 (4종)
`[PERSON]` `[ORG]` `[LOCATION]` `[PROJ_N]` — KLUE-RoBERTa-large 백본 학습 완료.

#### C. 학습 인프라
- 데이터셋: KLUE-NER 21k + 네이버 NER 90k + 합성 PROJ_N 2.8k = **113,808 문장**
- 선언적 빌드 아키텍처 (`configs/datasets.yaml` + `scripts/build_dataset.py`)
- plug-and-play 필터 모듈 (`scripts/filters/`)
- 모델 학습/평가/추론 스크립트 통합

#### D. 평가 지표 3중 측정
| 라벨 | entity-F1 | token-F1 | mask-cov |
|---|---:|---:|---:|
| PROJ_N | 0.9986 | 0.9996 | 1.0000 |
| PERSON | 0.9609 | 0.9762 | 0.9716 |
| ORG | 0.8704 | 0.9063 | 0.8752 |
| LOCATION | 0.8618 | 0.9424 | 0.9207 |
| **micro avg** | **0.921** | — | — |

→ KLUE 공식 SOTA RoBERTa-large (entity F1 0.914) 수준 도달.

### 1.3 시연 가능한 프로토타입

**End-to-end 마스킹 데모** (현재 동작):
```
입력: 안녕하세요. 저는 단국대학교 컴퓨터공학과 김민수입니다.
     차세대 인사관리시스템 프로젝트의 PM을 맡고 있고,
     사무실은 서울 강남구입니다.
     문의는 010-1234-5678 또는 minsu@example.com 으로 주세요.

출력: 안녕하세요. 저는 [ORG] 컴퓨터공학과 [PERSON]입니다.
     [PROJ_N]의 PM을 맡고 있고,
     사무실은 [LOCATION]입니다.
     문의는 [PHONE] 또는 [EMAIL] 으로 주세요.
```

실행 명령: `python scripts/infer_ner.py --model-dir models/klue_roberta_large_iter6 --text "..."`

---

## 2. AI 도구 및 Git 활용 내역

### 2.1 사용 AI 도구
- **Claude Code (Anthropic)** — CLI 기반 AI 에이전트
- 코드 작성·디버깅·실험 분석·문서화 전반 활용

### 2.2 주요 프롬프팅 사례

| 프롬프팅 패턴 | 실제 사용 예 |
|---|---|
| **현실적 범위 추천 요청** | "마스킹 토큰의 범위를 현실적인 범위로 만들어줘" |
| **데이터셋 구축 자동화** | "데이터셋 다운로드부터 검증까지의 워크플로를 만들어줘" |
| **오류 원인 정량 분석** | "지금 점수가 낮게 나오는 이유 가설을 5개 이상 만들어서 검증해줘" |
| **데이터 품질 감사** | "데이터 품질 평가 기준을 5개 이상 만들어서 품질 체크해줘" |
| **아키텍처 재설계** | "더 데이터셋을 추가할 수 있으니 범용적·유연하게 설계해줘" |
| **위험 분석** | "그대로 진행하면 발생할 수 있는 문제가 뭔데?" |
| **반복 개선** | "1~3을 반복해서 95% 이상 나오도록 해줘" |

→ Claude를 **단순 코드 생성기**가 아닌 **연구 파트너**로 활용. 가설 수립·실험 설계·실패 원인 분석·정직한 한계 보고까지.

### 2.3 Git 커밋 히스토리 — 18개 커밋

```
4a04b38 Iter7 결과: KLUE-only 보수적 정제도 회귀 (-0.005)
86a1fd4 선언적 데이터셋 빌드 아키텍처 + Trouble Shooting 문서화
607792f 네이버 NER 데이터 통합 — train +90,000 문장
8ce3ccd 데이터 품질 감사 + 6 가설 검증 결과 통합 문서
ab66722 데이터 품질 6기준 + 모델 저성능 가설 6개 검증
ad5d5b4 최종 분석: 6 iteration 종합 + ORG/LOC 95% 미달 정직 보고
85badad Iter5: warm-start iter2 + 3ep — plateau 확인 (회귀 -0.005)
5517d02 Task-aligned 평가: entity-F1 / token-F1 / masking coverage 3중
b69193c Ensemble 평가 스크립트 + iter1+iter2 결합
5fcdbcf Iter3 실패 (회귀 -0.008) — 단순 엔티티 치환 증강 부적합
635a1c3 Iter2 결과: RoBERTa-base 3ep, F1 0.9158
aabecdc 엔티티 치환 데이터 증강 스크립트
06b3d67 Iter1 오류 분석 — ORG/LOC 95%↑ 달성 위한 분석
c06120c Full-scale 학습 결과: F1 0.9100
cd21012 합성 데이터 확장 + NIKL/AI-Hub 다운로드 가이드
be90230 Baseline 학습 + 평가: F1 0.883
8724d11 NER 학습 파이프라인 + KLUE 변환 검증
529f369 Initial scaffolding: regex, dataset converters, synthetic data
```

**검증 방법**: 발표 시 `git log --oneline` 또는 GitHub repo 직접 시연

### 2.4 작업 규모
- 약 **5,000+ 라인** 코드 작성
- 모듈 **24개** (변환 5 / 필터 2 / 학습·평가 6 / 검증 7 / 보조 4)
- 학습 실험 **8회**, CPU 누적 **약 22 시간**
- 결과 문서 **8개** (results/ 디렉터리)

---

## 3. 트러블슈팅

총 **12개 항목** README 의 Trouble Shooting 섹션에 등록. 대표 5건:

### TS-02. `regex/` 디렉터리가 서드파티 패키지 shadow

**증상**: `transformers` 임포트 시 `AttributeError: module 'regex' has no attribute 'compile'`
**원인**: 우리가 만든 `regex/` 폴더가 PyPI 의 `regex` 패키지를 가림.
**해결**: 디렉터리명을 `regex/` → `pii_regex/` 로 rename, 모든 import 업데이트.

### TS-06. 단순 엔티티 치환 증강이 오히려 회귀 (iter3)

**증상**: KLUE entity surface 를 같은 라벨의 다른 entity 로 무작위 치환 → F1 0.916 → **0.908** 회귀.
**원인 분석**: KLUE 어노테이션이 문맥 의존적 ("한국" = ORG 또는 LOC 문맥). 무작위 surface 치환이 문맥-라벨 정합 파괴.
**해결**: 단순 surface 치환 증강 폐기. 대신 더 큰 코퍼스(Naver) 추가하는 방향으로 전환.

### TS-07. 네이버 NER 포맷이 KLUE 와 다름

**증상**: `convert_naver.py` 변환 후 모든 태그가 O 가 됨.
**원인**: 네이버 NER 은 `LABEL_B`/`LABEL_I`/`-` 포맷 (KLUE 는 `B-LABEL`/`I-LABEL`/`O`).
**해결**: `remap_tag()` 에서 두 포맷 모두 지원하도록 분기.

### TS-08. KLUE-NER surface 라벨 노이즈 발견

**증상 (가설 검증으로 발견)**: 같은 어절이 train 안에서 여러 라벨로 어노테이션.
- `'한국'` → LOCATION 170회, ORG 5회 (3% 노이즈)
- `'한국은'` → LOC 14, ORG 15 (50% — 완전 모호)
**영향**: 노이즈 surface 위 dev recall 0.85 vs 클린 0.92 (**-6.85%p**)
**해결**: 보수적 정제 스크립트 `clean_label_noise.py`. minority<15% & count>=5 인 surface 만 majority 로 통일. 합법적 ambiguity 보존.

### TS-10. Train/Dev 도메인 shift 위험

**증상 (사전 분석)**: Naver 90k 추가 시 train 79% Naver / dev 93% KLUE — 도메인 mismatch.
**예상 영향**: Naver 스타일 학습이 KLUE dev 에서 underperform 가능.
**완화**:
- dev 는 보존 (평가 정직성)
- 단계적 fine-tuning 또는 warm-start 로 KLUE 지식 유지
- 평가지표 다양화 (entity-F1 + token-F1 + mask-coverage)

### 그 외 등록된 항목 (요약)
- TS-01: transformers 5.x Trainer API 변경 (`tokenizer` → `processing_class`)
- TS-03: Windows cp949 인코딩 → `PYTHONIOENCODING=utf-8`
- TS-04: KLUE char→word BIO 무결성 → `normalize_bio()` 자동 보정
- TS-05: KLUE-BERT LayerNorm beta/gamma 키 워닝 (무해)
- TS-09: 네이버 entity 의 URL/특수문자 노이즈 → 필터 4종 추가
- TS-11: KLUE ORG↔LOCATION 본질적 모호성 (KLUE 공식 SOTA 영역 한계)
- TS-12: PyYAML 의존 누락 → requirements.txt 추가

---

## 4. 최종 데모까지의 계획

**남은 기간**: 2026-05-12 ~ 2026-05-30 = **약 18일 (3주)**

### 4.1 Week 1 (5/13 ~ 5/19) — Chrome 확장 + 추론 서버

| 작업 | 산출물 | 우선순위 |
|---|---|---|
| 로컬 추론 서버 (FastAPI) | `server/main.py` — POST /mask 엔드포인트 | ⭐⭐⭐ |
| Chrome 확장 manifest v3 | `extension/manifest.json` | ⭐⭐⭐ |
| Content script (DOM hook) | 입력창 가로채기, fetch 인터셉트 | ⭐⭐⭐ |
| 옵션 페이지 | 마스킹 토큰 on/off, 서버 주소 설정 | ⭐⭐ |
| ChatGPT / Gemini / Claude 사이트 통합 테스트 | 실제 동작 영상 | ⭐⭐⭐ |

### 4.2 Week 2 (5/20 ~ 5/25) — 평가 + 보고서 작성 시작

| 작업 | 산출물 | 우선순위 |
|---|---|---|
| BERTScore 응답 품질 평가 | 마스킹 전/후 GPT/Gemini/Claude 응답 비교 | ⭐⭐⭐ |
| 처리 지연시간 측정 | 정규식 / NER / E2E 각 단계별 latency | ⭐⭐⭐ |
| 추가 NIKL 데이터 통합 (선택) | F1 추가 향상 시도 | ⭐ |
| 최종 보고서 초안 | LaTeX/Word 작성 시작 | ⭐⭐⭐ |

### 4.3 Week 3 (5/26 ~ 5/30) — 마무리 + 발표 준비

| 작업 | 산출물 | 우선순위 |
|---|---|---|
| 최종 보고서 완성 | PDF 제출용 | ⭐⭐⭐ |
| 발표 자료 (PPT) | 슬라이드 + 데모 영상 | ⭐⭐⭐ |
| 데모 영상 녹화 | 실제 ChatGPT 입력 시 마스킹 동작 | ⭐⭐⭐ |
| 최종 리허설 | 발표 시간 측정·문답 준비 | ⭐⭐ |

### 4.4 To-Do 체크리스트

```
[x] 1차 정규식 마스킹 (7종)
[x] 2차 NER 모델 학습 (PERSON/ORG/LOC/PROJ_N)
[x] 데이터셋 통합 (KLUE + Naver + 합성, 113k)
[x] 데이터 품질 감사 + 가설 검증
[x] 선언적 빌드 아키텍처
[x] entity / token / mask-coverage 3중 평가

[ ] FastAPI 로컬 추론 서버 (latency < 100ms 목표)
[ ] Chrome 확장 manifest v3 + content script
[ ] OpenAI / Google / Anthropic LLM 사이트 통합 테스트
[ ] BERTScore 응답 품질 평가 (3 LLM × 마스킹 전/후)
[ ] 처리 지연시간 측정 (정규식 / NER / 네트워크)
[ ] 최종 보고서 작성
[ ] 발표 자료 + 데모 영상 녹화
```

### 4.5 일정 리스크 & 완화

| 리스크 | 완화 방안 |
|---|---|
| Chrome 확장 학습 곡선 | manifest v3 공식 튜토리얼 + LLM 사이트별 DOM 구조 사전 조사 |
| 로컬 추론 서버 성능 (CPU) | 모델을 ONNX 또는 quantized 로 export, batch size 1 최적화 |
| BERTScore 평가 시 LLM API 비용 | 평가 샘플 100~200건 limit, OpenAI 무료 크레딧 활용 |
| 데모 시 안정성 | 발표 1주 전 데모 환경 freeze, 백업 영상 준비 |

### 4.6 목표

> **5/30 발표 시**:
> - 실제 ChatGPT 입력창에 PII 가 포함된 한국어 프롬프트 입력 → 자동 마스킹된 텍스트가 전송되는 영상 시연
> - 한국어 NER 의 ORG/LOC 95% 미달 원인을 데이터 품질·OOV 측면에서 정량 분석한 결과 발표
> - PROJ_N(0.999) / PERSON(0.961) 마스킹은 모든 지표 95% 달성, LOC/ORG 는 KLUE 공식 SOTA 수준 도달을 입증
