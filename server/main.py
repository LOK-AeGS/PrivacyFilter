"""PrivacyFilter FastAPI 서버.

Endpoints:
  GET  /healthz     서버 상태 + 모델 로딩 여부
  POST /mask        text + session_id → masked + spans
  POST /unmask      text + spans → restored
  POST /clear_session   세션 매핑 초기화
  GET  /stats       활성 세션 수, 매핑 개수

실행:
  uvicorn server.main:app --port 8000
  # 또는
  python -m uvicorn server.main:app --port 8000

환경 변수:
  PF_MODEL_DIR   NER 모델 디렉터리 (기본: models/klue_roberta_large_iter10)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from server.alias_manager import AliasManager  # noqa: E402
from server.mask_service import MaskService, Span  # noqa: E402

MODEL_DIR = os.environ.get(
    "PF_MODEL_DIR",
    str(REPO_ROOT / "models" / "klue_roberta_large_iter10"),
)

app = FastAPI(title="PrivacyFilter", version="0.1.0")

# Chrome 확장에서 호출 가능하도록 CORS 허용 (개발용 와일드카드)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

alias_manager = AliasManager()
mask_service = MaskService(MODEL_DIR, alias_manager)


# ───────────────── Schemas ─────────────────


class MaskRequest(BaseModel):
    text: str = Field(..., description="원본 텍스트")
    session_id: str = Field("default", description="세션 식별자 (가명 일관성 단위)")


class SpanOut(BaseModel):
    start: int
    end: int
    label: str
    original: str
    alias: str
    src: str  # "regex" or "ner"


class MaskResponse(BaseModel):
    masked_text: str
    spans: List[SpanOut]
    latency_ms: dict


class UnmaskRequest(BaseModel):
    text: str
    spans: List[SpanOut]


class UnmaskResponse(BaseModel):
    restored_text: str


class ClearSessionRequest(BaseModel):
    session_id: str


# ───────────────── Endpoints ─────────────────


@app.get("/healthz")
def healthz():
    return {
        "status": "ok",
        "model_dir": MODEL_DIR,
        "model_loaded": mask_service._pipe is not None,
    }


@app.get("/stats")
def stats():
    return alias_manager.stats()


@app.post("/mask", response_model=MaskResponse)
def mask(req: MaskRequest):
    if not req.text:
        raise HTTPException(status_code=400, detail="text is empty")
    masked, spans, latency = mask_service.mask(req.text, req.session_id)
    return MaskResponse(
        masked_text=masked,
        spans=[SpanOut(**{k: getattr(s, k) for k in ("start", "end", "label", "original", "alias", "src")}) for s in spans],
        latency_ms=latency,
    )


@app.post("/unmask", response_model=UnmaskResponse)
def unmask(req: UnmaskRequest):
    spans = [Span(start=s.start, end=s.end, label=s.label, original=s.original, alias=s.alias, src=s.src) for s in req.spans]
    restored = MaskService.unmask(req.text, spans)
    return UnmaskResponse(restored_text=restored)


@app.post("/clear_session")
def clear_session(req: ClearSessionRequest):
    removed = alias_manager.clear_session(req.session_id)
    return {"removed": removed, "session_id": req.session_id}


@app.on_event("startup")
def warmup():
    """서버 시작 시 모델 미리 로드 — 첫 요청 지연 회피."""
    print(f"[startup] PF_MODEL_DIR = {MODEL_DIR}", flush=True)
    if Path(MODEL_DIR).exists():
        mask_service._ensure_model()
    else:
        print(f"[startup] ⚠️ 모델 디렉터리 없음: {MODEL_DIR}", flush=True)
