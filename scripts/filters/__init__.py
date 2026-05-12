"""필터 레지스트리.

각 필터는 단일 record(dict)를 받아 수정된 record 또는 None(drop)을 반환한다.
datasets.yaml 에서 이름 기반으로 호출된다.

추가 방법:
  1. quality.py 또는 label.py 에 함수 정의
  2. 본 파일의 FILTERS dict 에 등록
  3. configs/datasets.yaml 의 source.filters 에 이름 추가
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from .quality import (
    drop_url_entities,
    drop_excessive_special_chars,
    drop_too_long_entities,
    drop_short_entities,
    strip_trailing_punctuation,
)
from .label import (
    drop_record_if_any_entity_dropped,
    clean_label_noise,
)

# (record) → record or None
FilterFn = Callable[[dict], Optional[dict]]

# datasets.yaml 의 `filters` 리스트에서 참조하는 이름들
FILTERS: Dict[str, FilterFn] = {
    "drop_url_entities": drop_url_entities,
    "drop_excessive_special_chars": drop_excessive_special_chars,
    "drop_too_long_entities": drop_too_long_entities,
    "drop_short_entities": drop_short_entities,
    "strip_trailing_punctuation": strip_trailing_punctuation,
    "drop_record_if_any_entity_dropped": drop_record_if_any_entity_dropped,
}

__all__ = ["FILTERS", "FilterFn"]
