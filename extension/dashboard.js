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

const statusEl = document.querySelector("#dashboardStatus");
const refreshButton = document.querySelector("#refreshDashboard");
const searchInput = document.querySelector("#searchInput");
const sourceFilter = document.querySelector("#sourceFilter");
const keywordFilter = document.querySelector("#keywordFilter");
const resultCount = document.querySelector("#resultCount");
const listEl = document.querySelector("#dashboardList");

let allItems = [];
let keywords = DEFAULT_KEYWORDS;

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function sourceName(item) {
  return item.sourceName || item.source || item.sourceId || "교육청";
}

function itemDate(item) {
  const raw = item.date || item.publishedAt || item.collectedAt;
  if (!raw) return null;
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function itemText(item) {
  return [
    item.title,
    item.summary,
    item.contentPreview,
    sourceName(item)
  ].join("\n").toLowerCase();
}

function matchedKeywords(item) {
  const text = itemText(item);
  return keywords.filter((keyword) => text.includes(keyword.toLowerCase()));
}

function formatDate(item) {
  const date = itemDate(item);
  if (!date) return "";
  return new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium" }).format(date);
}

async function fetchItems(dataUrl) {
  const url = new URL(dataUrl);
  url.searchParams.set("t", Date.now().toString());
  const response = await fetch(url.toString(), { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`자료를 불러오지 못했습니다. (${response.status})`);
  }
  const data = await response.json();
  return Array.isArray(data) ? data : data.items || [];
}

function fillFilters(items) {
  const currentSource = sourceFilter.value;
  const sources = Array.from(new Set(items.map(sourceName))).sort((a, b) => a.localeCompare(b, "ko"));
  sourceFilter.innerHTML = `<option value="">전체 기관</option>` + sources
    .map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`)
    .join("");
  sourceFilter.value = sources.includes(currentSource) ? currentSource : "";

  const currentKeyword = keywordFilter.value;
  keywordFilter.innerHTML = `<option value="">전체 키워드</option>` + keywords
    .map((keyword) => `<option value="${escapeHtml(keyword)}">${escapeHtml(keyword)}</option>`)
    .join("");
  keywordFilter.value = keywords.includes(currentKeyword) ? currentKeyword : "";
}

function filteredItems() {
  const query = searchInput.value.trim().toLowerCase();
  const selectedSource = sourceFilter.value;
  const selectedKeyword = keywordFilter.value;

  return allItems
    .filter((item) => !selectedSource || sourceName(item) === selectedSource)
    .filter((item) => !selectedKeyword || matchedKeywords(item).includes(selectedKeyword))
    .filter((item) => !query || itemText(item).includes(query))
    .sort((a, b) => (itemDate(b)?.getTime() || 0) - (itemDate(a)?.getTime() || 0));
}

function render() {
  const items = filteredItems();
  resultCount.textContent = `${items.length.toLocaleString("ko-KR")}건`;

  if (items.length === 0) {
    listEl.className = "dashboardList empty";
    listEl.textContent = "표시할 보도자료가 없습니다.";
    return;
  }

  listEl.className = "dashboardList";
  listEl.innerHTML = items.map((item) => {
    const matches = matchedKeywords(item);
    const keywordHtml = matches.length
      ? `<div class="keywordLine">${matches.map((keyword) => `<span>${escapeHtml(keyword)}</span>`).join("")}</div>`
      : "";
    const summary = item.summary || item.contentPreview || "";
    return `
      <article class="newsRow">
        <div class="newsHead">
          <span class="source">${escapeHtml(sourceName(item))}</span>
          <time>${escapeHtml(formatDate(item))}</time>
        </div>
        <a href="${escapeHtml(item.url || "#")}" target="_blank" rel="noreferrer">${escapeHtml(item.title || "제목 없음")}</a>
        ${summary ? `<p>${escapeHtml(summary)}</p>` : ""}
        ${keywordHtml}
      </article>
    `;
  }).join("");
}

async function loadDashboard() {
  refreshButton.disabled = true;
  statusEl.textContent = "저장된 보도자료를 불러오는 중입니다.";
  try {
    const state = await chrome.storage.local.get({
      dataUrl: DEFAULT_DATA_URL,
      keywords: DEFAULT_KEYWORDS
    });
    keywords = Array.isArray(state.keywords) ? state.keywords : DEFAULT_KEYWORDS;
    allItems = await fetchItems(state.dataUrl || DEFAULT_DATA_URL);
    fillFilters(allItems);
    statusEl.textContent = `마지막 갱신: ${new Intl.DateTimeFormat("ko-KR", { dateStyle: "short", timeStyle: "short" }).format(new Date())}`;
    render();
  } catch (error) {
    statusEl.textContent = error.message || "자료를 불러오지 못했습니다.";
    listEl.className = "dashboardList empty";
    listEl.textContent = "데이터 주소와 GitHub Pages 설정을 확인해 주세요.";
  } finally {
    refreshButton.disabled = false;
  }
}

for (const control of [searchInput, sourceFilter, keywordFilter]) {
  control.addEventListener("input", render);
  control.addEventListener("change", render);
}

refreshButton.addEventListener("click", loadDashboard);

loadDashboard();
