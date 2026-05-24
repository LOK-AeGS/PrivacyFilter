// Content Script — ChatGPT 입력 가로채기(전송 직전 마스킹) + 응답 복원.
//
// 동작:
//   1. Enter / 전송버튼 클릭을 capture 단계에서 가로챔
//   2. 입력 텍스트를 background→offscreen 으로 보내 마스킹
//   3. 입력창을 마스킹된 텍스트로 교체 후 실제 전송 트리거
//   4. 어시스턴트 응답 DOM 을 감시해 alias→original 복원
//
// 사이트 UI 변경 시 아래 SELECTORS 만 갱신하면 된다.

const SELECTORS = {
  // 입력창 (contenteditable ProseMirror 또는 textarea)
  input: '#prompt-textarea, div[contenteditable="true"], textarea[data-testid], main textarea',
  sendButton: 'button[data-testid="send-button"], button[aria-label*="보내기"], button[aria-label*="Send"]',
  assistantMessage: '[data-message-author-role="assistant"]',
};

let enabled = true;
let internalSubmit = false; // 우리가 트리거한 전송은 다시 가로채지 않기 위한 플래그

chrome.storage.local.get({ enabled: true }, (v) => { enabled = v.enabled; });
chrome.storage.onChanged.addListener((changes) => {
  if (changes.enabled) enabled = changes.enabled.newValue;
});

// ───────────── 입력창 헬퍼 ─────────────

function getInput() {
  // #prompt-textarea(ChatGPT 프롬프트 ID)를 우선 — querySelector 의 문서순서 때문에
  // 다른 contenteditable 이 먼저 잡히는 문제 회피.
  return (
    document.querySelector("#prompt-textarea") ||
    document.querySelector(SELECTORS.input)
  );
}

// 이벤트 발생 지점에서 가장 가까운 입력 영역 (가장 견고한 방식)
function findEditable(node) {
  return (node && node.closest && node.closest('#prompt-textarea, [contenteditable="true"], textarea')) || null;
}

function getText(el) {
  if (!el) return "";
  if (el.tagName === "TEXTAREA") return el.value;
  return el.innerText;
}

function setText(el, text) {
  if (!el) return;
  el.focus();
  if (el.tagName === "TEXTAREA") {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
    setter.call(el, text);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    return;
  }
  // contenteditable: 전체 선택 후 insertText (React/ProseMirror 가 입력 이벤트로 인식)
  const sel = window.getSelection();
  const range = document.createRange();
  range.selectNodeContents(el);
  sel.removeAllRanges();
  sel.addRange(range);
  document.execCommand("insertText", false, text);
}

function triggerSend() {
  const btn = document.querySelector(SELECTORS.sendButton);
  if (btn && !btn.disabled) {
    btn.click();
    return true;
  }
  // 폴백: 입력창에 Enter 키 디스패치
  const el = getInput();
  if (el) {
    const ev = new KeyboardEvent("keydown", { key: "Enter", code: "Enter", bubbles: true });
    el.dispatchEvent(ev);
    return true;
  }
  return false;
}

// ───────────── 마스킹 후 전송 ─────────────

async function maskAndSend(inputArg) {
  const input = inputArg || getInput();
  const text = getText(input);
  console.log("[PF] 원문:", JSON.stringify(text));
  if (!text || !text.trim()) { console.log("[PF] 빈 입력 — 그대로 전송"); internalSubmit = true; triggerSend(); return; }

  let res;
  try {
    res = await chrome.runtime.sendMessage({ type: "mask", text });
  } catch (e) {
    console.warn("[PF] ❌ mask 요청 실패(offscreen 미응답?), 원문 전송:", e);
  }
  console.log("[PF] 마스킹 응답:", res);

  if (res && res.maskedText && !res.error) {
    console.log("[PF] ✅ 마스킹됨:", JSON.stringify(res.maskedText), "/ 스팬", res.spans && res.spans.length);
    setText(input, res.maskedText);
    await new Promise((r) => setTimeout(r, 40)); // React 상태 반영 대기
    if (res.spans && res.spans.length) {
      showToast(`🔒 ${res.spans.length}개 항목 마스킹 (${res.latency.total_ms}ms)`);
    }
  } else if (res && res.error) {
    console.warn("[PF] ❌ 마스킹 오류, 원문 전송:", res.error);
  } else {
    console.warn("[PF] ⚠ 마스킹 결과 없음 — 원문 전송됨");
  }

  internalSubmit = true;
  triggerSend();
}

// ───────────── 전송 이벤트 가로채기 ─────────────

function onKeydown(e) {
  if (!enabled) { console.log("[PF] Enter 무시 — 확장 비활성(enabled=false)"); return; }
  if (e.key !== "Enter" || e.shiftKey) return;
  console.log("[PF] Enter 감지 → isComposing:", e.isComposing, "keyCode:", e.keyCode);
  if (e.isComposing || e.keyCode === 229) {
    console.log("[PF] ⏭ 한글 조합 중(IME)이라 통과 — 마스킹 안 함");
    return;
  }
  const input = findEditable(e.target) || getInput();
  console.log("[PF] 입력영역:", input ? (input.id || input.tagName) : null);
  if (!input) { console.log("[PF] ⏭ 입력영역 못 찾음 — 통과"); return; }
  if (internalSubmit) { internalSubmit = false; return; } // 우리가 보낸 Enter 통과

  console.log("[PF] ✋ 가로채기 성공 → 마스킹 시작");
  e.preventDefault();
  e.stopImmediatePropagation();
  maskAndSend(input);
}

function onClick(e) {
  if (!enabled) return;
  const btn = e.target.closest && e.target.closest(SELECTORS.sendButton);
  if (!btn) return;
  if (internalSubmit) { internalSubmit = false; return; } // 우리가 보낸 click 통과

  e.preventDefault();
  e.stopImmediatePropagation();
  maskAndSend();
}

document.addEventListener("keydown", onKeydown, true);
document.addEventListener("click", onClick, true);

// ───────────── 응답 복원 ─────────────

function walkTextNodes(root, fn) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const n of nodes) fn(n);
}

async function restoreMessage(msgEl) {
  let res;
  try {
    res = await chrome.runtime.sendMessage({ type: "getPairs" });
  } catch { return; }
  const pairs = (res && res.pairs) || [];
  if (!pairs.length) return;
  pairs.sort((a, b) => b.alias.length - a.alias.length);

  walkTextNodes(msgEl, (node) => {
    let t = node.nodeValue;
    let changed = false;
    for (const { alias, original } of pairs) {
      if (alias && t.includes(alias)) { t = t.split(alias).join(original); changed = true; }
    }
    if (changed) node.nodeValue = t;
  });
}

// 어시스턴트 메시지 스트리밍이 멈추면 복원 (메시지별 디바운스)
const restoreTimers = new WeakMap();
function scheduleRestore(msgEl) {
  if (!enabled) return;
  clearTimeout(restoreTimers.get(msgEl));
  restoreTimers.set(msgEl, setTimeout(() => restoreMessage(msgEl), 700));
}

const observer = new MutationObserver((mutations) => {
  for (const m of mutations) {
    // 추가/변경된 노드 주변의 어시스턴트 메시지 탐색
    const target = m.target.nodeType === 1 ? m.target : m.target.parentElement;
    if (!target) continue;
    const msgEl = target.closest && target.closest(SELECTORS.assistantMessage);
    if (msgEl) scheduleRestore(msgEl);
  }
});
observer.observe(document.body, { childList: true, subtree: true, characterData: true });

// ───────────── 토스트 ─────────────

let toastEl = null;
function showToast(text) {
  if (!toastEl) {
    toastEl = document.createElement("div");
    toastEl.style.cssText = [
      "position:fixed", "bottom:90px", "left:50%", "transform:translateX(-50%)",
      "background:#10a37f", "color:#fff", "padding:8px 16px", "border-radius:20px",
      "font-size:13px", "font-family:sans-serif", "z-index:99999",
      "box-shadow:0 2px 8px rgba(0,0,0,.2)", "transition:opacity .3s", "pointer-events:none",
    ].join(";");
    document.body.appendChild(toastEl);
  }
  toastEl.textContent = text;
  toastEl.style.opacity = "1";
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => { if (toastEl) toastEl.style.opacity = "0"; }, 2500);
}

// 로드 표식을 DOM 에 남긴다 (content script 는 격리 world 라 window 전역은
// 페이지 콘솔에서 안 보임 → DOM 속성은 공유되므로 콘솔에서 확인 가능).
document.documentElement.dataset.pfLoaded = "1";
console.log("[PrivacyFilter] content script 활성화");
