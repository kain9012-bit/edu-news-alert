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
const DEFAULT_SOURCE_IDS = [
  "moe",
  "jeonbuk",
  "jeonbuk_institute",
  "jeonbuk_support",
  "seoul",
  "gyeonggi",
  "busan",
  "daegu",
  "incheon",
  "jngj_s1n1",
  "jngj_s1n2",
  "jngj_s1n3",
  "daejeon",
  "ulsan",
  "sejong",
  "gangwon",
  "chungbuk",
  "chungnam",
  "gyeongbuk",
  "gyeongnam",
  "jeju"
];
const SOURCE_SCHEMA_VERSION = 2;

chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.warn("setPanelBehavior 실패", error));

const openWindows = new Set();

function migrateSourceIds(sourceIds, schemaVersion) {
  if (!Array.isArray(sourceIds)) return DEFAULT_SOURCE_IDS;
  if (schemaVersion === SOURCE_SCHEMA_VERSION) return sourceIds;

  const migrated = new Set(sourceIds.filter((id) => id !== "gwangju" && id !== "jeonnam"));
  if (sourceIds.includes("gwangju") || sourceIds.includes("jeonnam")) {
    migrated.add("jngj_s1n1");
    migrated.add("jngj_s1n2");
    migrated.add("jngj_s1n3");
  }
  return Array.from(migrated).filter((id) => DEFAULT_SOURCE_IDS.includes(id));
}

chrome.runtime.onInstalled.addListener(async () => {
  const existing = await chrome.storage.local.get({
    dataUrl: DEFAULT_DATA_URL,
    keywords: DEFAULT_KEYWORDS,
    enabledSourceIds: DEFAULT_SOURCE_IDS,
    sourceSchemaVersion: 0,
    searchMode: "title_summary"
  });
  const enabledSourceIds = migrateSourceIds(existing.enabledSourceIds, existing.sourceSchemaVersion);

  await chrome.storage.local.set({
    dataUrl: existing.dataUrl || DEFAULT_DATA_URL,
    keywords: Array.isArray(existing.keywords) ? existing.keywords : DEFAULT_KEYWORDS,
    enabledSourceIds,
    sourceSchemaVersion: SOURCE_SCHEMA_VERSION,
    searchMode: existing.searchMode || "title_summary"
  });
});

chrome.commands.onCommand.addListener((command, tab) => {
  if (command !== "open-news-alert") return;
  const windowId = tab && tab.windowId;
  if (windowId == null) return;

  if (openWindows.has(windowId)) {
    openWindows.delete(windowId);
    try {
      chrome.runtime.sendMessage({ type: "closeSidePanel", windowId }, () => {
        void chrome.runtime.lastError;
      });
    } catch (error) {
      // 이미 닫힌 사이드바는 무시한다.
    }
    return;
  }

  openWindows.add(windowId);
  chrome.sidePanel
    .open({ windowId })
    .catch((error) => console.warn("사이드바 열기 실패", error));
});

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === "sidePanelOpened" && message.windowId != null) {
    openWindows.add(message.windowId);
  }
  if (message?.type === "sidePanelClosed" && message.windowId != null) {
    openWindows.delete(message.windowId);
  }
});
