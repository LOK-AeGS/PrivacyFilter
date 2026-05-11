# data/raw/

각 데이터셋 원본을 여기에 배치한다. 라이선스상 재배포가 어렵거나 신청이 필요한
데이터는 직접 받아 두어야 한다. `.gitignore` 에 의해 내용은 커밋되지 않는다.

## KLUE-NER

자동 다운로드 (별도 배치 불필요):
```
python scripts/convert_klue.py
```
HuggingFace `datasets` 가 캐시에 받아온다.

## 네이버+창원대 NER

다운로드 후 다음 경로에 배치:
```
data/raw/naver/train.tsv
```
출처: https://github.com/naver/nlp-challenge

## 국립국어원 개체명 말뭉치 (모두의 말뭉치)

신청 후 받은 JSON 파일들을 다음 경로에 배치:
```
data/raw/nikl/*.json
```
출처: https://corpus.korean.go.kr (회원가입 + 사용 신청 필요)

## AI-Hub 개인정보 비식별화

신청 후 받은 데이터를 표준 포맷(JSON/JSONL with `text` & `entities`)으로
정규화한 뒤 다음 경로에 배치:
```
data/raw/aihub/*.json   (또는 *.jsonl)
```
출처: https://aihub.or.kr (회원가입 + 사용 신청 필요)
