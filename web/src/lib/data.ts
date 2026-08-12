import type { NewsItem, Report, ReportIndexEntry } from "../types";

// GitHub Pages(edu-news-alert)를 데이터 소스로 그대로 사용한다.
// Access-Control-Allow-Origin: * 이므로 Vercel에서 교차 출처로 바로 불러올 수 있다.
// 배포 환경별로 바꾸려면 .env 에 VITE_DATA_BASE 를 지정한다.
const RAW_BASE =
  (import.meta.env.VITE_DATA_BASE as string | undefined) ||
  "https://kain9012-bit.github.io/edu-news-alert/";
export const DATA_BASE = RAW_BASE.endsWith("/") ? RAW_BASE : RAW_BASE + "/";

async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(DATA_BASE + path, { cache: "no-cache" });
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}

// 탭을 오갈 때마다 다시 받지 않도록 한 세션 동안 결과를 캐시한다(로딩 깜빡임 방지).
let indexCache: Promise<{ reports: ReportIndexEntry[] } | null> | null = null;
let newsCache: Promise<NewsItem[]> | null = null;
const reportCache = new Map<string, Promise<Report | null>>();

export function fetchReportIndex(): Promise<{ reports: ReportIndexEntry[] } | null> {
  if (!indexCache) indexCache = getJson("reports/index.json");
  return indexCache;
}

export function fetchReport(date: string): Promise<Report | null> {
  let p = reportCache.get(date);
  if (!p) {
    p = getJson<Report>(`reports/${date}.json`);
    reportCache.set(date, p);
  }
  return p;
}

export async function fetchNews(): Promise<NewsItem[]> {
  if (!newsCache) {
    newsCache = getJson<NewsItem[] | { items: NewsItem[] }>("news.json").then((data) =>
      !data ? [] : Array.isArray(data) ? data : data.items || []
    );
  }
  return newsCache;
}

interface Briefing {
  selectedItems?: { newsId?: string }[];
}

// 게시일 d 의 선별 결과는 배포일(d 또는 d+1) briefing 파일에 담긴다. 둘 다 시도해 합친다.
export async function fetchSelectedIds(dates: string[]): Promise<Set<string>> {
  const wanted = new Set<string>();
  for (const d of dates) {
    wanted.add(d);
    wanted.add(addDays(d, 1));
  }
  const results = await Promise.all(
    [...wanted].map((d) => getJson<Briefing>(`briefings/${d}.json`))
  );
  const selected = new Set<string>();
  for (const b of results) {
    for (const it of b?.selectedItems || []) {
      if (it?.newsId) selected.add(String(it.newsId));
    }
  }
  return selected;
}

export function addDays(iso: string, n: number): string {
  const d = new Date(iso + "T00:00:00+09:00");
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

export function weekday(iso: string): string {
  const d = new Date(iso + "T00:00:00+09:00");
  return "일월화수목금토".charAt(d.getDay());
}

export function dateLabel(iso: string): string {
  const p = (iso || "").slice(0, 10).split("-");
  if (p.length !== 3) return iso;
  return `${p[0]}. ${Number(p[1])}. ${Number(p[2])}. (${weekday(iso)})`;
}
