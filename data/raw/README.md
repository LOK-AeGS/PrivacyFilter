# data/raw/

각 데이터셋 원본을 여기에 배치한다. 라이선스상 재배포가 어렵거나 신청이 필요한
데이터는 사용자가 직접 받아 두어야 한다. `.gitignore` 에 의해 내용은 커밋되지 않는다.

## 1. KLUE-NER  (자동 — 별도 작업 불필요)

```bash
python scripts/convert_klue.py
```
HuggingFace `datasets` 가 자동으로 받아 캐시한다. 첫 실행 시 ~30MB 다운로드.

## 2. 네이버+창원대 NER  (수동 다운로드)

**출처**: https://github.com/naver/nlp-challenge — `missions/ner/` 폴더

```bash
# 예시 (사용자 PC에서)
git clone https://github.com/naver/nlp-challenge.git
cp nlp-challenge/missions/ner/data/train data/raw/naver/train.tsv

# 변환
python scripts/convert_naver.py
```

**원본 포맷**: TSV, 어절 단위 BIO. 라이선스 확인 필요.

## 3. 국립국어원 개체명 말뭉치  (회원가입 + 사용 신청 필요)

**출처**: https://corpus.korean.go.kr (모두의 말뭉치)

### 신청 절차

1. 모두의 말뭉치 사이트 회원가입 (https://corpus.korean.go.kr/main.do)
2. 로그인 후 **자료 → 말뭉치 → 개체명 분석 말뭉치** 검색
3. 다운로드 신청서 작성 — 사용 목적·소속·기간 명시 (학생 연구 가능)
4. 승인까지 보통 **1~3 영업일** 소요
5. 승인 후 **마이페이지 → 다운로드** 에서 JSON 파일 받기

### 배치 및 변환

```bash
# 받은 JSON 들을 다음 경로에 둔다
data/raw/nikl/SXNE2102108130.json
data/raw/nikl/SXNE2102108131.json
# ...

# 변환
python scripts/convert_nikl.py
```

**원본 포맷** (요약):
```json
{
  "document": [{
    "sentence": [{
      "form": "이순신 장군은 ...",
      "NE": [{"form": "이순신", "label": "PS_NAME", "begin": 0, "end": 3}, ...]
    }]
  }]
}
```

라벨 prefix(PS, OG, LC) 기준으로 PERSON/ORG/LOCATION 으로 매핑 (configs/label_mapping.yaml의 `nikl_prefix`).

## 4. AI-Hub 개인정보 비식별화  (회원가입 + 사용 신청 필요)

**출처**: https://aihub.or.kr — "개인정보 비식별화" 또는 "프라이버시 보호 한국어" 데이터셋 검색

### 신청 절차

1. AI-Hub 회원가입 (https://aihub.or.kr)
2. **데이터 검색** 에서 키워드 "개인정보 비식별화" 검색
3. 데이터셋 상세 페이지에서 **다운로드 신청** 클릭
4. 활용 목적 입력 (학생 캡스톤·연구 가능)
5. 승인까지 보통 **1~5 영업일**
6. 승인 후 **마이페이지 → 다운로드** — AI-Hub 다운로더(Java/CLI) 필요할 수 있음

### 배치 및 변환

원본 포맷은 하위 도메인(의료/금융 등)에 따라 다르다. 본 repo 는 다음 두 표준 변형을 지원한다.

**(A) JSON-span 포맷**:
```json
{
  "data": [
    {"text": "...", "entities": [{"begin": 0, "end": 3, "type": "NAME"}, ...]},
    ...
  ]
}
```

**(B) JSONL 포맷**:
```json
{"text": "...", "entities": [{"begin": 0, "end": 3, "type": "NAME"}, ...]}
```

AI-Hub 원본이 위와 다르면 사용자 측에서 위 포맷으로 변환한 뒤 배치한다.

```bash
data/raw/aihub/...json  (또는 *.jsonl)

# 변환
python scripts/convert_aihub.py
```

**용도**: AI-Hub PII 는 정규식 토큰(RRN/PHONE/EMAIL/...) 의 검증·평가용 보조 데이터셋으로 사용한다. NER 학습 본세트에는 포함하지 않는다.
