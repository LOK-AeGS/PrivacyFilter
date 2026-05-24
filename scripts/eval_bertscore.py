"""Phase 4: 마스킹 전/후 LLM 응답 품질을 BERTScore 로 비교.

각 프롬프트마다:
    R0 = LLM(원문 프롬프트)
    R1 = unmask( LLM( mask(원문 프롬프트) ) )
    BERTScore(R1, R0)  → 1.0 에 가까울수록 마스킹이 응답 의미를 보존(=품질 영향 없음)

LLM 호출은 양쪽 모두 temperature=0 으로 고정해, 차이가 '마스킹' 에서만 오도록 통제한다.

사전 준비:
    .env 에  ANTHROPIC_API_KEY=sk-ant-...  저장 (gitignored)

실행:
    python scripts/eval_bertscore.py \
        --model-dir models/klue_roberta_base_iter11 \
        --prompts data/eval/bertscore_prompts.jsonl \
        --llm-model claude-sonnet-4-6
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from server.alias_manager import AliasManager  # noqa: E402
from server.mask_service import MaskService  # noqa: E402


def read_jsonl(path: Path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def call_claude(client, model: str, prompt: str, max_tokens: int) -> str:
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", type=Path, default=REPO_ROOT / "models" / "klue_roberta_base_iter11")
    ap.add_argument("--prompts", type=Path, default=REPO_ROOT / "data" / "eval" / "bertscore_prompts.jsonl")
    ap.add_argument("--llm-model", default="claude-sonnet-4-6")
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--bert-model", default="bert-base-multilingual-cased")
    ap.add_argument("--bert-layers", type=int, default=9)
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "results" / "bertscore_eval.json")
    args = ap.parse_args()

    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY 없음 — .env 에 ANTHROPIC_API_KEY=... 를 추가하세요.")

    import anthropic
    client = anthropic.Anthropic(api_key=key)

    masker = MaskService(str(args.model_dir), AliasManager())
    prompts = list(read_jsonl(args.prompts))
    print(f"프롬프트 {len(prompts)}개 · LLM={args.llm_model}\n")

    rows, cands, refs = [], [], []
    for p in prompts:
        pid, text = p["id"], p["prompt"]
        masked, spans, _ = masker.mask(text, session_id=f"p{pid}")
        r0 = call_claude(client, args.llm_model, text, args.max_tokens)
        r1 = MaskService.unmask(call_claude(client, args.llm_model, masked, args.max_tokens), spans)
        cands.append(r1)
        refs.append(r0)
        rows.append({"id": pid, "type": p.get("type", ""), "n_pii": len(spans),
                     "masked": masked, "r0": r0, "r1": r1})
        print(f"  [{pid:2}] {p.get('type', ''):<14} PII {len(spans)}개 마스킹 완료")

    print("\nBERTScore 계산 중 (최초 1회 스코어링 모델 다운로드)...")
    from bert_score import score
    P, R, F1 = score(cands, refs, model_type=args.bert_model, num_layers=args.bert_layers, verbose=False)
    for row, p_, r_, f_ in zip(rows, P.tolist(), R.tolist(), F1.tolist()):
        row["bertscore_P"], row["bertscore_R"], row["bertscore_F1"] = round(p_, 4), round(r_, 4), round(f_, 4)

    mean_p, mean_r, mean_f1 = float(P.mean()), float(R.mean()), float(F1.mean())

    print("\n" + "=" * 60)
    print(f"{'ID':>3}  {'유형':<14} {'PII':>4}  {'BERTScore-F1':>12}")
    print("-" * 60)
    for row in rows:
        print(f"{row['id']:>3}  {row['type']:<14} {row['n_pii']:>4}  {row['bertscore_F1']:>12.4f}")
    print("-" * 60)
    print(f"{'합계/평균':<20} {sum(r['n_pii'] for r in rows):>4}  {mean_f1:>12.4f}")
    print(f"\nBERTScore 평균 — P {mean_p:.4f} / R {mean_r:.4f} / F1 {mean_f1:.4f}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"llm_model": args.llm_model, "bert_model": args.bert_model, "n_prompts": len(prompts),
                   "mean": {"P": mean_p, "R": mean_r, "F1": mean_f1}, "rows": rows},
                  f, ensure_ascii=False, indent=2)
    print(f"\n저장: {args.out}")


if __name__ == "__main__":
    main()
