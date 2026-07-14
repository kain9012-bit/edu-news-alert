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
const startDate = document.querySelector("#startDate");
const endDate = document.querySelector("#endDate");
const searchInput = document.querySelector("#searchInput");
const sourceFilter = document.querySelector("#sourceFilter");
const keywordFilter = document.querySelector("#keywordFilter");
const resultCount = document.querySelector("#resultCount");
const retentionText = document.querySelector("#retentionText");
const listEl = document.querySelector("#dashboardList");

let allItems = [];
let keywords = DEFAULT_KEYWORDS;
let retentionDays = 14;

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

function sourceName(item) {
  return item.sourceName || item.source || item.sourceId || "교육청";
}

function dateKey(item) {
  const raw = String(item.date || item.publishedAt || item.collectedAt || "");
  const match = raw.match(/^\d{4}-\d{2}-\d{2}/);
  return match ? match[0] : "";
}

function itemText(item) {
  return [item.title, item.summary, item.contentPreview, sourceName(item)].join("\n").toLowerCase();
}

function matchedKeywords(item) {
  const text = itemText(item);
  return keywords.filter((keyword) => text.includes(keyword.toLowerCase()));
}

function formatDate(item) {
  const value = dateKey(item);
  if (!value) return "";
  return new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium" }).format(new Date(`${value}T00:00:00+09:00`));
}

async function fetchJson(url) {
  const requestUrl = new URL(url);
  requestUrl.searchParams.set("t", Date.now().toString());
  const response = await fetch(requestUrl.toString(), { cache: "no-store" });
  if (!response.ok) throw new Error(`자료를 불러오지 못했습니다. (${response.status})`);
  return response.json();
}

function addDays(value, amount) {
  const date = new Date(`${value}T00:00:00+09:00`);
  date.setDate(date.getDate() + amount);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function setQuickRange(days) {
  if (!endDate.max) return;
  endDate.value = endDate.max;
  const requestedStart = addDays(endDate.value, -(days - 1));
  startDate.value = requestedStart < startDate.min ? startDate.min : requestedStart;
  render();
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

function initializeDateRange(items) {
  const dates = items.map(dateKey).filter(Boolean).sort();
  if (dates.length === 0) return;
  const min = dates[0];
  const max = dates[dates.length - 1];
  startDate.min = min;
  startDate.max = max;
  endDate.min = min;
  endDate.max = max;
  if (!startDate.value || !endDate.value) {
    endDate.value = max;
    const sevenDaysAgo = addDays(max, -6);
    startDate.value = sevenDaysAgo < min ? min : sevenDaysAgo;
  }
}

function filteredItems() {
  const query = searchInput.value.trim().toLowerCase();
  const selectedSource = sourceFilter.value;
  const selectedKeyword = keywordFilter.value;
  const from = startDate.value;
  const to = endDate.value;

  return allItems
    .filter((item) => {
      const date = dateKey(item);
      return (!from || date >= from) && (!to || date <= to);
    })
    .filter((item) => !selectedSource || sourceName(item) === selectedSource)
    .filter((item) => !selectedKeyword || matchedKeywords(item).includes(selectedKeyword))
    .filter((item) => !query || itemText(item).includes(query))
    .sort((a, b) => dateKey(b).localeCompare(dateKey(a)));
}

function render() {
  if (startDate.value && endDate.value && startDate.value > endDate.value) {
    resultCount.textContent = "0건";
    listEl.className = "dashboardList empty";
    listEl.textContent = "시작일이 종료일보다 늦습니다.";
    return;
  }

  const items = filteredItems();
  resultCount.textContent = `${items.length.toLocaleString("ko-KR")}건`;
  retentionText.textContent = `최근 ${retentionDays}일 보관 자료`;

  if (items.length === 0) {
    listEl.className = "dashboardList empty";
    listEl.textContent = "조건에 맞는 보도자료가 없습니다.";
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
      keywords: DEFAULT_KEYWORDS,
      enabledSourceIds: []
    });
    const [news, status] = await Promise.all([
      fetchJson(state.dataUrl || DEFAULT_DATA_URL),
      fetchJson(siblingDataUrl(state.dataUrl, "status.json")).catch(() => ({}))
    ]);
    const enabled = new Set(state.enabledSourceIds || []);
    const items = Array.isArray(news) ? news : news.items || [];
    allItems = items.filter((item) => enabled.size === 0 || enabled.has(item.sourceId));
    keywords = Array.isArray(state.keywords) ? state.keywords : DEFAULT_KEYWORDS;
    retentionDays = Number(status.retentionDays) || 14;
    fillFilters(allItems);
    initializeDateRange(allItems);

    const collectedAt = status.collectedAt ? new Date(status.collectedAt) : new Date();
    statusEl.textContent = `마지막 수집 ${new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short" }).format(collectedAt)}`;
    render();
  } catch (error) {
    statusEl.textContent = error.message || "자료를 불러오지 못했습니다.";
    listEl.className = "dashboardList empty";
    listEl.textContent = "데이터 주소와 GitHub Pages 상태를 확인해 주세요.";
  } finally {
    refreshButton.disabled = false;
  }
}

for (const control of [startDate, endDate, searchInput, sourceFilter, keywordFilter]) {
  control.addEventListener("input", render);
  control.addEventListener("change", render);
}

document.querySelectorAll("[data-days]").forEach((button) => {
  button.addEventListener("click", () => setQuickRange(Number(button.dataset.days)));
});
refreshButton.addEventListener("click", loadDashboard);

loadDashboard();
