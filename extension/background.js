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
const ALARM_NAME = "check-news";

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

async function getOptions() {
  const saved = await chrome.storage.local.get({
    dataUrl: DEFAULT_DATA_URL,
    keywords: DEFAULT_KEYWORDS,
    enabledSourceIds: DEFAULT_SOURCE_IDS,
    sourceSchemaVersion: 0,
    searchMode: "title_summary",
    intervalMinutes: 60,
    seenIds: [],
    recentMatches: [],
    lastCheckedAt: null,
    lastError: null
  });

  const enabledSourceIds = migrateSourceIds(saved.enabledSourceIds, saved.sourceSchemaVersion);
  if (saved.sourceSchemaVersion !== SOURCE_SCHEMA_VERSION) {
    await chrome.storage.local.set({ enabledSourceIds, sourceSchemaVersion: SOURCE_SCHEMA_VERSION });
  }

  return {
    ...saved,
    keywords: normalizeKeywords(saved.keywords),
    enabledSourceIds,
    intervalMinutes: Math.max(15, Number(saved.intervalMinutes) || 60)
  };
}

function normalizeKeywords(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  return String(value || "")
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

async function scheduleAlarm() {
  const options = await getOptions();
  await chrome.alarms.clear(ALARM_NAME);
  await chrome.alarms.create(ALARM_NAME, {
    delayInMinutes: 1,
    periodInMinutes: options.intervalMinutes
  });
}

function itemText(item, mode) {
  const parts = [item.title || ""];
  if (mode !== "title_only") {
    parts.push(item.summary || "");
  }
  return parts.join("\n").toLowerCase();
}

function matchKeywords(item, keywords, mode) {
  const text = itemText(item, mode);
  return keywords.filter((keyword) => text.includes(keyword.toLowerCase()));
}

async function fetchNews(dataUrl) {
  const url = new URL(dataUrl);
  url.searchParams.set("t", Date.now().toString());
  const response = await fetch(url.toString(), { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`데이터를 불러오지 못했습니다. (${response.status})`);
  }
  const data = await response.json();
  return Array.isArray(data) ? data : data.items || [];
}

async function checkNews({ notify = true } = {}) {
  const options = await getOptions();
  const seen = new Set(options.seenIds || []);
  const enabled = new Set(options.enabledSourceIds || []);
  const news = await fetchNews(options.dataUrl);

  const matches = news
    .filter((item) => enabled.has(item.sourceId))
    .map((item) => ({ ...item, matchedKeywords: matchKeywords(item, options.keywords, options.searchMode) }))
    .filter((item) => item.matchedKeywords.length > 0);

  const newMatches = matches.filter((item) => item.id && !seen.has(item.id));
  const nextSeenIds = Array.from(new Set([...newMatches.map((item) => item.id), ...(options.seenIds || [])])).slice(0, 2000);
  const recentMatches = [...newMatches, ...(options.recentMatches || [])].slice(0, 50);

  await chrome.storage.local.set({
    seenIds: nextSeenIds,
    recentMatches,
    lastCheckedAt: new Date().toISOString(),
    lastError: null,
    lastMatchCount: matches.length,
    lastNewMatchCount: newMatches.length
  });

  if (notify && newMatches.length > 0) {
    const first = newMatches[0];
    await chrome.storage.local.set({ lastNotificationUrl: first.url || null });
    await openNewsPanel();
  }

  return { total: news.length, matches: matches.length, newMatches: newMatches.length };
}

async function openNewsPanel() {
  const currentWindow = await chrome.windows.getLastFocused().catch(() => null);
  if (!currentWindow?.id) return;

  await chrome.sidePanel.open({ windowId: currentWindow.id }).then(() => {
    openWindows.add(currentWindow.id);
  }).catch((error) => {
    console.warn("사이드바 열기 실패", error);
  });
}

chrome.runtime.onInstalled.addListener(async () => {
  const existing = await chrome.storage.local.get(["keywords", "dataUrl"]);
  if (!existing.keywords) {
    await chrome.storage.local.set({
      dataUrl: DEFAULT_DATA_URL,
      keywords: DEFAULT_KEYWORDS,
      enabledSourceIds: DEFAULT_SOURCE_IDS,
      sourceSchemaVersion: SOURCE_SCHEMA_VERSION,
      searchMode: "title_summary",
      intervalMinutes: 60,
      seenIds: [],
      recentMatches: []
    });
  }
  await scheduleAlarm();
  await checkNews({ notify: false }).catch(async (error) => {
    await chrome.storage.local.set({ lastError: error.message, lastCheckedAt: new Date().toISOString() });
  });
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM_NAME) {
    checkNews().catch(async (error) => {
      chrome.storage.local.set({ lastError: error.message, lastCheckedAt: new Date().toISOString() });
    });
  }
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
      // 무시한다.
    }
  } else {
    openWindows.add(windowId);
    chrome.sidePanel
      .open({ windowId })
      .catch((error) => console.warn("사이드바 열기 실패", error));
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "sidePanelOpened" && message.windowId != null) {
    openWindows.add(message.windowId);
    return false;
  }
  if (message?.type === "sidePanelClosed" && message.windowId != null) {
    openWindows.delete(message.windowId);
    return false;
  }
  if (message?.type === "CHECK_NOW") {
    checkNews({ notify: true })
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "RESCHEDULE") {
    scheduleAlarm()
      .then(() => sendResponse({ ok: true }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  return false;
});
