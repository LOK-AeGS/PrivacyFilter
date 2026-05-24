const toggle = document.getElementById("toggle");
const debugToggle = document.getElementById("debugToggle");
const dot = document.getElementById("dot");
const modelStatus = document.getElementById("modelStatus");
const stats = document.getElementById("stats");
const clearBtn = document.getElementById("clearBtn");

// 토글 상태 로드
chrome.storage.local.get({ enabled: true, debug: false }, (v) => {
  toggle.checked = v.enabled;
  debugToggle.checked = v.debug;
});
toggle.addEventListener("change", () => {
  chrome.storage.local.set({ enabled: toggle.checked });
});
debugToggle.addEventListener("change", () => {
  chrome.storage.local.set({ debug: debugToggle.checked });
});

// 모델/세션 상태 조회
function refreshStatus() {
  chrome.runtime.sendMessage({ type: "status" }, (res) => {
    if (chrome.runtime.lastError || !res) {
      modelStatus.textContent = "백그라운드 응답 없음";
      return;
    }
    if (res.ready) {
      dot.classList.add("on");
      modelStatus.textContent = "NER 모델 준비 완료";
    } else {
      dot.classList.remove("on");
      modelStatus.textContent = "모델 로딩 중…";
    }
    if (res.stats) stats.textContent = `매핑 ${res.stats.totalMappings}개 · 세션 ${res.stats.activeSessions}`;
  });
}
refreshStatus();
setInterval(refreshStatus, 1500);

clearBtn.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "clearSession" }, () => refreshStatus());
});
