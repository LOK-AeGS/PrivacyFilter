# Iteration 3: 엔티티 치환 증강 + Warm-start — **실패 (회귀)**

**설정**
- 모델: warm-start `models/klue_roberta_iter2` (F1 0.9158)
- Train: `train_aug_orgloc.jsonl` (71,424 = 원본 23,808 + augmented 47,616, ORG/LOCATION 만 치환)
- Epochs: 1
- LR: 2e-5 (warm-start 안정성 위해 낮춤)
- 학습 시간: 7,190 sec (2시간)

## 결과

| 라벨 | Iter2 (best) | **Iter3** | Δ |
|---|---|---|---|
| micro F1 | 0.9158 | 0.9076 | **−0.008** |
| PERSON | 0.9552 | 0.9524 | −0.003 |
| ORG | **0.8700** | 0.8516 | **−0.018** |
| LOCATION | **0.8502** | 0.8380 | **−0.012** |
| PROJ_N | 1.0000 | 1.0000 | 0 |

**모든 라벨 회귀**. 평가에서는 사용하지 않음.

## 원인 분석

1. **무작위 엔티티 치환이 KLUE 의 문맥 의존 라벨링을 파괴**.
   - KLUE 에서 "한국", "러시아" 등은 문맥에 따라 ORG(국가 행위주체) 또는 LOC(지리). 무작위로 surface 만 바꾸면 라벨↔context 정합이 깨짐.
   - 예: 원본 "벨기에와 6월 17일 브라질 상파울루에서 경기" → 증강 "미국 캘리포니아에서 ... 충남 부여군 가이아나의 ..." 같이 의미 붕괴.
2. **train_loss 0.021 (매우 낮음) vs eval 회귀** — 노이즈 학습으로 과적합.
3. **치환 안 한 PERSON 도 회귀** — 노이즈 문장이 전반적 학습을 흔듦.

## 교훈

- **단순 surface 치환은 KLUE 같이 어노테이션이 의미·문맥 의존적인 데이터셋에 부적합**.
- 효과 있으려면 의미 보존 증강이 필요: paraphrase, back-translation, 또는 컨텍스트 보존 entity swap.
- ORG↔LOCATION 의 95% 달성은 augmentation 만으로는 비현실적.

## Iter 4 계획

- Warm-start iter2 유지 (iter3 모델 폐기)
- **원본 train.jsonl** (증강 없음) 추가 학습
- Epochs 2, lr 1e-5 (더 보수적)
- 기대: iter2 의 학습 부족분 보완으로 +0.5~1.5% 가능 (95% 달성은 어렵지만 ceiling 탐색)
