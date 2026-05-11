# Full-scale 학습: KLUE-BERT-base, 2 epochs

**실험 ID**: full_23k_2ep
**커밋 시점**: 2026-05-12

## 설정

| 항목 | 값 |
|---|---|
| 백본 | klue/bert-base (110M) |
| Train | 23,808 문장 (KLUE 21,008 + 합성 2,800) |
| Dev | 5,350 문장 (KLUE 5,000 + 합성 350) |
| Test | 350 문장 (합성 only) |
| Epochs | 2 |
| Batch size | 16 |
| Learning rate | 5e-5 |
| Weight decay | 0.01 |
| Warmup ratio | 0.1 |
| FP16 | OFF (CPU) |
| 환경 | torch 2.11.0+cpu, transformers 5.4.0, CPU 20코어 |

## 학습 로그

| Epoch | eval_loss | eval_f1 | PROJ_N | PERSON | ORG | LOCATION |
|---|---|---|---|---|---|---|
| 1 | 0.0555 | 0.9039 | 1.0000 | 0.9471 | 0.8550 | 0.8279 |
| 2 | 0.0546 | **0.9100** | 0.9986 | 0.9512 | 0.8612 | 0.8424 |

- train_runtime: 5,040 sec (**1시간 24분**)
- train_samples_per_second: 9.447
- final train_loss: 0.0744

## Dev 평가 (Epoch 2, best)

| 라벨 | F1 | Support |
|---|---|---|
| PROJ_N | 0.9986 | 348 |
| PERSON | 0.9512 | 4,188 |
| ORG | 0.8612 | 2,032 |
| LOCATION | 0.8424 | 1,513 |
| **micro avg** | **0.9100** | 8,081 |

- Precision: 0.9104
- Recall: 0.9097
- eval_loss: 0.0546

## Test 평가 (350 합성 문장)

```
              precision    recall  f1-score   support
    LOCATION     1.0000    1.0000    1.0000        19
         ORG     1.0000    1.0000    1.0000        31
      PERSON     1.0000    1.0000    1.0000        18
      PROJ_N     1.0000    1.0000    1.0000       348
   micro avg     1.0000    1.0000    1.0000       416
```

⚠️ **주의**: Test 가 train 과 동일 합성 템플릿 분포에서 추출되어 과대평가될 수 있음.
실사용 분포에서는 PROJ_N F1 ~0.93~0.97 수준으로 떨어질 가능성.

## 이전 실험과 비교 (동일 dev 분포)

| 라벨 | balanced 4.2k (3ep) | **full 23.8k (2ep)** | Δ |
|---|---|---|---|
| micro F1 | 0.8829 | **0.9100** | **+0.0271** |
| PERSON | 0.9380 | 0.9512 | +0.0132 |
| ORG | 0.8235 | 0.8612 | **+0.0377** |
| LOCATION | 0.8039 | 0.8424 | **+0.0385** |
| PROJ_N | 0.9834 | 0.9986 | +0.0152 |

→ ORG / LOCATION 이 가장 큰 폭으로 향상. KLUE train 6배 증가 효과를 직접 받는 라벨들.

## 정성 평가 (예시 문장)

원문:
> 안녕하세요. 저는 단국대학교 컴퓨터공학과 김민수입니다. 차세대 인사관리시스템 프로젝트의 PM을 맡고 있고, 사무실은 서울 강남구입니다. 문의는 010-1234-5678 또는 minsu@example.com 으로 주세요.

마스킹:
> 안녕하세요. 저는 [ORG]학과 [PERSON]입니다. [PROJ_N]의 PM을 맡고 있고, 사무실은 [LOCATION]입니다. 문의는 [PHONE] 또는 [EMAIL] 으로 주세요.

추출된 스팬:
- ORG: "단국대학교 컴퓨터공"  ← "학과" 부분이 약간 짧게 잘림 (학습 데이터의 ORG 경계 정의에 영향)
- PERSON: "김민수"
- PROJ_N: "차세대 인사관리시스템 프로젝트"
- LOCATION: "서울 강남구"
- PHONE: "010-1234-5678" (정규식)
- EMAIL: "minsu@example.com" (정규식)

## 알려진 한계

1. **ORG 경계 모호성**: "단국대학교 컴퓨터공학과" 처럼 학교+학과 결합 시 경계가 일관되지 않음 → KLUE 어노테이션 규칙을 따른 결과.
2. **PROJ_N test 1.0 은 과대평가**: 동일 템플릿 분포 결과. 실사용 검증 필요.
3. **NIKL / AI-Hub 미포함**: 수동 신청 필요. 합치면 LOCATION/ORG 추가 향상 기대.
4. **transformers 5.x LayerNorm 키 워닝**: 학습·평가에는 영향 없음 (구 KLUE 체크포인트의 beta/gamma → 신 weight/bias 명명 차이).

## 향후 개선 여지

- NIKL · AI-Hub 합쳐 LOCATION/ORG 보강 (F1 0.92+ 기대)
- 실제 ChatGPT 프롬프트 샘플 수집 후 도메인 평가셋 구축
- klue/roberta-large 비교 실험 (GPU 환경)
- PROJ_N 합성 데이터를 더 다양화 (현재 158 템플릿 × 233 사전 → 1,000+ 템플릿으로 확장 시 일반화 개선 기대)
