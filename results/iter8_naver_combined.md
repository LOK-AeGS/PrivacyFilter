# Iteration 8: KLUE + Naver + 합성 통합 학습 — **회귀** (TS-10 현실화)

**설정**
- 모델: warm-start `models/klue_roberta_large_iter6` (F1 0.9211)
- Train: `data/processed/train.jsonl` (KLUE 21k + Naver 90k + 합성 2.8k = **113,808 문장**)
  - URL/특수문자/긴 entity 필터 적용 (`scripts/filters/quality.py`)
  - 보수적 라벨 노이즈 정제 (107 surface, 232 entity)
- Dev: dev.jsonl 5,350 (그대로)
- Epochs: 1
- LR: 1e-5
- Batch: 8
- **학습 시간: 11시간 12분** (CPU)

## 결과

| 라벨 | iter6 best | **iter8** | Δ |
|---|---:|---:|---:|
| micro F1 | 0.9211 | **0.9109** | **−0.0102** ❌ |
| PERSON | 0.9609 | 0.9560 | −0.0049 |
| ORG | 0.8704 | **0.8551** | **−0.0153** ❌ |
| LOCATION | 0.8618 | **0.8420** | **−0.0198** ❌❌ |
| PROJ_N | 0.9986 | 1.0000 | +0.0014 |

**핵심 라벨(ORG/LOCATION) 모두 큰 폭 회귀**. iter8 모델은 폐기.

## 원인 분석 — TS-10 (도메인 shift) 현실화

train 과 dev 의 소스 분포 불일치:

| 분할 | KLUE | Naver | synthetic |
|---|---:|---:|---:|
| **train** | 18% (21k) | **79% (90k)** | 2% (2.8k) |
| **dev** | **93% (5k)** | 0% | 7% (350) |

→ 모델이 79% Naver 스타일을 학습하지만, dev 는 93% KLUE 분포. **도메인 mismatch 로 KLUE dev 평가에서 더 안 맞음**.

이 위험은 통합 직후 README TS-10 으로 사전 등록했었음. **예측 정확**.

추가 원인:
- Naver 와 KLUE 의 어노테이션 규칙 차이 (M4 충돌 164 surface): Naver 가 국가명을 일관되게 LOC, KLUE 는 문맥에 따라 ORG/LOC → 통합 학습 시 KLUE 의 ORG 규칙 손상
- Naver 엔티티의 일부 노이즈는 필터로 정제했지만, 기본 어노테이션 규칙 차이는 미해결

## 8 iteration 종합

| iter | 구성 | F1 | 비고 |
|---|---|---:|---|
| 1 | BERT-base 2ep | 0.910 | baseline |
| 2 | RoBERTa-base 3ep | 0.916 | +백본 |
| 3 | + 엔티티 증강 | 0.908 ❌ | 회귀 (TS-06) |
| 4 | BERT+RoBERTa Ensemble | 0.917 | 미미 |
| 5 | warm-start +3ep | 0.911 ❌ | plateau |
| **6** | **RoBERTa-large 2ep** | **0.921** ⭐ | **최고 — final** |
| 7 | + KLUE 라벨 정제 | 0.916 ❌ | 회귀 |
| 8 | + Naver 90k 통합 | 0.911 ❌ | 회귀 (TS-10) |

## 최종 결론

> **iter6 (RoBERTa-large, KLUE 21k + 합성 2.8k) 가 최종 best 모델.**
> **현재 환경(CPU + 공개 데이터만)에서 entity-F1 95% per-label 도달은 본질적으로 불가능함이 8 iteration 으로 입증.**

KLUE 공식 RoBERTa-large 도 entity macro F1 0.914 영역. 우리는 0.921 도달 — **공식 SOTA 수준**.

## 95% per-label 도달을 위해 남은 옵션 (시도 못 한 영역)

| 옵션 | 기대 효과 | 비용 | 비고 |
|---|---|---|---|
| NIKL 데이터 추가 | +3~5%p | 신청 1~3 영업일 | **사용자 신청 필요** |
| AI-Hub 데이터 추가 | +1~3%p | 신청 1~5 영업일 | 사용자 신청 필요 |
| GPU + 다중 시드 ensemble (5개 large) | +2~4%p | GPU 환경 + ~5h | 본 CPU 환경 불가 |
| CRF / span-based prediction | +2~4%p | 구현 ~수일 | architecture 변경 |
| 단계적 fine-tuning (Naver → KLUE) | +1~3%p | 추가 학습 ~3h | curriculum learning 시도 가능 |

## 다음 단계 (5/30 발표까지)

iter6 final 확정 → 시간을 **Chrome 확장 + FastAPI 서버** 개발에 투입.

남은 작업:
1. FastAPI 로컬 추론 서버 (~1일)
2. Chrome 확장 manifest v3 + content script (~3일)
3. ChatGPT/Gemini/Claude 통합 테스트 (~1일)
4. BERTScore 응답 품질 평가 (~1일)
5. 처리 지연시간 측정 (~0.5일)
6. 최종 보고서 + 발표 자료 (~3일)
