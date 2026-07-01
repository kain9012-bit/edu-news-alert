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
const SOURCES = [
  { id: "moe", name: "교육부", sourceIds: ["moe"] },
  { id: "jeonbuk_group", name: "전북특별자치도교육청", sourceIds: ["jeonbuk", "jeonbuk_institute", "jeonbuk_support"] },
  { id: "seoul", name: "서울특별시교육청", sourceIds: ["seoul"] },
  { id: "gyeonggi", name: "경기도교육청", sourceIds: ["gyeonggi"] },
  { id: "busan", name: "부산광역시교육청", sourceIds: ["busan"] },
  { id: "daegu", name: "대구광역시교육청", sourceIds: ["daegu"] },
  { id: "incheon", name: "인천광역시교육청", sourceIds: ["incheon"] },
  { id: "gwangju", name: "광주광역시교육청", sourceIds: ["gwangju"] },
  { id: "daejeon", name: "대전광역시교육청", sourceIds: ["daejeon"] },
  { id: "ulsan", name: "울산광역시교육청", sourceIds: ["ulsan"] },
  { id: "sejong", name: "세종특별자치시교육청", sourceIds: ["sejong"] },
  { id: "gangwon", name: "강원특별자치도교육청", sourceIds: ["gangwon"] },
  { id: "chungbuk", name: "충청북도교육청", sourceIds: ["chungbuk"] },
  { id: "chungnam", name: "충청남도교육청", sourceIds: ["chungnam"] },
  { id: "jeonnam", name: "전라남도교육청", sourceIds: ["jeonnam"] },
  { id: "gyeongbuk", name: "경상북도교육청", sourceIds: ["gyeongbuk"] },
  { id: "gyeongnam", name: "경상남도교육청", sourceIds: ["gyeongnam"] },
  { id: "jeju", name: "제주특별자치도교육청", sourceIds: ["jeju"] }
];

const form = document.querySelector("#optionsForm");
const dataUrl = document.querySelector("#dataUrl");
const keywords = document.querySelector("#keywords");
const intervalMinutes = document.querySelector("#intervalMinutes");
const sources = document.querySelector("#sources");
const savedText = document.querySelector("#savedText");
const resetSeen = document.querySelector("#resetSeen");

function renderSources(enabledSourceIds) {
  const enabled = new Set(enabledSourceIds);
  sources.innerHTML = SOURCES.map((source) => `
    <label>
      <input type="checkbox" value="${source.id}" ${source.sourceIds.some((id) => enabled.has(id)) ? "checked" : ""}>
      ${source.name}
    </label>
  `).join("");
}

function selectedSources() {
  const selectedGroupIds = new Set(Array.from(sources.querySelectorAll("input:checked")).map((input) => input.value));
  return SOURCES
    .filter((source) => selectedGroupIds.has(source.id))
    .flatMap((source) => source.sourceIds);
}

function allSourceIds() {
  return SOURCES.flatMap((source) => source.sourceIds);
}

async function loadOptions() {
  const state = await chrome.storage.local.get({
    dataUrl: DEFAULT_DATA_URL,
    keywords: DEFAULT_KEYWORDS,
    enabledSourceIds: allSourceIds(),
    searchMode: "title_summary",
    intervalMinutes: 60
  });

  dataUrl.value = state.dataUrl;
  keywords.value = Array.isArray(state.keywords) ? state.keywords.join("\n") : String(state.keywords || "");
  intervalMinutes.value = state.intervalMinutes;
  form.searchMode.value = state.searchMode;
  renderSources(state.enabledSourceIds);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const nextKeywords = keywords.value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);
  const nextSources = selectedSources();

  await chrome.storage.local.set({
    dataUrl: dataUrl.value.trim(),
    keywords: nextKeywords,
    enabledSourceIds: nextSources.length > 0 ? nextSources : allSourceIds(),
    searchMode: form.searchMode.value,
    intervalMinutes: Math.max(15, Number(intervalMinutes.value) || 60)
  });
  await chrome.runtime.sendMessage({ type: "RESCHEDULE" });
  savedText.textContent = "저장했습니다.";
  setTimeout(() => { savedText.textContent = ""; }, 2500);
});

resetSeen.addEventListener("click", async () => {
  await chrome.storage.local.set({ seenIds: [], recentMatches: [] });
  savedText.textContent = "알림 기록을 초기화했습니다.";
  setTimeout(() => { savedText.textContent = ""; }, 2500);
});

loadOptions();
