const DEFAULT_DATA_URL = "https://kain9012-bit.github.io/edu-news-alert/news.json";
const DEFAULT_KEYWORDS = [
  "AI",
  "인공지능",
  "데이터",
  "빅데이터",
  "디지털",
  "에듀테크",
  "업무경감",
  "행정효율화",
  "자동화",
  "공공데이터",
  "교육행정",
  "데이터 기반"
];

const statusText = document.querySelector("#statusText");
const briefingCount = document.querySelector("#briefingCount");
const briefingList = document.querySelector("#briefingList");
const refreshButton = document.querySelector("#refreshBriefing");
const openOptionsButton = document.querySelector("#openOptions");
const openDashboardButton = document.querySelector("#openDashboard");
let currentWindowId = null;

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function siblingDataUrl(dataUrl, fileName) {
  const url = new URL(dataUrl || DEFAULT_DATA_URL);
  const parts = url.pathname.split("/");
  parts[parts.length - 1] = fileName;
  url.pathname = parts.join("/");
  return url.toString();
}

function itemText(item, mode) {
  const parts = [item.title || ""];
  if (mode !== "title_only") parts.push(item.summary || "");
  return parts.join("\n").toLowerCase();
}

function matchedKeywords(item, keywords, mode) {
  const text = itemText(item, mode);
  return keywords.filter((keyword) => text.includes(keyword.toLowerCase()));
}

function formatWindow(startValue, endValue) {
  const start = new Date(startValue);
  const end = new Date(endValue);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return "최근 수집 기준";

  const format = new Intl.DateTimeFormat("ko-KR", {
    month: "numeric",
    day: "numeric",
    hour: "numeric"
  });
  return `${format.format(start)} ~ ${format.format(end)}`;
}

async function fetchBriefing(url) {
  const requestUrl = new URL(url);
  requestUrl.searchParams.set("t", Date.now().toString());
  const response = await fetch(requestUrl.toString(), { cache: "no-store" });
  if (!response.ok) throw new Error(`자료를 불러오지 못했습니다. (${response.status})`);
  return response.json();
}

function renderItems(items, keywords, searchMode) {
  briefingCount.textContent = `${items.length.toLocaleString("ko-KR")}건`;
  if (items.length === 0) {
    briefingList.className = "list empty";
    briefingList.textContent = "이 시간대에 표시할 보도자료가 없습니다.";
    return;
  }

  briefingList.className = "list";
  briefingList.innerHTML = items.map((item) => {
    const matches = matchedKeywords(item, keywords, searchMode);
    const keywordLine = matches.length
      ? `<small class="matchedLine">${matches.map(escapeHtml).join(", ")}</small>`
      : "";
    const url = escapeHtml(item.url || "#");
    return `
      <a class="item" href="${url}" data-url="${url}" rel="noreferrer">
        <span class="source">${escapeHtml(item.sourceName || item.source || item.sourceId || "교육청")}</span>
        <strong>${escapeHtml(item.title || "제목 없음")}</strong>
        ${keywordLine}
      </a>
    `;
  }).join("");
}

async function loadBriefing() {
  refreshButton.disabled = true;
  statusText.textContent = "최근 자료를 불러오는 중입니다.";
  try {
    const state = await chrome.storage.local.get({
      dataUrl: DEFAULT_DATA_URL,
      keywords: DEFAULT_KEYWORDS,
      enabledSourceIds: [],
      searchMode: "title_summary"
    });
    const briefing = await fetchBriefing(siblingDataUrl(state.dataUrl, "latest.json"));
    const enabled = new Set(state.enabledSourceIds || []);
    const items = (briefing.items || []).filter((item) => enabled.size === 0 || enabled.has(item.sourceId));
    const keywords = Array.isArray(state.keywords) ? state.keywords : DEFAULT_KEYWORDS;

    statusText.textContent = formatWindow(briefing.windowStart, briefing.windowEnd);
    renderItems(items, keywords, state.searchMode);
  } catch (error) {
    statusText.textContent = error.message || "자료를 불러오지 못했습니다.";
    briefingCount.textContent = "0건";
    briefingList.className = "list empty";
    briefingList.textContent = "잠시 후 다시 확인해 주세요.";
  } finally {
    refreshButton.disabled = false;
  }
}

briefingList.addEventListener("click", async (event) => {
  const item = event.target.closest("a.item");
  if (!item) return;
  event.preventDefault();
  const url = item.dataset.url;
  if (url && url !== "#") await chrome.tabs.create({ url, active: true });
});

refreshButton.addEventListener("click", loadBriefing);
openOptionsButton.addEventListener("click", () => chrome.runtime.openOptionsPage());
openDashboardButton.addEventListener("click", () => {
  chrome.tabs.create({ url: chrome.runtime.getURL("dashboard.html") });
});

chrome.windows.getCurrent().then((currentWindow) => {
  currentWindowId = currentWindow.id;
  chrome.runtime.sendMessage({ type: "sidePanelOpened", windowId: currentWindowId });
});

window.addEventListener("beforeunload", () => {
  if (currentWindowId != null) {
    chrome.runtime.sendMessage({ type: "sidePanelClosed", windowId: currentWindowId });
  }
});

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === "closeSidePanel" && message.windowId === currentWindowId) window.close();
});

loadBriefing();
