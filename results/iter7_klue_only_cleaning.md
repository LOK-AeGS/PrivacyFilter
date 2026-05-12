# Iteration 7: KLUE-only 보수적 라벨 정제 + Warm-start — **회귀**

**설정**
- 모델: warm-start `models/klue_roberta_large_iter6` (F1 0.9211)
- Train: `train_cleaned.jsonl` (23,808, KLUE+합성, 75 entity 정제)
- Dev: dev.jsonl 5,350 (그대로)
- Epochs: 1
- LR: 1e-5
- 학습 시간: 약 2시간 6분

## 결과

| 라벨 | Iter6 best | Iter7 | Δ |
|---|---:|---:|---:|
| micro F1 | 0.9211 | 0.9159 | **−0.005** |
| PERSON | 0.9609 | 0.9620 | +0.001 |
| ORG | 0.8704 | 0.8580 | **−0.012** |
| LOCATION | 0.8618 | 0.8480 | **−0.014** |
| PROJ_N | 0.9986 | 0.9957 | −0.003 |

**모든 핵심 라벨 회귀**. iter7 모델 폐기.

## 원인 분석

- 정제 규모 너무 작음: 29 surface, 75 entity 만 변경
- warm-start + 낮은 lr + 1 epoch 으로 미세 수정만 가능
- 정제 자체가 일부 legitimate ORG 케이스를 LOCATION 으로 잘못 변경했을 가능성
  (예: '서울시는' KLUE ORG 24회를 LOCATION 으로 → KLUE dev 에 서울시 ORG 케이스 있으면 손해)

## Iter8 계획

데이터 자체를 KLUE+Naver+synthetic 통합 (113,808)으로 확장하고 새 빌드 파이프라인 적용:
- `build_dataset.py` 산출 train.jsonl (URL 필터 + 보수적 정제 적용)
- warm-start iter6 large
- 1 epoch, lr 1e-5
- 예상 시간: ~10.5 시간 (CPU)

기대: OOV 일반화 (H6) 개선으로 ORG/LOC unseen recall 향상.
