import { useEffect, useMemo, useState } from "react";
import { ExternalLink, Search } from "lucide-react";
import type { NewsItem } from "../types";
import { dateLabel, fetchNews, fetchReportIndex, fetchSelectedIds } from "../lib/data";
import { DateRange } from "./DateRange";

interface Row {
  id: string;
  sid: string;
  source: string;
  title: string;
  date: string;
  url?: string;
}

// 기관 필터 정렬 순서: 교육부 → 정식 시도교육청 순(광주·전남은 통합청 하나).
const SOURCE_ORDER = [
  "moe",
  "seoul",
  "jngj_s1n1",
  "busan",
  "daegu",
  "incheon",
  "daejeon",
  "ulsan",
  "sejong",
  "gyeonggi",
  "gangwon",
  "chungbuk",
  "chungnam",
  "jeonbuk",
  "gyeongbuk",
  "gyeongnam",
  "jeju",
];
const sourceRank = (sid: string) => {
  const i = SOURCE_ORDER.indexOf(sid);
  return i < 0 ? SOURCE_ORDER.length : i;
};

export function ArchiveTab() {
  const [rows, setRows] = useState<Row[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [org, setOrg] = useState("all");
  const [range, setRange] = useState({ from: "", to: "" });
  const [selOnly, setSelOnly] = useState(false);

  useEffect(() => {
    (async () => {
      const news = await fetchNews();
      const cleaned: Row[] = news
        .map((n: NewsItem) => ({
          id: String(n.id || ""),
          sid: String(n.sourceId || ""),
          source: String(n.source || "기타"),
          title: String(n.title || ""),
          date: String(n.date || "").slice(0, 10),
          url: n.url,
        }))
        .filter((r) => r.title && r.date);
      setRows(cleaned);
      setLoading(false);
      // 발행된 모든 보고서의 briefing을 합쳐 선정 여부를 집계한다.
      const idx = await fetchReportIndex();
      const reportDates = (idx?.reports || []).map((r) => r.date);
      fetchSelectedIds(reportDates).then(setSelected);
    })();
  }, []);

  const dates = useMemo(
    () => [...new Set(rows.map((r) => r.date))].sort().reverse(),
    [rows]
  );
  const orgs = useMemo(() => {
    const sidByName = new Map<string, string>();
    for (const r of rows) if (!sidByName.has(r.source)) sidByName.set(r.source, r.sid);
    return [...sidByName.keys()].sort((a, b) => {
      const d = sourceRank(sidByName.get(a) || "") - sourceRank(sidByName.get(b) || "");
      return d !== 0 ? d : a < b ? -1 : 1;
    });
  }, [rows]);

  const filtered = useMemo(() => {
    const query = q.trim().toLowerCase();
    return rows.filter((r) => {
      if (range.from && r.date < range.from) return false;
      if (range.to && r.date > range.to) return false;
      if (org !== "all" && r.source !== org) return false;
      if (selOnly && !selected.has(r.id)) return false;
      if (query && r.title.toLowerCase().indexOf(query) < 0) return false;
      return true;
    });
  }, [rows, q, org, range, selOnly, selected]);

  const grouped = useMemo(() => {
    const by: Record<string, Row[]> = {};
    for (const r of filtered) (by[r.date] = by[r.date] || []).push(r);
    return Object.keys(by)
      .sort()
      .reverse()
      .map((d) => ({
        date: d,
        items: by[d].sort((a, b) => (a.source < b.source ? -1 : a.source > b.source ? 1 : a.title < b.title ? -1 : 1)),
      }));
  }, [filtered]);

  const selectedCount = rows.filter((r) => selected.has(r.id)).length;

  return (
    <div>
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-slate-900">전국 보도자료</h1>
        <p className="text-slate-500 text-sm mt-1">
          교육부와 전국 시도교육청 본청 보도자료 전체 수집분입니다. 교육동향으로 선정된 자료는 <b className="text-green-700">선정</b>으로 표시됩니다.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-2 sm:gap-3 mb-5">
        <div className="bg-slate-50 rounded-lg p-3">
          <p className="text-xs text-slate-500">수집 기간</p>
          <p className="text-lg sm:text-xl font-bold text-slate-900">{dates.length}일</p>
        </div>
        <div className="bg-slate-50 rounded-lg p-3">
          <p className="text-xs text-slate-500">전체 수집</p>
          <p className="text-lg sm:text-xl font-bold text-slate-900">{rows.length}건</p>
        </div>
        <div className="bg-slate-50 rounded-lg p-3">
          <p className="text-xs text-slate-500">교육동향 선정</p>
          <p className="text-lg sm:text-xl font-bold text-blue-700">{selectedCount}건</p>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-3 sm:p-4 flex flex-wrap items-end gap-3 mb-5">
        <DateRange
          from={range.from}
          to={range.to}
          min={dates[dates.length - 1]}
          max={dates[0]}
          onChange={setRange}
        />
        <label className="flex flex-col gap-1 flex-1 min-w-0 sm:flex-none">
          <span className="text-xs font-bold text-slate-500">기관</span>
          <select value={org} onChange={(e) => setOrg(e.target.value)} className="w-full h-10 border border-slate-200 rounded-lg px-3 text-sm bg-white sm:max-w-[160px]">
            <option value="all">전체 기관</option>
            {orgs.map((o) => (
              <option key={o} value={o}>{o}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 w-full sm:w-auto sm:flex-1 sm:min-w-[180px]">
          <span className="text-xs font-bold text-slate-500">제목 검색</span>
          <span className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              type="search"
              placeholder="예: 인공지능, 기초학력"
              className="w-full h-10 border border-slate-200 rounded-lg pl-9 pr-3 text-sm"
            />
          </span>
        </label>
        <label className="inline-flex items-center gap-2 h-10 text-sm text-slate-700 whitespace-nowrap">
          <input type="checkbox" checked={selOnly} onChange={(e) => setSelOnly(e.target.checked)} className="w-4 h-4 accent-blue-600" />
          교육동향 선정만
        </label>
      </div>

      {loading ? (
        <p className="text-slate-500 py-16 text-center">보도자료를 불러오는 중…</p>
      ) : !grouped.length ? (
        <p className="text-slate-500 py-16 text-center">조건에 맞는 보도자료가 없습니다.</p>
      ) : (
        <div className="space-y-6">
          {grouped.map((g) => {
            const sel = g.items.filter((x) => selected.has(x.id)).length;
            return (
              <section key={g.date}>
                <h2 className="text-sm font-bold text-blue-700 border-b-2 border-blue-100 pb-1.5 mb-2">
                  {dateLabel(g.date)} · {g.items.length}건, 선정 {sel}건
                </h2>
                <ul className="bg-white border border-slate-200 rounded-xl overflow-hidden divide-y divide-slate-50">
                  {g.items.map((it) => {
                    const isSel = selected.has(it.id);
                    return (
                      <li
                        key={it.id}
                        className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 hover:bg-slate-50"
                      >
                        <span className="order-1 text-xs font-bold text-slate-500 sm:w-[110px] sm:shrink-0">
                          {it.source}
                        </span>
                        <span
                          className={`order-2 ml-auto sm:order-3 sm:ml-0 shrink-0 text-xs font-bold px-2 py-0.5 rounded-full ${
                            isSel ? "bg-green-50 text-green-700" : "bg-slate-100 text-slate-400"
                          }`}
                        >
                          {isSel ? "선정" : "미선정"}
                        </span>
                        <span className="order-3 w-full sm:order-2 sm:w-auto sm:flex-1 text-slate-800 break-keep">
                          {it.url ? (
                            <a href={it.url} target="_blank" rel="noopener noreferrer" className="hover:text-blue-700 hover:underline inline-flex items-baseline gap-1">
                              {it.title}
                              <ExternalLink className="w-3 h-3 shrink-0 self-center text-slate-300" />
                            </a>
                          ) : (
                            it.title
                          )}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
