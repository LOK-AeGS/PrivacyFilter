// 확장 페이지로 열어 브라우저(WASM) 추론 경로를 ChatGPT 없이 검증.
// chrome-extension://<id>/test.html 로 접속.
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

const $ = (id) => document.getElementById(id);
let svc;

(async () => {
  const t0 = performance.now();
  const tokenizer = await AutoTokenizer.from_pretrained("klue-ner");
  const model = await AutoModelForTokenClassification.from_pretrained("klue-ner", { dtype: "q8" });
  svc = new MaskService({ tokenizer, model, aliasManager: new AliasManager() });
  $("status").textContent = `모델 준비 완료 (로딩 ${Math.round(performance.now() - t0)}ms, 백엔드 WASM)`;
  $("maskBtn").disabled = false;
  $("benchBtn").disabled = false;
})().catch((e) => { $("status").textContent = "로딩 실패: " + e.message; console.error(e); });

$("maskBtn").addEventListener("click", async () => {
  const text = $("input").value;
  const { maskedText, spans, latency } = await svc.mask(text, "test");
  $("masked").textContent = maskedText;
  $("latency").textContent = `regex ${latency.regex_ms}ms · NER ${latency.ner_ms}ms · 합계 ${latency.total_ms}ms`;
  $("spans").innerHTML =
    "<table><tr><th>라벨</th><th>출처</th><th>원본</th><th>가명</th></tr>" +
    spans.map((s) => `<tr><td>${s.label}</td><td>${s.src}</td><td>${s.original}</td><td>${s.alias}</td></tr>`).join("") +
    "</table>";
  // 왕복 복원: 가명이 포함된 텍스트를 다시 원본으로
  $("restored").textContent = MaskService.unmask(maskedText, spans);
});

$("benchBtn").addEventListener("click", async () => {
  const text = $("input").value;
  const times = [];
  await svc.mask(text, "warm"); // 워밍업
  for (let i = 0; i < 20; i++) {
    const { latency } = await svc.mask(text, "bench" + i);
    times.push(latency.total_ms);
  }
  times.sort((a, b) => a - b);
  const avg = (times.reduce((a, b) => a + b, 0) / times.length).toFixed(1);
  const p95 = times[Math.floor(times.length * 0.95)];
  $("latency").textContent = `벤치 20회 → 평균 ${avg}ms · 중앙값 ${times[10]}ms · p95 ${p95}ms · 최소 ${times[0]}ms · 최대 ${times[times.length - 1]}ms`;
});
