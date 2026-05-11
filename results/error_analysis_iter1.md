# Iteration 1: 오류 분석

**모델**: `models/klue_bert_ner_full` (KLUE-BERT-base, 2 epochs, F1 0.9100)
**Dev**: 5,350 문장
**도구**: `scripts/error_analysis.py`

## 오류 카테고리

| 카테고리 | PERSON | ORG | LOCATION | PROJ_N |
|---|---|---|---|---|
| missed | 126 | **138** | 68 | 0 |
| boundary | 76 | 70 | **88** | 0 |
| type | 14 | **91** | 58 | 0 |
| extra | 97 | 130 | 98 | 1 |

`missed` = 예측에 누락 / `boundary` = 같은 라벨이지만 경계 다름 / `type` = 위치는 같지만 라벨 다름 / `extra` = FP

## 주요 패턴 (정성 분석)

### 1. ORG ↔ LOCATION 혼동 (type 149건)
국가명이 문맥에 따라 ORG(국가 행위주체) 또는 LOCATION(지리)으로 어노테이션됨.
```
gold=ORG '러시아'      pred=LOCATION '러시아'
gold=ORG '브라질'      pred=LOCATION '브라질'
gold=ORG '한국의'      pred=LOCATION '한국의'
gold=LOCATION '남북'   pred=ORG '남북'
```

### 2. 긴 복합 엔티티 under-extension (boundary)
모델이 안전한 짧은 스팬을 선호.
```
gold='서울대 경영대학에'  pred='서울대'
gold='단국대천안병원 응급실로'  pred='단국대천안병원'
gold='대구 중구 경북대 사범대학부설고등학교'  pred='사범대학부설고등학교'
```

### 3. 조사 붙은 어절 missed
```
gold=ORG '외환은행장' / '하나은행장과' / 'S병원을'
gold=LOCATION '수도권과' / '평택시장,' / '수도권시청률'
```

### 4. KLUE 어노테이션 자체의 미묘함 (extra)
모델이 명사를 엔티티로 분류했지만 KLUE 가 태그 안 한 케이스.
```
pred=ORG 'SBS' / '노동당' / '경찰에'  — gold 에는 없음
pred=LOCATION '(건대입구점)' / 'KBS'  — gold 에는 없음
```

## 시사점

- **백본 교체 필요**: ORG↔LOCATION 혼동을 줄이려면 더 좋은 context representation. KLUE 논문 기준 RoBERTa-base 가 BERT-base 대비 entity macro F1 +3.8%.
- **추가 에폭**: 미세 경계 학습에 더 많은 step 필요.
- **데이터 증강 (후속)**: 같은 entity 의 변형 표면(particles 부착)을 더 다양하게.
- **CRF 레이어 (후속)**: BIO 시퀀스 일관성 강화 — boundary 오류 감소 기대.

## Iteration 2 계획

1. 백본 `klue/bert-base` → `klue/roberta-base`
2. Epochs 2 → 3
3. Learning rate 5e-5 → 3e-5 (좀 더 안정적 학습)
4. 나머지(batch, weight decay, warmup) 동일
5. 전체 23,808 train / 5,350 dev 유지

기대치: micro F1 0.93+, ORG/LOCATION 각각 0.90+
