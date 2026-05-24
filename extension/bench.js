// 처리 지연 벤치 전용 페이지 로직. test.js 와 동일한 배포 설정(WASM·단일스레드)으로
// 모델을 올린 뒤, window.runBench(prompts, iters) 로 다중 프롬프트 지연을 측정한다.
import {
  env,
  AutoTokenizer,
  AutoModelForTokenClassification,
} from "./lib/transformers/transformers.min.js";
import { MaskService } from "./lib/mask_service.js";
import { AliasManager } from "./lib/alias_manager.js";

env.allowRemoteModels = false;
env.allowLocalModels = true;
env.localModelPath = chrome.runtime.getURL("models/");
env.backends.onnx.wasm.wasmPaths = chrome.runtime.getURL("lib/transformers/");
env.backends.onnx.wasm.numThreads = 1;

const status = document.getElementById("status");
let svc;
let loadMs;

(async () => {
  const t0 = performance.now();
  const tokenizer = await AutoTokenizer.from_pretrained("klue-ner");
  const model = await AutoModelForTokenClassification.from_pretrained("klue-ner", { dtype: "q8" });
  svc = new MaskService({ tokenizer, model, aliasManager: new AliasManager() });
  loadMs = Math.round(performance.now() - t0);
  window.__loadMs = loadMs;
  window.__benchReady = true;
  status.textContent = `READY (모델 로딩 ${loadMs}ms)`;
})().catch((e) => {
  window.__benchError = e.message;
  status.textContent = "로딩 실패: " + e.message;
  console.error(e);
});

// prompts: [{id, type, prompt}], iters: 워밍 후 측정 반복 횟수
window.runBench = async (prompts, iters) => {
  // 콜드 추론: 모델 로드 직후 첫 mask 호출(커널 워밍업 포함)
  const c0 = performance.now();
  await svc.mask(prompts[0].prompt, "cold");
  const coldMs = Math.round(performance.now() - c0);

  const results = [];
  for (const p of prompts) {
    const total = [], ner = [], regex = [];
    let nSpans = 0;
    for (let i = 0; i < iters; i++) {
      const { spans, latency } = await svc.mask(p.prompt, `b${p.id}_${i}`);
      total.push(latency.total_ms);
      ner.push(latency.ner_ms);
      regex.push(latency.regex_ms);
      nSpans = spans.length;
    }
    results.push({ id: p.id, type: p.type || "", chars: p.prompt.length, n_spans: nSpans, total, ner, regex });
  }
  return { loadMs, coldMs, results };
};
