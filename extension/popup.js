const statusText = document.querySelector("#statusText");
const matchesEl = document.querySelector("#matches");
const checkNowButton = document.querySelector("#checkNow");
const openOptionsButton = document.querySelector("#openOptions");
const openDashboardButton = document.querySelector("#openDashboard");

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatDate(value) {
  if (!value) return "아직 확인 전";
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "short",
    timeStyle: "short"
  }).format(new Date(value));
}

function renderMatches(items) {
  if (!items || items.length === 0) {
    matchesEl.className = "list empty";
    matchesEl.textContent = "아직 표시할 알림이 없습니다.";
    return;
  }

  matchesEl.className = "list";
  matchesEl.innerHTML = items.slice(0, 8).map((item) => {
    const keywords = (item.matchedKeywords || []).map(escapeHtml).join(", ");
    const url = escapeHtml(item.url || "#");
    return `
      <a class="item" href="${url}" target="_blank" rel="noreferrer">
        <span class="source">${escapeHtml(item.sourceName || item.source || item.sourceId || "교육청")}</span>
        <strong>${escapeHtml(item.title || "제목 없음")}</strong>
        <small>${keywords}</small>
      </a>
    `;
  }).join("");
}

async function refresh() {
  const state = await chrome.storage.local.get({
    recentMatches: [],
    lastCheckedAt: null,
    lastError: null,
    lastMatchCount: 0
  });

  if (state.lastError) {
    statusText.textContent = `마지막 확인 실패: ${state.lastError}`;
  } else {
    statusText.textContent = `${formatDate(state.lastCheckedAt)} 확인, 관심 자료 ${state.lastMatchCount || 0}건`;
  }
  renderMatches(state.recentMatches);
}

checkNowButton.addEventListener("click", async () => {
  checkNowButton.disabled = true;
  checkNowButton.textContent = "확인 중";
  const response = await chrome.runtime.sendMessage({ type: "CHECK_NOW" });
  if (!response?.ok) {
    statusText.textContent = `확인 실패: ${response?.error || "알 수 없는 오류"}`;
  }
  checkNowButton.disabled = false;
  checkNowButton.textContent = "지금 확인";
  await refresh();
});

openOptionsButton.addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});

openDashboardButton.addEventListener("click", () => {
  chrome.tabs.create({ url: chrome.runtime.getURL("dashboard.html") });
});

refresh();
