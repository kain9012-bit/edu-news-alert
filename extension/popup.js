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
const briefingScope = document.querySelector("#briefingScope");
const briefingCount = document.querySelector("#briefingCount");
const briefingList = document.querySelector("#briefingList");
const briefingSearch = document.querySelector("#briefingSearch");
const searchLabel = document.querySelector("#searchLabel");
const refreshButton = document.querySelector("#refreshBriefing");
const openOptionsButton = document.querySelector("#openOptions");
const openDashboardButton = document.querySelector("#openDashboard");
const aiBriefing = document.querySelector("#aiBriefing");
const aiBriefingMeta = document.querySelector("#aiBriefingMeta");
const aiBriefingSummary = document.querySelector("#aiBriefingSummary");
const aiTrendList = document.querySelector("#aiTrendList");
let currentWindowId = null;
let recentItems = [];
let activeKeywords = DEFAULT_KEYWORDS;
let activeSearchMode = "title_summary";

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

function aiBriefingUrl(dataUrl) {
  const url = new URL(dataUrl || DEFAULT_DATA_URL);
  const parts = url.pathname.split("/");
  parts[parts.length - 1] = "briefings/latest.json";
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

function importanceLabel(value) {
  return { high: "중요", medium: "보통", low: "참고" }[value] || value || "";
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

async function loadAiSelection(dataUrl) {
  aiBriefing.hidden = true;
  try {
    const result = await fetchBriefing(aiBriefingUrl(dataUrl));
    const metadata = result.metadata || {};
    const categories = Array.isArray(result.categorySummary) ? result.categorySummary.slice(0, 6) : [];
    aiBriefingMeta.textContent = `${metadata.relevantCount || 0}건 채택 · ${metadata.filteredOutCount || 0}건 제외`;
    aiBriefingSummary.textContent = `후보 ${metadata.candidateCount || 0}건 중 교육동향으로 볼 수 있는 자료 ${metadata.relevantCount || 0}건을 남겼습니다.`;
    aiTrendList.innerHTML = categories.map((item) => `
      <div class="aiTrend">
        <strong>${escapeHtml(item.category || "기타")}</strong>
        <p>${Number(item.count || 0).toLocaleString("ko-KR")}건</p>
      </div>
    `).join("");
    aiBriefing.hidden = false;
    return result;
  } catch (_error) {
    aiBriefing.hidden = true;
    return null;
  }
}

function renderItems(items, keywords, searchMode, emptyText) {
  briefingCount.textContent = `${items.length.toLocaleString("ko-KR")}건`;
  if (items.length === 0) {
    briefingList.className = "list empty";
    briefingList.textContent = emptyText;
    return;
  }

  briefingList.className = "list";
  briefingList.innerHTML = items.map((item) => {
    const matches = matchedKeywords(item, keywords, searchMode);
    const keywordLine = matches.length
      ? `<small class="matchedLine">${matches.map(escapeHtml).join(", ")}</small>`
      : "";
    const url = escapeHtml(item.url || "#");
    const categoryLine = item.aiCategory
      ? `<small class="categoryLine">${escapeHtml(item.aiCategory)} · ${escapeHtml(importanceLabel(item.aiImportance))}</small>`
      : "";
    return `
      <a class="item" href="${url}" data-url="${url}" rel="noreferrer">
        <span class="source">${escapeHtml(item.sourceName || item.source || item.sourceId || "교육청")}</span>
        <strong>${escapeHtml(item.title || "제목 없음")}</strong>
        ${categoryLine}
        ${keywordLine}
      </a>
    `;
  }).join("");
}

function renderCurrentView() {
  const query = briefingSearch.value.trim().toLowerCase();
  const hasSavedKeywords = activeKeywords.length > 0;
  const baseItems = hasSavedKeywords
    ? recentItems.filter((item) => matchedKeywords(item, activeKeywords, activeSearchMode).length > 0)
    : recentItems;
  const items = query
    ? baseItems.filter((item) => itemText(item, activeSearchMode).includes(query))
    : baseItems;
  const emptyText = query
    ? `“${briefingSearch.value.trim()}” 검색 결과가 없습니다.`
    : hasSavedKeywords
      ? "최근 24시간에 관심 키워드와 일치하는 보도자료가 없습니다."
      : "최근 24시간에 표시할 보도자료가 없습니다.";

  renderItems(items, activeKeywords, activeSearchMode, emptyText);
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
    const [briefing, aiSelection] = await Promise.all([
      fetchBriefing(siblingDataUrl(state.dataUrl, "latest.json")),
      loadAiSelection(state.dataUrl)
    ]);
    const keywords = Array.isArray(state.keywords) ? state.keywords : DEFAULT_KEYWORDS;
    const enabled = new Set(state.enabledSourceIds || []);
    const sameSelectionWindow = aiSelection
      && aiSelection.metadata?.windowStart === briefing.windowStart
      && aiSelection.metadata?.windowEnd === briefing.windowEnd;
    if (!sameSelectionWindow) aiBriefing.hidden = true;
    const selectedItems = sameSelectionWindow && Array.isArray(aiSelection.selectedItems)
      ? aiSelection.selectedItems
      : null;
    const selectedMap = new Map((selectedItems || []).map((item) => [item.newsId, item]));
    recentItems = (briefing.items || [])
      .filter((item) => enabled.size === 0 || enabled.has(item.sourceId))
      .filter((item) => selectedItems === null || selectedMap.has(item.id))
      .map((item) => {
        const selected = selectedMap.get(item.id);
        return selected
          ? { ...item, aiCategory: selected.category, aiImportance: selected.importance }
          : item;
      });
    activeKeywords = keywords;
    activeSearchMode = state.searchMode;
    briefingScope.textContent = activeKeywords.length > 0
      ? (selectedItems === null ? "최근 24시간 관심 자료" : "최근 24시간 AI 선별 관심 자료")
      : (selectedItems === null ? "최근 24시간 전체 자료" : "최근 24시간 AI 선별 자료");
    searchLabel.textContent = activeKeywords.length > 0
      ? "관심 자료 내 검색"
      : "전체 보도자료 검색";
    briefingSearch.placeholder = "제목, 내용 검색";

    statusText.textContent = formatWindow(briefing.windowStart, briefing.windowEnd);
    renderCurrentView();
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
briefingSearch.addEventListener("input", renderCurrentView);
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
