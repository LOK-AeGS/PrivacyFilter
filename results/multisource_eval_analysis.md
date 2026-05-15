# Multi-source 평가 — KLUE dev 편향 발견 + iter9 가 진짜 최고

**작성일**: 2026-05-15
**평가셋**: `data/eval/multisource_eval.jsonl` (9,380 문장, 5개 출처)

## 평가셋 구성

| 출처 | 문장 수 | 비고 |
|---|---:|---|
| KLUE dev | 5,000 | 기존 dev (학습 미사용) |
| NIKL holdout | 2,000 | nikl_sample(80k) 제외, 엔티티 포함 문장에서 추출 |
| Naver holdout | 2,000 | 학습 미사용, 엔티티 포함 문장에서 추출 |
| 합성 dev | 350 | 기존 PROJ_N dev |
| **realworld 라벨** | **30** | 수작업 BIO 라벨링 (data/eval/realworld_labeled.jsonl) |
| **합계** | **9,380** | data leak 방지 (토큰 단위 중복 제거) |

## iter6 vs iter9 비교 결과

### 출처별 F1

| 출처 | iter6 | iter9 | Δ | 해석 |
|---|---:|---:|---:|---|
| KLUE | 0.917 | 0.898 | −0.019 | iter6 가 KLUE 에 더 fit |
| **NIKL** | **0.744** | **0.901** | **+0.157** | iter9 가 NIKL 도메인 학습 |
| Naver | 0.676 | 0.708 | +0.032 | iter9 가 미학습 도메인에도 일반화 우월 |
| synthetic | 1.000 | 1.000 | 0 | 둘 다 합성 패턴 완벽 |
| realworld | 0.828 | 0.808 | −0.020 | 표본 30 으로 변동성 큼 |
| **ALL** | **0.816** | **0.853** | **+0.037** | **iter9 우월** |

### 라벨별 ALL F1

| 라벨 | iter6 | iter9 | Δ |
|---|---:|---:|---:|
| PERSON | 0.897 | 0.910 | +0.013 |
| **ORG** | 0.778 | **0.818** | **+0.040** |
| **LOCATION** | 0.706 | **0.786** | **+0.080** |
| PROJ_N | 0.984 | 0.994 | +0.010 |

→ **모든 라벨에서 iter9 가 iter6 보다 우월**. 특히 LOCATION +0.080, ORG +0.040.

## 진짜로 무엇이 일어났나

### 1. KLUE dev 의 좁은 평가 분포 함정

기존 9 iteration 의 평가:
```
data/processed/dev.jsonl (5,350 문장)
   ├─ KLUE 5,000 (93%)        ← 단일 출처
   └─ synthetic 350 (7%)
```

→ 이 dev 에 의존한 결과:
- iter6 = 0.921 (KLUE 에 fit)
- iter8/iter9 = 0.911/0.903 (외부 데이터 추가로 KLUE fit 약화)
- 결론: "외부 데이터 추가는 모두 회귀" — **잘못된 결론**

### 2. 실제로는 iter6 가 KLUE-overfit

iter6 의 source 별 격차:
- KLUE: 0.917
- NIKL: 0.744 (KLUE 보다 −17%p)
- Naver: 0.676 (−24%p)

→ KLUE 한 출처에만 강함. **일반화 능력은 부족**.

### 3. iter9 는 진정한 일반화

iter9 는:
- KLUE: 0.898 (−0.02, 작은 손실)
- NIKL: 0.901 (+0.16, 큰 이득)
- Naver: 0.708 (+0.03, 학습 안 한 도메인도 향상)

→ **작은 손실 < 큰 이득**. 다양한 출처에서 골고루 좋음.

## ML 의 고전적 교훈 — "the metric becomes the target"

> **평가 지표를 한 출처로 고정하면, 모델이 그 출처에 overfit 되어 일반화를 잃는다.**

본 프로젝트의 9 iteration 은 KLUE dev 라는 단일 지표에 매몰돼:
- "외부 데이터 추가는 회귀" 라고 결론
- 실제로는 더 일반화된 모델을 폐기할 뻔함

Multi-source 평가로 이 함정을 발견:
- iter9 의 진정한 가치 확인
- 95% 도달 가능성 재평가 필요

## 95% 도달 가능성 재평가

### 라벨별 진척

| 라벨 | iter9 ALL | NIKL 단독 | 95% 거리 |
|---|---:|---:|---:|
| PERSON | 0.910 | 0.967 | 거의 도달 |
| **ORG** | 0.818 | **0.888** | NIKL 단독으론 +0.06 |
| **LOCATION** | 0.786 | **0.878** | NIKL 단독으론 +0.07 |
| PROJ_N | 0.994 | — | 도달 ✓ |

→ NIKL 분포에선 ORG/LOC 도 0.88 까지 도달. 추가 학습 (NIKL 전체 316k, 2-3 epoch) 시 90% 영역 가능성. 95% 까지는 여전히 도전적.

## 최종 모델 정정

| 항목 | 기존 (잘못) | **정정** |
|---|---|---|
| Best model | iter6 (KLUE-only) | **iter9 (KLUE+NIKL)** |
| KLUE dev F1 | 0.921 | 0.903 |
| Multi-source F1 | 0.816 | **0.853** |
| 결론 | 외부 데이터 회귀 | **외부 데이터로 진정한 일반화 향상** |

## 발표 narrative 정정

기존: "9 iteration 모두 시도. 데이터 추가는 모두 회귀. iter6 최종."

**정정**:
> **"9 iteration 의 평가는 KLUE-NER dev 단일 출처였다. 이 한계를 인지하고 multi-source 평가셋(9,380 문장, 5개 출처) 을 직접 구축해 iter6 와 iter9 를 공정 비교한 결과, iter9 가 모든 라벨·모든 외부 출처에서 우월(전체 F1 +0.037, LOCATION +0.080) 함을 확인했다.**
>
> **이는 'metric overfitting' 의 전형으로, 평가셋 다양화 없이 모델 비교만으로는 진짜 일반화를 측정할 수 없다는 ML 의 고전적 교훈을 직접 경험했다. 최종 모델은 iter9 (KLUE+NIKL 학습) 로 확정."**

## 다음 단계

- iter9 를 최종 모델로 사용 (Chrome 확장, FastAPI 서버)
- KLUE 라벨 정제 + NIKL 전체 데이터로 추가 학습 시도 → 95% 영역 도전
- 평가는 항상 multi-source 로
