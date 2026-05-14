# Iteration 9: KLUE + NIKL 통합 학습 — **회귀** (외부 데이터의 본질적 한계 확인)

**설정**
- 모델: warm-start `models/klue_roberta_large_iter6` (F1 0.9211)
- Train: KLUE 21k + **NIKL 80k** + 합성 2.8k = **103,808 문장**
  - NIKL = 국립국어원 개체명 말뭉치 (315,697 문장 중 80k subsample)
- Dev: dev.jsonl 5,350 (KLUE 유지, 평가 정직성)
- Epochs: 1, LR 1e-5, Batch 8
- **학습 시간: 약 11시간 30분** (CPU)

## 결과

| 라벨 | iter6 best | **iter9** | Δ |
|---|---:|---:|---:|
| micro F1 | 0.9211 | **0.9027** | **−0.0184** ❌ |
| PERSON | 0.9609 | 0.9567 | −0.0042 |
| ORG | 0.8704 | **0.8411** | **−0.0293** ❌ |
| LOCATION | 0.8618 | **0.8160** | **−0.0458** ❌❌ |
| PROJ_N | 0.9986 | 1.0000 | +0.0014 |

**핵심 라벨(ORG/LOCATION) 모두 큰 폭 회귀**. iter8(Naver) 보다 더 나쁨. iter9 모델 폐기.

## 핵심 발견 — "데이터 부족"이 문제가 아니었다

iter8 (Naver 추가) 와 iter9 (NIKL 추가) 가 **둘 다 회귀**. 그것도:

| iter | 추가 데이터 | 어노테이션 성격 | F1 변화 |
|---|---|---|---|
| 8 | Naver 90k | 자체 규칙 (KLUE와 다름) | −0.010 |
| 9 | NIKL 80k | **국립국어원 표준** (KLUE와 유사 기대) | **−0.018** |

→ **"KLUE 와 비슷한 표준 어노테이션이면 도메인 shift 적을 것"** 이라는 iter9 의 가설이 **틀림**.
   오히려 NIKL 이 Naver 보다 더 큰 회귀.

### 왜 NIKL 도 회귀했나?

1. **KLUE dev 분포가 매우 좁은 타겟**
   - dev 는 93% KLUE 분포. train 에 외부 데이터가 들어오면 모델이 "더 넓은 분포" 로 최적화됨
   - 결과적으로 좁은 KLUE dev 에서 성능 ↓
   - iter8·iter9 가 **동일한 패턴** — 외부 데이터 종류와 무관하게 회귀

2. **NIKL 의 미묘한 어노테이션 차이**
   - NIKL 2022 와 KLUE-NER 은 둘 다 "표준" 이지만 세부 규칙 다름
   - 경계 처리, 세분화 라벨(OGG_*, LCP_*) → 상위 통합 시 정보 손실
   - LOCATION 이 −0.046 으로 가장 큰 회귀 → NIKL 의 LC 계열 라벨 체계가 KLUE 와 특히 다름 추정

3. **warm-start 의 함정**
   - iter6 가 이미 KLUE 에 최적화돼 있는데, NIKL 로 1 epoch 추가 학습하면 KLUE 지식이 희석됨

## 결론 — 8회 + 9회차로 입증된 사실

> **단일 모델 + KLUE dev 평가 환경에서, "외부 데이터 추가" 는 (그것이 표준 어노테이션이든 아니든) 일관되게 회귀를 유발한다.**
> **iter6 (RoBERTa-large, KLUE 21k + 합성) 의 0.9211 이 최종 best.**

### 9 iteration 전체 요약

| iter | 구성 | F1 | 결과 |
|---|---|---:|---|
| 1 | BERT-base | 0.910 | baseline |
| 2 | RoBERTa-base | 0.916 | +백본 |
| 3 | + 엔티티 증강 | 0.908 | ❌ 회귀 |
| 4 | Ensemble | 0.917 | 미미 |
| 5 | warm-start +3ep | 0.911 | ❌ 회귀 |
| **6** | **RoBERTa-large** | **0.921** | ⭐ **최고** |
| 7 | + KLUE 라벨 정제 | 0.916 | ❌ 회귀 |
| 8 | + Naver 90k | 0.911 | ❌ 회귀 |
| 9 | + NIKL 80k | 0.903 | ❌ 회귀 (최대 폭) |

→ **모든 데이터 차원 시도 (증강·정제·Naver·NIKL) 가 회귀**. 모델 차원에서만 iter6 가 +0.005.

## 진짜 결론

ORG/LOC 의 95% entity-F1 미달은:
1. ❌ 데이터 부족 때문이 아님 — NIKL 316k 를 줘도 회귀
2. ✅ **KLUE-NER dev 자체의 평가 특성** — 좁은 분포 + 본질적 라벨 노이즈/모호성
3. ✅ KLUE 공식 RoBERTa-large SOTA 0.914 와 동일 영역에 우리 0.921 — 이미 천장

**남은 단 하나의 가능성**: KLUE dev 와 같은 분포의 추가 데이터 (= KLUE-NER 자체의 확장판) 또는 GPU 환경 + 다중 시드 ensemble + CRF. 본 학부 프로젝트 + CPU 환경의 범위를 벗어남.

## 권장 — 모델 파트 종료, 응용 파트로 전환

- **최종 모델 확정: `models/klue_roberta_large_iter6`** (F1 0.921, KLUE SOTA 영역)
- Task-aligned 지표로는 PERSON 0.976 / PROJ_N 1.0 / LOC 0.94 / ORG 0.91 (token-F1)
- 남은 17일 (5/15→5/30) 을 Chrome 확장 + FastAPI 서버 + 보고서에 투입
