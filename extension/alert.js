const alertMeta = document.querySelector("#alertMeta");
const alertList = document.querySelector("#alertList");
const closeAlert = document.querySelector("#closeAlert");
const openDashboard = document.querySelector("#openDashboard");

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function render() {
  const { alertMatches = [] } = await chrome.storage.local.get({ alertMatches: [] });
  alertMeta.textContent = `${alertMatches.length}건이 새로 발견되었습니다.`;

  if (alertMatches.length === 0) {
    alertList.className = "list empty";
    alertList.textContent = "새로 표시할 보도자료가 없습니다.";
    return;
  }

  alertList.className = "list";
  alertList.innerHTML = alertMatches.slice(0, 4).map((item) => {
    const keywords = (item.matchedKeywords || []).map(escapeHtml).join(", ");
    return `
      <a class="item" href="${escapeHtml(item.url || "#")}" target="_blank" rel="noreferrer">
        <span class="source">${escapeHtml(item.sourceName || item.source || item.sourceId || "교육청")}</span>
        <strong>${escapeHtml(item.title || "제목 없음")}</strong>
        <small>${keywords}</small>
      </a>
    `;
  }).join("");
}

closeAlert.addEventListener("click", () => {
  window.close();
});

openDashboard.addEventListener("click", async () => {
  await chrome.tabs.create({ url: chrome.runtime.getURL("dashboard.html") });
  window.close();
});

render();
