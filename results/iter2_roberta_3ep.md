# Iteration 2: klue/roberta-base, 3 epochs, lr 3e-5

**모델**: `models/klue_roberta_iter2`
**학습 시간**: 7,361 sec (**2시간 3분**), CPU 20코어, 9.70 samples/sec
**데이터**: train 23,808 / dev 5,350 / test 350

## 에폭별 dev F1

| Epoch | micro F1 | PERSON | ORG | LOCATION | PROJ_N |
|---|---|---|---|---|---|
| 1 | 0.9074 | 0.9514 | 0.8550 | 0.8354 | 1.0000 |
| 2 | 0.9128 | 0.9537 | 0.8621 | 0.8487 | 1.0000 |
| **3** | **0.9158** | **0.9552** | **0.8700** | **0.8502** | **1.0000** |

## Iter 1 (BERT-base, 2ep) 대비

| 라벨 | Iter1 | Iter2 | Δ |
|---|---|---|---|
| micro F1 | 0.9100 | 0.9158 | +0.0058 |
| PERSON | 0.9512 | 0.9552 | +0.0040 |
| ORG | 0.8612 | 0.8700 | +0.0088 |
| LOCATION | 0.8424 | 0.8502 | +0.0078 |
| PROJ_N | 0.9986 | 1.0000 | +0.0014 |

## 분석

- 백본 RoBERTa 교체 + 에폭/lr 조정으로 모든 라벨 소폭 향상.
- 단, **KLUE 논문에서 보고된 BERT→RoBERTa +3.8%p 향상은 재현되지 않음**.
  - 가능 원인: 본 실험의 평가는 entity-level micro F1 (엄격), KLUE 논문은 char-level micro F1 (관대).
  - 실제로 char-level 로 측정하면 +2~3%p 가능성.
- ORG/LOCATION 의 95% 도달까지 격차가 여전히 큼 (각 -0.08, -0.10).

## 95% 도달 가능성 평가

KLUE-NER 의 ORG/LOCATION 은 어노테이션 자체에 본질적 노이즈가 있음 (국가명의 ORG↔LOC 문맥 의존, 조사 부착 경계 등). KLUE 공식 leaderboard 의 RoBERTa-large entity F1 도 0.91~0.92 수준. 95% 도달은 SOTA 영역이며 단일 모델 단일 데이터로는 매우 어려움.

**개입 가능 영역**:
1. 엔티티 표면 변형 증강 (iter 3) — +1~2% 기대
2. 다중 시드 ensemble — +1~2% 기대
3. roberta-large (GPU 필요)
4. NIKL/AI-Hub 추가 데이터 (사용자 다운로드 필요)

## Iteration 3 계획

- 학습 데이터에 엔티티 치환 증강 적용 (`augment_entity.py`, --only-labels ORG LOCATION, k=2, p=0.8)
- Iter2 모델에서 warm-start, 1 epoch 추가 학습
- 기대 시간: ~2시간
