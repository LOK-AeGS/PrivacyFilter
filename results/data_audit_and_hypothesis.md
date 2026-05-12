# 데이터 품질 감사 + 모델 저성능 가설 검증

**목적**: 데이터셋이 제대로 마스킹·정제되었는지, 95% 미달의 근본 원인이 무엇인지 정량 검증.

## Part 1 — 데이터 품질 6기준 평가

### C1. 라벨 일관성: ⚠️ 노이즈 확인

같은 어절 surface 가 train 안에서 여러 라벨로 어노테이션된 비율.

| 분할 | unique surface | inconsistent | 비율 |
|---|---:|---:|---:|
| train | 18,043 | 168 | **0.93%** |
| dev | 6,438 | 48 | 0.75% |
| test | 354 | 0 | 0.00% |

대표 노이즈 (train):
```
'한국'    → LOCATION 170,  ORG  5   (3%)
'미국'    → LOCATION 154,  ORG 10   (6%)
'북한의'  → ORG  47,       LOCATION 25  (35% — inherent ambiguity)
'한국은'  → LOCATION 14,   ORG 15   (50% — full ambiguity)
'한국이'  → LOCATION 10,   ORG  6   (38%)
```

→ **KLUE 의 어노테이션이 국가명·국가행위주체의 문맥 구분에서 일관성 없음**.

### C2. BIO 무결성 (확장): ✅ 깨끗

| 검사 | train | dev | test |
|---|---:|---:|---:|
| I-X without B-X | 0 | 0 | 0 |
| label switch in span | 0 | 0 | 0 |
| consecutive B-same-label | 1,977 | 636 | 0 |
| zero-length entity | 0 | 0 | 0 |

`consecutive B-B 같은 라벨` 은 정상 (인접한 두 별개 엔티티). 무결성 위반 없음.

### C3. 경계/조사 일관성: ⚠️ 심각한 변이

같은 entity base 가 train 에서 여러 끝글자(조사 부착 결과)로 등장한 비율.

| 분할 | (lbl, base) 조합 | 변이 케이스 | 비율 |
|---|---:|---:|---:|
| train | 15,209 | 836 | **5.50%** |
| dev | 5,822 | 296 | 5.08% |

대표 (train):
```
LOCATION|미국 → 끝글자: '국'(154), '서'(22), '에'(11), '의'(6), '을'(1), ...  19종
LOCATION|경기 → 끝글자: '기'(8), '시'(9), '서'(11), '도'(1), 'A'(1), ...      19종
PERSON|김     → '김'(28), '의'(1), '이'(2), '수'(1)                            4종
```

→ KLUE 어절 단위 어노테이션이 entity 에 조사 포함/제외를 일관성 없게 처리. "미국" vs "미국에서" 가 모두 LOCATION 으로 잡힘.

### C4. 중복 / 데이터 leak: ✅ 거의 없음

| 분할 | 중복 / 전체 | 비율 |
|---|---:|---:|
| dev ∩ train | 1 / 5,350 | 0.02% |
| test ∩ train | 0 / 350 | 0.00% |

→ Leak 없음.

### C5. source × 라벨 분포

| 분할 | source | LOCATION | ORG | PERSON | PROJ_N |
|---|---|---:|---:|---:|---:|
| train | klue | 6,254 | 7,925 | 13,600 | 0 |
| train | synthetic | 139 | 188 | 197 | 2,784 |
| dev | klue | 1,493 | 1,994 | 4,150 | 0 |
| dev | synthetic | 23 | 33 | 31 | 348 |
| test | synthetic | 19 | 31 | 18 | 348 |

→ PROJ_N 은 합성에만, KLUE 라벨(LOC/ORG/PERSON)은 KLUE 가 대다수. 의도된 분포.

### C6. 엔티티 길이 분포

| 분할 | 라벨 | n | mean | median | p95 | max |
|---|---|---:|---:|---:|---:|---:|
| train | PERSON | 13,797 | 1.12 | 1 | 2 | 5 |
| train | ORG | 8,113 | 1.15 | 1 | 2 | 8 |
| train | LOCATION | 6,393 | 1.27 | 1 | 3 | 7 |
| train | PROJ_N | 2,784 | 3.23 | 3 | 4 | 5 |

→ KLUE 엔티티 대부분 1~2어절, PROJ_N(합성)은 3어절 평균. 비정상값 없음.

## Part 2 — 모델 저성능 가설 6개 검증

대상 모델: `models/klue_roberta_large_iter6` (entity F1 0.9211)

### H1. 라벨 노이즈 영향: ⚠️ 강한 영향 (−6.85%p)

train 라벨 노이즈 surface (≥2 라벨, 168개) 위 dev gold 엔티티 vs 클린 surface 비교.

| 영역 | dev gold n | entity recall |
|---|---:|---:|
| 노이즈 surface 위 | 330 | **0.8545** |
| 클린 surface 위 | 7,742 | **0.9230** |
| 격차 | | **−6.85%p** |

→ 노이즈 학습 신호가 직접 dev 성능 끌어내림.

### H2. 조사 부착 비일관: ✅ 영향 작음

3개 이상 끝글자로 등장한 base 의 dev recall.

| 영역 | dev gold n | recall |
|---|---:|---:|
| 경계 변이 base | 1,319 | 0.9227 |
| 경계 일관 base | 6,753 | 0.9197 |

→ 차이 없음. 모델이 조사 변이를 의외로 잘 처리.

### H3. 클래스 불균형: ✅ 직접 영향 작음

| 라벨 | train n | dev n | dev recall |
|---|---:|---:|---:|
| PERSON | 13,797 | 4,181 | 0.9581 |
| ORG | 8,113 | 2,027 | 0.8614 |
| LOCATION | 6,393 | 1,516 | 0.8760 |
| PROJ_N | 2,784 | 348 | 1.0000 |

→ LOCATION(6.4k)이 ORG(8.1k)보다 적은데 recall 더 높음. 빈도만으로 설명 안 됨.

### H4. 엔티티 길이별 성능: ⚠️ 길수록 급락

| 길이 | PERSON | ORG | LOCATION | PROJ_N |
|---:|---:|---:|---:|---:|
| 1 | 0.963 | 0.878 | 0.895 | — |
| 2 | 0.933 | 0.789 | 0.834 | 1.000 |
| 3 | 0.892 | 0.692 | 0.798 | 1.000 |
| 4 | 1.000 | 0.750 | 0.781 | 1.000 |
| 5 | — | **0.500** | **0.500** | 1.000 |
| 6 | — | — | 1.000 | — |

→ ORG/LOC len ≥ 3 부터 70%대로, len 5 에선 50% 까지 떨어짐.
   PROJ_N 은 합성으로 학습된 surface 가 그대로 dev 에 등장해 100%.

### H5. 국가명 모호성: ⚠️ KLUE 어노테이션 한계

| surface | train ORG | train LOC | dev gold | model recall |
|---|---:|---:|---|---|
| 한국 | 5 | 170 | LOC=28/ORG=1 | 28/29 |
| 한국은 | 15 | 14 | LOC=5/ORG=3 | **5/8** |
| 한국의 | 7 | 34 | ORG=2/LOC=4 | 5/6 |
| 한국이 | 6 | 10 | ORG=2 | 2/2 |
| 미국의 | 9 | 38 | LOC=3/ORG=4 | 6/7 |
| 미국이 | 7 | 6 | LOC=1/ORG=2 | 2/3 |
| 북한의 | 47 | 25 | ORG=8/LOC=2 | 9/10 |

→ "한국은" 같이 train 에서 50:50 으로 라벨 잡힌 surface 는 inherent noise. 모델이 결정 불가능.

### H6. train/dev OOV 일반화 격차: ⚠️⚠️ **가장 큰 원인**

dev 의 gold entity surface 가 train 에 (같은 라벨로) 등장했는가에 따른 recall.

| 라벨 | seen n | seen recall | unseen n | unseen recall | 격차 |
|---|---:|---:|---:|---:|---:|
| PERSON | 1,180 | 0.9797 | 3,001 | 0.9497 | −3.00%p |
| ORG | 873 | **0.9359** | 1,154 | **0.8050** | **−13.09%p** |
| LOCATION | 647 | 0.9320 | 869 | **0.8343** | **−9.77%p** |
| PROJ_N | 292 | 1.0000 | 56 | 1.0000 | 0%p |

→ **ORG 의 unseen surface 에서 recall 0.81, LOC unseen 0.83** — OOV 일반화가 가장 큰 bottleneck.
   PERSON 은 surface 패턴(2~3자 한국 이름)이 학습되어 OOV 에서도 95%.
   PROJ_N 은 합성으로 surface 종류가 제한적이라 변동 없음.

## Part 3 — 95% 달성 가능성 종합 평가

### 데이터 문제로 인한 ceiling

1. **본질적 라벨 노이즈** (H1): 인기 국가명 등 168개 surface 가 train 에서 두 라벨로 등장.
   - 보수적 정제(minority<15%)만 해도 75 entity 만 영향. 영향 제한적.
   - 적극 정제(`한국은` 같은 50:50 case 통일)는 합법적 context 변이를 깎음.

2. **OOV 일반화 한계** (H6): ORG/LOC unseen surface 에서 13~10%p 추락.
   - 모델이 본 적 없는 한국 기관명·지명을 일반화로 못 잡음.
   - 해결: 더 큰 코퍼스 (NIKL/AI-Hub), 또는 contextual features 강화.

3. **긴 entity 패널티** (H4): len ≥ 3 에서 ORG/LOC 70%대.
   - boundary 학습이 어렵고 surface 가 unique 해서 unseen 처리 부담.

### KLUE-NER 본질적 ceiling

- KLUE 공식 RoBERTa-large 도 entity macro F1 0.914 (KLUE 논문)
- 우리 RoBERTa-large entity F1 0.921 — 공식 SOTA 영역
- 한 라벨에서 95% 도달은 KLUE-NER 평가 셋의 **본질적 어려움**으로 제한됨

### 95% per-label 도달 경로 (현실적)

**가능성 평가**:

| 전략 | 기대 효과 | 95% 도달? | 비용 |
|---|---|---|---|
| 라벨 노이즈 정제 (보수적) | +0.5~1.5%p | ❌ ORG/LOC | 본 iter7 진행 중 |
| 라벨 노이즈 정제 (적극) | +1~3%p, 일부 회귀 위험 | ❌ 가능성 작음 | 추가 1회 학습 |
| NIKL 신청 후 추가 | +3~5%p | 🟡 가능성 있음 | 사용자 신청(1~5일) + 학습 |
| AI-Hub 신청 후 추가 | +1~3%p | 🟡 가능성 있음 | 사용자 신청(1~5일) + 학습 |
| GPU + roberta-large × 5 시드 앙상블 | +2~4%p | 🟡 부분 가능 | GPU 환경 + 5~10시간 |
| CRF 레이어 + span-based prediction | +2~4%p | 🟡 가능성 있음 | 구현 ~수일 |
| KLUE dev 일관화 (eval gaming) | +3~5%p (인위적) | ✅ 도달 | **No-hardcoding 원칙 위반** |

### 결론

> **"하드코딩 없이 모든 라벨 95%"** 는 KLUE-NER 의 ORG/LOC 에서 단일 base/large 모델로는 도달 불가.
> 본질적 원인:
> 1. KLUE 의 라벨링 노이즈 (~1% 라벨, ~5% 경계)
> 2. 한국어 OOV 일반화의 본질적 어려움
> 3. KLUE 공식 SOTA 도 0.91 macro
>
> 진정한 도달을 위해 필요한 것:
> 1. **NIKL/AI-Hub 추가 데이터** (사용자 신청)
> 2. GPU 환경 + 다중 시드 large 앙상블
> 3. 또는 mask 효과 task-aligned 지표로 평가 전환 (token-F1 / mask coverage 에선 LOC 0.94, ORG 0.91)
>
> Iter7 (보수적 라벨 노이즈 정제 + warm-start) 결과로 데이터 정제의 실제 영향 확인 예정.
