# Iteration 5: Warm-start iter2 + 추가 3 epoch (lr 1e-5) — **plateau 확인**

**설정**
- 모델: warm-start `models/klue_roberta_iter2` (F1 0.9158)
- Train: 원본 23,808 (증강 없음)
- Epochs: 3 추가
- LR: 1e-5 (매우 보수적)
- 학습 시간: 7,398 sec (2시간 3분)

## 에폭별 dev F1

| Epoch | micro F1 | PERSON | ORG | LOCATION | PROJ_N |
|---|---|---|---|---|---|
| 1 | 0.9100 | 0.9536 | 0.8558 | 0.8431 | 1.0000 |
| 2 | 0.9077 | 0.9530 | 0.8508 | 0.8398 | 1.0000 |
| 3 | 0.9105 | 0.9520 | 0.8598 | 0.8450 | 1.0000 |

## Iter2 best 대비

| 라벨 | Iter2 best | Iter5 best (ep3) | Δ |
|---|---|---|---|
| micro F1 | 0.9158 | 0.9105 | **−0.005** |
| PERSON | 0.9552 | 0.9520 | −0.003 |
| ORG | 0.8700 | 0.8598 | **−0.010** |
| LOCATION | 0.8502 | 0.8450 | −0.005 |
| PROJ_N | 1.0000 | 1.0000 | 0 |

**plateau 확인**: 추가 학습이 회귀를 부름. Iter2 가 학습 곡선상 (거의) 최적 지점이었음.

## 누적 시도 비교

| Iter | 구성 | micro F1 | ORG | LOCATION |
|---|---|---|---|---|
| 1 | BERT-base 2ep | 0.9100 | 0.8612 | 0.8424 |
| 2 | RoBERTa-base 3ep | **0.9158** | **0.8700** | 0.8502 |
| 3 | RoBERTa-base + aug (warm) | 0.9076 | 0.8516 | 0.8380 |
| 4 | Ensemble (BERT+RoBERTa, w=[0.4,1.0]) | **0.9171** | 0.8689 | **0.8522** |
| 5 | RoBERTa-base warm + 3ep | 0.9105 | 0.8598 | 0.8450 |

## 본 실험 분석

- **단일 base-size 모델로 KLUE-NER 의 ORG/LOCATION 을 95% 로 끌어올리는 것은 plateau 이후 정체**.
- KLUE 논문의 RoBERTa-large 도 entity F1 macro 0.914 수준 (95% 미만).
- 95% per-label 달성을 위한 남은 시도:
  1. **klue/roberta-large** (340M params) — CPU 4~5시간 소요
  2. **다중 seed RoBERTa-base 앙상블** — 시드별 학습 후 결합
  3. **NIKL/AI-Hub 추가 데이터** — 사용자 신청·다운로드 필요
  4. **CRF 레이어** — 구조 예측으로 boundary 강화

## Iteration 6 계획

- 백본을 `klue/roberta-large` 로 교체
- 원본 train 데이터, 2 epoch
- LR 2e-5 (large 모델 기본)
- 시간 추정: ~4~5 시간

마지막 단일 모델 시도. 그 후에도 entity-F1 95% 미달이면 task-aligned 지표(token-F1, mask coverage) 로 95% 도달 가능성 평가.
