// Service Worker — offscreen 문서 생명주기 관리 + content ↔ offscreen 메시지 릴레이.
//
// 모델 추론(WASM)은 Service Worker 에서 직접 못 돌리므로 offscreen 문서에 위임한다.
// sessionId 는 보낸 탭의 id 로 부여 → 탭별 가명 일관성.

const OFFSCREEN_PATH = "offscreen.html";

let creating = null; // 중복 생성 방지용 promise

async function ensureOffscreen() {
  // 이미 존재하는지 확인
  const existing = await chrome.runtime.getContexts({
    contextTypes: ["OFFSCREEN_DOCUMENT"],
    documentUrls: [chrome.runtime.getURL(OFFSCREEN_PATH)],
  });
  if (existing.length > 0) return;

  if (creating) {
    await creating;
    return;
  }
  creating = chrome.offscreen.createDocument({
    url: OFFSCREEN_PATH,
    reasons: ["WORKERS"],
    justification: "온디바이스 NER 모델(ONNX/WASM) 추론을 위해 필요합니다.",
  });
  await creating;
  creating = null;
}

// offscreen 으로 명령 전달 후 응답 받기
async function callOffscreen(cmd, payload) {
  await ensureOffscreen();
  return chrome.runtime.sendMessage({ target: "offscreen", cmd, ...payload });
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // offscreen 으로 가는 메시지는 여기서 처리하지 않음 (루프 방지)
  if (msg.target === "offscreen") return false;

  if (msg.type === "mask" || msg.type === "unmask") {
    const sessionId = sender.tab ? `tab-${sender.tab.id}` : "default";
    callOffscreen(msg.type, { text: msg.text, sessionId })
      .then((res) => sendResponse(res))
      .catch((err) => sendResponse({ error: String(err && err.message || err) }));
    return true; // 비동기 응답
  }

  if (msg.type === "getPairs") {
    const sessionId = sender.tab ? `tab-${sender.tab.id}` : "default";
    callOffscreen("getPairs", { sessionId })
      .then((res) => sendResponse(res))
      .catch((err) => sendResponse({ pairs: [], error: String(err) }));
    return true;
  }

  if (msg.type === "clearSession") {
    // 팝업(탭 없음)에서 호출되면 전체 세션 초기화
    const sessionId = sender.tab ? `tab-${sender.tab.id}` : "*";
    callOffscreen("clearSession", { sessionId })
      .then((res) => sendResponse(res))
      .catch((err) => sendResponse({ error: String(err) }));
    return true;
  }

  if (msg.type === "status") {
    callOffscreen("status", {})
      .then((res) => sendResponse(res))
      .catch((err) => sendResponse({ ready: false, error: String(err) }));
    return true;
  }
  return false;
});

// 설치 시 미리 offscreen 띄워 모델 로딩 시작 (첫 요청 지연 완화)
chrome.runtime.onInstalled.addListener(() => { ensureOffscreen(); });
chrome.runtime.onStartup.addListener(() => { ensureOffscreen(); });
