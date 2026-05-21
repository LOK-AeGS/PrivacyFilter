// 확장 실행에 필요한 대용량 바이너리(.wasm, .onnx)를 복원한다.
// GitHub 100MB 제한 때문에 이 파일들은 git 에 올리지 않으므로, clone 후 1회 실행한다.
//
//   node scripts/setup_extension.mjs
//
// 동작:
//   1) Transformers.js dist(웹빌드 + ORT wasm) 를 extension/lib/transformers/ 로 복사
//      (없으면 extension/_vendor 에 npm install)
//   2) ONNX int8 모델을 extension/models/klue-ner/ 로 복사
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const VENDOR = path.join(ROOT, "extension", "_vendor");
const LIB = path.join(ROOT, "extension", "lib", "transformers");
const MODEL_DST = path.join(ROOT, "extension", "models", "klue-ner");
const ONNX_SRC = path.join(ROOT, "onnx_models", "klue_roberta_iter2_onnx_int8");

function ensureDir(d) { fs.mkdirSync(d, { recursive: true }); }
function copy(src, dst) {
  if (!fs.existsSync(src)) { console.warn("  ⚠️  누락:", src); return false; }
  fs.copyFileSync(src, dst);
  console.log("  ✓", path.relative(ROOT, dst));
  return true;
}

// 1) Transformers.js dist
console.log("[1/2] Transformers.js dist 복원");
const distDir = path.join(VENDOR, "node_modules", "@huggingface", "transformers", "dist");
if (!fs.existsSync(distDir)) {
  console.log("  npm install @huggingface/transformers@3 …");
  ensureDir(VENDOR);
  if (!fs.existsSync(path.join(VENDOR, "package.json"))) {
    execSync("npm init -y", { cwd: VENDOR, stdio: "ignore" });
  }
  execSync("npm install @huggingface/transformers@3", { cwd: VENDOR, stdio: "inherit" });
}
ensureDir(LIB);
for (const f of [
  "transformers.min.js",
  "transformers.min.js.map",
  "ort-wasm-simd-threaded.jsep.wasm",
  "ort-wasm-simd-threaded.jsep.mjs",
]) copy(path.join(distDir, f), path.join(LIB, f));

// 2) ONNX 모델
console.log("[2/2] ONNX int8 모델 복원");
ensureDir(path.join(MODEL_DST, "onnx"));
copy(path.join(ONNX_SRC, "config.json"), path.join(MODEL_DST, "config.json"));
copy(path.join(ONNX_SRC, "tokenizer.json"), path.join(MODEL_DST, "tokenizer.json"));
copy(path.join(ONNX_SRC, "tokenizer_config.json"), path.join(MODEL_DST, "tokenizer_config.json"));
const ok = copy(path.join(ONNX_SRC, "model_quantized.onnx"), path.join(MODEL_DST, "onnx", "model_quantized.onnx"));
if (!ok) {
  console.log("\n  ONNX 모델이 없으면 먼저 생성하세요:");
  console.log("    python scripts/build_onnx.py --model-dir models/klue_roberta_iter2 \\");
  console.log("      --out-dir onnx_models/klue_roberta_iter2_onnx");
}
console.log("\n완료. chrome://extensions → '압축해제된 확장 프로그램 로드' → extension/ 선택");
