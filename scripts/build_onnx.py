"""학습된 NER 모델을 ONNX (int8 quantized) 로 변환.

Chrome 확장의 Transformers.js 에서 사용할 모델 생성.

실행:
    python scripts/build_onnx.py --model-dir models/klue_roberta_iter2 \
        --out-dir onnx_models/klue_roberta_iter2_onnx

산출:
    onnx_models/<name>/
      model.onnx              (fp32, 약 440MB)
      model_quantized.onnx    (int8, 약 110MB)
      tokenizer.json
      tokenizer_config.json
      config.json
      label_list.txt
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--task", default="token-classification")
    parser.add_argument("--skip-quantize", action="store_true")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    # 1. ONNX export (optimum-cli)
    print(f"[1/3] ONNX export: {args.model_dir} → {args.out_dir}")
    cmd = [
        "optimum-cli", "export", "onnx",
        "--model", str(args.model_dir),
        "--task", args.task,
        str(args.out_dir),
    ]
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit("optimum-cli export 실패")

    # 2. tokenizer 파일 보강
    print(f"[2/3] Tokenizer 파일 복사")
    for fname in ("tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
                  "vocab.txt", "label_list.txt", "eval_results.json"):
        src = args.model_dir / fname
        if src.exists():
            shutil.copy(src, args.out_dir / fname)

    # tokenizer_config 의 tokenizer_class 정규화 (transformers 5.x 의 "TokenizersBackend" → "BertTokenizerFast")
    tcfg_path = args.out_dir / "tokenizer_config.json"
    if tcfg_path.exists():
        tcfg = json.loads(tcfg_path.read_text(encoding="utf-8"))
        if tcfg.get("tokenizer_class") == "TokenizersBackend":
            tcfg["tokenizer_class"] = "BertTokenizerFast"
        # 불필요 키 제거
        for k in ("backend", "is_local", "never_split"):
            tcfg.pop(k, None)
        tcfg_path.write_text(json.dumps(tcfg, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  fixed: {tcfg_path}")

    if args.skip_quantize:
        print("--skip-quantize 지정 → 종료")
        return

    # 3. int8 quantization
    print(f"[3/3] int8 dynamic quantization")
    from optimum.onnxruntime import ORTQuantizer
    from optimum.onnxruntime.configuration import AutoQuantizationConfig

    q_out = args.out_dir.parent / (args.out_dir.name + "_int8")
    q_out.mkdir(parents=True, exist_ok=True)
    for f in args.out_dir.iterdir():
        if f.is_file() and f.name != "model.onnx":
            shutil.copy(f, q_out / f.name)

    quantizer = ORTQuantizer.from_pretrained(args.out_dir)
    qconfig = AutoQuantizationConfig.avx512_vnni(is_static=False, per_channel=False)
    quantizer.quantize(save_dir=str(q_out), quantization_config=qconfig)
    print(f"  saved: {q_out}/model_quantized.onnx")

    # 산출물 크기 보고
    for d in (args.out_dir, q_out):
        total = sum(f.stat().st_size for f in d.glob("*") if f.is_file())
        print(f"\n  {d}: 총 {total/1024/1024:.1f} MB")


if __name__ == "__main__":
    main()
