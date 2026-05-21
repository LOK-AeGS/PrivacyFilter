// Offscreen 문서 — Transformers.js(ONNX/WASM)로 온디바이스 NER 추론.
// background 로부터 mask/unmask 명령을 받아 처리하고 응답한다.

import {
  env,
  AutoTokenizer,
  AutoModelForTokenClassification,
} from "./lib/transformers/transformers.min.js";
import { MaskService } from "./lib/mask_service.js";
import { AliasManager } from "./lib/alias_manager.js";

// 모든 리소스를 확장 내부(로컬)에서만 로드 — 외부 네트워크 호출 없음.
env.allowRemoteModels = false;
env.allowLocalModels = true;
env.localModelPath = chrome.runtime.getURL("models/");
env.backends.onnx.wasm.wasmPaths = chrome.runtime.getURL("lib/transformers/");
env.backends.onnx.wasm.numThreads = 1; // SharedArrayBuffer 미사용 환경

const aliasManager = new AliasManager();
let svcPromise = null; // lazy + 단일 로딩

async function getService() {
  if (!svcPromise) {
    svcPromise = (async () => {
      console.log("[PrivacyFilter] NER 모델 로딩 시작…");
      const t0 = performance.now();
      const tokenizer = await AutoTokenizer.from_pretrained("klue-ner");
      const model = await AutoModelForTokenClassification.from_pretrained("klue-ner", {
        dtype: "q8",
      });
      console.log(`[PrivacyFilter] 모델 로딩 완료 (${Math.round(performance.now() - t0)}ms)`);
      return new MaskService({ tokenizer, model, aliasManager });
    })();
  }
  return svcPromise;
}

// 설치 직후 미리 로딩 시작 (첫 마스킹 지연 완화)
getService().catch((e) => console.error("[PrivacyFilter] 모델 로딩 실패:", e));

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.target !== "offscreen") return false;

  (async () => {
    try {
      if (msg.cmd === "mask") {
        const svc = await getService();
        const { maskedText, spans, latency } = await svc.mask(msg.text, msg.sessionId);
        sendResponse({ maskedText, spans, latency });
      } else if (msg.cmd === "unmask") {
        const pairs = aliasManager.getPairs(msg.sessionId);
        const restored = MaskService.unmask(msg.text, pairs);
        sendResponse({ restoredText: restored, pairCount: pairs.length });
      } else if (msg.cmd === "getPairs") {
        sendResponse({ pairs: aliasManager.getPairs(msg.sessionId) });
      } else if (msg.cmd === "clearSession") {
        const removed = aliasManager.clearSession(msg.sessionId);
        sendResponse({ removed });
      } else if (msg.cmd === "status") {
        // 모델 준비 여부 (svcPromise 가 resolve 됐는지)
        let ready = false;
        if (svcPromise) {
          ready = await Promise.race([
            svcPromise.then(() => true),
            new Promise((r) => setTimeout(() => r(false), 0)),
          ]);
        }
        sendResponse({ ready, stats: aliasManager.stats() });
      } else {
        sendResponse({ error: "unknown cmd: " + msg.cmd });
      }
    } catch (err) {
      console.error("[PrivacyFilter] offscreen 처리 오류:", err);
      sendResponse({ error: String(err && err.message || err) });
    }
  })();
  return true; // 비동기 응답
});
