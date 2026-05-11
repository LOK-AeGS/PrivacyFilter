# Baseline: KLUE-BERT-base, balanced training

**실험 ID**: balanced_4200_3ep
**실행 일자**: 2026-05-11
**커밋**: 8724d11 + 본 결과

## 설정

| 항목 | 값 |
|---|---|
| 백본 | klue/bert-base (110M) |
| Optimizer | AdamW (default) |
| Learning rate | 5e-5 |
| Weight decay | 0.01 |
| Warmup ratio | 0.1 |
| Epochs | 3 |
| Batch size | 16 |
| Max length | 256 |
| FP16 | OFF (CPU) |
| 환경 | Windows 10, torch 2.11.0+cpu, transformers 5.4.0, CPU 20코어 |

## 데이터

| 분할 | 출처 | 문장 수 |
|---|---|---|
| Train (balanced) | KLUE 3,000 + 합성 1,200 | 4,200 |
| Dev | KLUE 5,000 + 합성 150 | 5,150 |
| Test | 합성 only | 150 |

## 학습 로그

```
Epoch 1: eval_f1 = 0.8728 (PROJ_N 0.9769)
Epoch 2: eval_f1 = 0.8817 (PROJ_N 0.9834)
Epoch 3: eval_f1 = 0.8829 (PROJ_N 0.9834)  ← best
```

- train_runtime: 1,582 sec (26분 22초)
- train_samples_per_second: 7.96
- final train_loss: 0.1027

## Dev 평가 (Epoch 3, best)

| 라벨 | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| PERSON | — | — | 0.9380 | 4,188 |
| ORG | — | — | 0.8235 | 2,032 |
| LOCATION | — | — | 0.8039 | 1,513 |
| **PROJ_N** | — | — | **0.9834** | 148 |
| **micro avg** | **0.8777** | **0.8882** | **0.8829** | 7,881 |

(eval_loss: 0.0870)

## 정성 평가 (예시 문장)

원문:
> 안녕하세요. 저는 단국대학교 컴퓨터공학과 김민수입니다. 차세대 인사관리시스템 프로젝트의 PM을 맡고 있고, 사무실은 서울 강남구입니다. 문의는 010-1234-5678 또는 minsu@example.com 으로 주세요.

마스킹:
> 안녕하세요. 저는 [ORG] 컴퓨터공학과 [PERSON]입니다. [PROJ_N]의 PM을 맡고 있고, 사무실은 [LOCATION]입니다. 문의는 [PHONE] 또는 [EMAIL] 으로 주세요.

추출된 스팬:
- ORG: "단국대학교"
- PERSON: "김민수"
- PROJ_N: "차세대 인사관리시스템 프로젝트"
- LOCATION: "서울 강남구"
- PHONE: "010-1234-5678" (정규식)
- EMAIL: "minsu@example.com" (정규식)

## 비교: 균형 학습 효과

| 실험 | Train 구성 | Dev F1 | PROJ_N F1 | 비고 |
|---|---|---|---|---|
| KLUE-biased | 3,000 (KLUE 다수) | 0.870 | **0.000** | 합성 누락 |
| Balanced | 4,200 (KLUE 3k + 합성 all) | **0.883** | **0.983** | 본 실험 |

→ 합성 데이터를 빠뜨리지 않게 표본을 잡으면, 다른 라벨 성능 저하 없이 PROJ_N 학습 가능.

## 향후 개선 여지

- 전체 KLUE train(21,008)을 사용한 본격 학습 (GPU 필요, ~30분/epoch)
- 국립국어원·AI-Hub 데이터 합쳐 LOCATION/ORG 보강
- 합성 데이터 다양화 (현재 PROJ_N 0.98 은 템플릿 의존 가능성)
- ELECTRA / RoBERTa 백본 비교
