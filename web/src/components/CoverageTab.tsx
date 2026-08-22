import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, ExternalLink, Search } from "lucide-react";
import type { Coverage, CoverageItem } from "../types";
import { fetchCoverage } from "../lib/data";
import { DateRange } from "./DateRange";

// 도넛 그래프 반지름 46 기준 원둘레.
const DONUT_CIRC = 2 * Math.PI * 46;

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="bg-slate-50 rounded-lg p-3">
      <p className="text-xs text-slate-500 break-keep">{label}</p>
      <p className={`text-lg sm:text-xl font-bold ${accent ? "text-blue-700" : "text-slate-900"}`}>
        {value}
      </p>
    </div>
  );
}

function ReleaseRow({ item }: { item: CoverageItem }) {
  const [open, setOpen] = useState(false);
  const covered = item.articleCount > 0;
  return (
    <li className="border-b border-slate-100 last:border-0">
      <button
        type="button"
        onClick={() => covered && setOpen((v) => !v)}
        className={`w-full text-left px-4 py-3 flex items-start gap-3 ${
          covered ? "hover:bg-slate-50 cursor-pointer" : "cursor-default"
        }`}
        aria-expanded={open}
      >
        <span className="shrink-0 mt-0.5 w-4 text-slate-400">
          {covered ? (
            open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />
          ) : null}
        </span>

        <span className="min-w-0 flex-1">
          <span className="block text-slate-800 break-keep">{item.title}</span>
          <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
            <span className="whitespace-nowrap">{item.date}</span>
            {item.department && (
              <span className="px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 font-bold whitespace-nowrap">
                {item.department}
              </span>
            )}
          </span>
        </span>

        <span
          className={`shrink-0 text-xs font-bold px-2 py-0.5 rounded-full whitespace-nowrap ${
            covered ? "bg-green-50 text-green-700" : "bg-slate-100 text-slate-400"
          }`}
        >
          {covered ? `게재 ${item.articleCount}` : "확인 안 됨"}
        </span>
      </button>

      {open && covered && (
        <ul className="mb-3 ml-11 mr-4 pl-4 border-l-2 border-slate-100 space-y-1.5">
          {item.articles.map((a, i) => (
            <li key={`${a.url}-${i}`} className="text-sm flex flex-wrap items-baseline gap-x-2">
              <span className="font-bold text-slate-500 whitespace-nowrap">{a.publisher}</span>
              <a
                href={a.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-slate-700 hover:text-blue-700 hover:underline break-keep inline-flex items-baseline gap-1"
              >
                {a.title}
                <ExternalLink className="w-3 h-3 shrink-0 self-center text-slate-300" />
              </a>
              {a.publishedAt && (
                <span className="text-xs text-slate-400 whitespace-nowrap">{a.publishedAt}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export function CoverageTab() {
  const [data, setData] = useState<Coverage | null>(null);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [range, setRange] = useState({ from: "", to: "" });
  const [dept, setDept] = useState("all");
  const [uncoveredOnly, setUncoveredOnly] = useState(false);
  const [statsOpen, setStatsOpen] = useState(false);

  useEffect(() => {
    fetchCoverage().then((d) => {
      setData(d);
      setLoading(false);
    });
  }, []);

  const items = data?.items || [];

  const depts = useMemo(() => {
    const names = new Set<string>();
    for (const it of items) if (it.department) names.add(it.department);
    return [...names].sort();
  }, [items]);

  // 날짜 입력의 선택 가능 범위는 실제 자료가 있는 구간으로 제한한다.
  const bounds = useMemo(() => {
    const dates = items.map((it) => it.date).filter(Boolean).sort();
    return { min: dates[0] || "", max: dates[dates.length - 1] || "" };
  }, [items]);

  const filtered = useMemo(() => {
    const query = q.trim().toLowerCase();
    return items.filter((it) => {
      if (range.from && it.date < range.from) return false;
      if (range.to && it.date > range.to) return false;
      if (dept !== "all" && (it.department || "") !== dept) return false;
      if (uncoveredOnly && it.articleCount > 0) return false;
      if (!query) return true;
      if (it.title.toLowerCase().includes(query)) return true;
      return it.articles.some(
        (a) =>
          a.title.toLowerCase().includes(query) || a.publisher.toLowerCase().includes(query)
      );
    });
  }, [items, q, dept, uncoveredOnly, range]);

  // 아래 통계 패널도 지금 보고 있는 조건을 그대로 따른다.
  const publisherStats = useMemo(() => {
    const counts = new Map<string, number>();
    for (const it of filtered)
      for (const a of it.articles) counts.set(a.publisher, (counts.get(a.publisher) || 0) + 1);
    return [...counts.entries()]
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count || (a.name < b.name ? -1 : 1));
  }, [filtered]);

  const deptStats = useMemo(() => {
    const rows = new Map<string, { releaseCount: number; coveredCount: number; articleCount: number }>();
    for (const it of filtered) {
      const name = it.department || "미확인";
      const row = rows.get(name) || { releaseCount: 0, coveredCount: 0, articleCount: 0 };
      row.releaseCount += 1;
      row.articleCount += it.articleCount;
      if (it.articleCount > 0) row.coveredCount += 1;
      rows.set(name, row);
    }
    return [...rows.entries()]
      .map(([name, row]) => ({ name, ...row }))
      // 순위는 부서가 배포한 보도자료 건수 기준으로 매긴다.
      .sort(
        (a, b) =>
          b.releaseCount - a.releaseCount ||
          b.articleCount - a.articleCount ||
          (a.name < b.name ? -1 : 1)
      );
  }, [filtered]);

  // 일별 보도자료 배포 건수 추이(빈 날은 0으로 채워 흐름을 그대로 보여준다).
  const dailyStats = useMemo(() => {
    const byDay = new Map<string, number>();
    for (const it of filtered) {
      if (it.date) byDay.set(it.date, (byDay.get(it.date) || 0) + 1);
    }
    const keys = [...byDay.keys()].sort();
    if (!keys.length) return [] as { key: string; label: string; count: number; monday: boolean }[];
    const out: { key: string; label: string; count: number; monday: boolean }[] = [];
    const cursor = new Date(`${keys[0]}T00:00:00+09:00`);
    const last = new Date(`${keys[keys.length - 1]}T00:00:00+09:00`);
    while (cursor <= last) {
      const key = cursor.toISOString().slice(0, 10);
      const [, m, dd] = key.split("-");
      out.push({
        key,
        label: `${Number(m)}/${Number(dd)}`,
        count: byDay.get(key) || 0,
        monday: (cursor.getDay() + 6) % 7 === 0,
      });
      cursor.setDate(cursor.getDate() + 1);
    }
    return out;
  }, [filtered]);
  const dailyMax = Math.max(1, ...dailyStats.map((d) => d.count));

  // 부서별 보도자료 수 도넛(상위 9개 + 기타).
  const donutData = useMemo(() => {
    const palette = [
      "#256ef4", "#0b50d0", "#4c87f6", "#228738", "#9e6a00",
      "#d95f5f", "#7a5fd9", "#2a9d8f", "#b1518e", "#8a949e",
    ];
    const top = deptStats.slice(0, 9);
    const restCount = deptStats.slice(9).reduce((s, d) => s + d.releaseCount, 0);
    const rows = [...top.map((d) => ({ name: d.name, count: d.releaseCount }))];
    if (restCount > 0) rows.push({ name: "기타", count: restCount });
    const total = rows.reduce((s, r) => s + r.count, 0);
    let offset = 0;
    const slices = rows.map((r, i) => {
      const length = total ? (r.count / total) * DONUT_CIRC : 0;
      const slice = { ...r, color: palette[i % palette.length], length, offset };
      offset += length;
      return slice;
    });
    return { total, slices };
  }, [deptStats]);

  if (loading) return <p className="text-slate-500 py-16 text-center">언론 게재현황을 불러오는 중…</p>;
  if (!data || !items.length)
    return (
      <p className="text-slate-500 py-16 text-center">
        아직 수집된 언론 보도 자료가 없습니다.
      </p>
    );

  // 통계는 지금 보고 있는 조건(기간·부서)에 맞춰 계산한다.
  const shown = {
    releases: filtered.length,
    covered: filtered.filter((it) => it.articleCount > 0).length,
    articles: filtered.reduce((sum, it) => sum + it.articleCount, 0),
  };
  const rate = shown.releases ? Math.round((shown.covered / shown.releases) * 100) : 0;

  return (
    <div>
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-slate-900">전북 언론 게재현황</h1>
        <p className="text-slate-500 text-sm mt-1 break-keep">
          전북교육청 보도자료를 어느 언론사가 기사로 다뤘는지 모아봅니다. 제목을 누르면 기사 목록이 열립니다.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-2 sm:gap-3 mb-5">
        <Stat label="보도자료" value={`${shown.releases}건`} />
        <Stat label="게재율" value={`${rate}%`} accent />
        <Stat label="게재 기사" value={`${shown.articles}건`} />
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-3 sm:p-4 flex flex-wrap items-end gap-3 mb-5">
        <DateRange from={range.from} to={range.to} min={bounds.min} max={bounds.max} onChange={setRange} />
        <label className="flex flex-col gap-1 flex-1 min-w-0 sm:flex-none">
          <span className="text-xs font-bold text-slate-500">부서</span>
          <select
            value={dept}
            onChange={(e) => setDept(e.target.value)}
            className="w-full h-10 border border-slate-200 rounded-lg px-3 text-sm bg-white sm:max-w-[180px]"
          >
            <option value="all">전체 부서</option>
            {depts.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 w-full sm:w-auto sm:flex-1 sm:min-w-[180px]">
          <span className="text-xs font-bold text-slate-500">검색</span>
          <span className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              type="search"
              placeholder="보도자료 제목, 기사 제목, 언론사"
              className="w-full h-10 border border-slate-200 rounded-lg pl-9 pr-3 text-sm"
            />
          </span>
        </label>
        <label className="inline-flex items-center gap-2 h-10 text-sm text-slate-700 whitespace-nowrap w-full sm:w-auto">
          <input
            type="checkbox"
            checked={uncoveredOnly}
            onChange={(e) => setUncoveredOnly(e.target.checked)}
            className="w-4 h-4 accent-blue-600"
          />
          확인 안 된 자료만
        </label>
      </div>

      <div className="mb-5">
        <button
          type="button"
          onClick={() => setStatsOpen((v) => !v)}
          aria-expanded={statsOpen}
          className="w-full flex items-center gap-2 px-4 py-3 bg-white border border-slate-200 rounded-xl text-left hover:bg-slate-50 transition-colors"
        >
          {statsOpen ? (
            <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />
          ) : (
            <ChevronRight className="w-4 h-4 text-slate-400 shrink-0" />
          )}
          <span className="font-bold text-slate-800">보도자료 추이 · 부서별 비중</span>
          <span className="ml-auto text-xs text-slate-400 whitespace-nowrap">
            부서 {deptStats.length}곳
          </span>
        </button>
        {statsOpen && (
          <div className="mt-3">
            <div className="grid gap-4 sm:grid-cols-2">
        <section className="bg-white border border-slate-200 rounded-xl p-4">
          <h2 className="text-sm font-bold text-blue-700 border-b-2 border-blue-100 pb-1.5 mb-3">
            일별 보도자료 수 추이
          </h2>
          {dailyStats.length ? (
            <svg viewBox="0 0 320 150" className="w-full h-40" role="img" aria-label="일별 보도자료 수 추이">
              {/* 세로 눈금(월요일) */}
              {dailyStats.map((d, i) =>
                d.monday ? (
                  <g key={`g-${d.key}`}>
                    <line
                      x1={10 + (i / Math.max(1, dailyStats.length - 1)) * 300}
                      x2={10 + (i / Math.max(1, dailyStats.length - 1)) * 300}
                      y1={10} y2={120} stroke="#e6e8ea" strokeWidth="1"
                    />
                    <text
                      x={10 + (i / Math.max(1, dailyStats.length - 1)) * 300}
                      y={135} textAnchor="middle" fontSize="9" fill="#8a949e"
                    >
                      {d.label}
                    </text>
                  </g>
                ) : null
              )}
              {/* 영역 채움 */}
              <polygon
                fill="#256ef4" opacity="0.08" stroke="none"
                points={`10,120 ${dailyStats
                  .map((d, i) =>
                    `${10 + (i / Math.max(1, dailyStats.length - 1)) * 300},${120 - (d.count / dailyMax) * 105}`
                  )
                  .join(" ")} 310,120`}
              />
              {/* 꺾은선 */}
              <polyline
                fill="none" stroke="#256ef4" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round"
                points={dailyStats
                  .map((d, i) =>
                    `${10 + (i / Math.max(1, dailyStats.length - 1)) * 300},${120 - (d.count / dailyMax) * 105}`
                  )
                  .join(" ")}
              />
              {/* 점 + 값 */}
              {dailyStats.map((d, i) => {
                const x = 10 + (i / Math.max(1, dailyStats.length - 1)) * 300;
                const y = 120 - (d.count / dailyMax) * 105;
                return (
                  <g key={d.key}>
                    <circle cx={x} cy={y} r={d.count ? 2.4 : 0} fill="#0b50d0">
                      <title>{`${d.key} · ${d.count}건`}</title>
                    </circle>
                    {d.count === dailyMax && (
                      <text x={x} y={y - 5} textAnchor="middle" fontSize="9" fontWeight="700" fill="#0b50d0">
                        {d.count}
                      </text>
                    )}
                  </g>
                );
              })}
              <line x1="10" y1="120" x2="310" y2="120" stroke="#cdd1d5" strokeWidth="1" />
            </svg>
          ) : (
            <p className="text-sm text-slate-400 py-8 text-center">표시할 자료가 없습니다.</p>
          )}
          <p className="mt-3 text-xs text-slate-400 break-keep">
            날짜별 배포 건수이며, 세로 눈금은 월요일입니다. 점에 마우스를 올리면 날짜와 건수가 표시됩니다.
          </p>
        </section>

        <section className="bg-white border border-slate-200 rounded-xl p-4">
          <h2 className="text-sm font-bold text-blue-700 border-b-2 border-blue-100 pb-1.5 mb-3">
            부서별 보도자료 비중
          </h2>
          {donutData.total ? (
            <div className="flex flex-wrap items-center gap-4">
              <svg viewBox="0 0 120 120" className="w-36 h-36 shrink-0" role="img" aria-label="부서별 보도자료 비중">
                {donutData.slices.map((sl) => (
                  <circle
                    key={sl.name}
                    cx="60" cy="60" r="46" fill="none"
                    stroke={sl.color} strokeWidth="20"
                    strokeDasharray={`${sl.length} ${DONUT_CIRC - sl.length}`}
                    strokeDashoffset={-sl.offset}
                    transform="rotate(-90 60 60)"
                  >
                    <title>{`${sl.name} ${sl.count}건`}</title>
                  </circle>
                ))}
                <text x="60" y="57" textAnchor="middle" className="fill-slate-900" fontSize="15" fontWeight="700">
                  {donutData.total}건
                </text>
                <text x="60" y="72" textAnchor="middle" className="fill-slate-400" fontSize="9">
                  보도자료
                </text>
              </svg>
              <ul className="flex-1 min-w-[150px] space-y-1">
                {donutData.slices.map((sl) => (
                  <li key={sl.name} className="flex items-center gap-2 text-sm">
                    <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: sl.color }} aria-hidden />
                    <span className="flex-1 min-w-0 truncate text-slate-700">{sl.name}</span>
                    <span className="font-bold text-slate-900 tabular-nums">{sl.count}건</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-sm text-slate-400 py-8 text-center">표시할 자료가 없습니다.</p>
          )}
          <p className="mt-3 text-xs text-slate-400 break-keep">
            부서는 보도자료 게시판에 표시된 담당 부서를 따릅니다.
          </p>
        </section>
            </div>
          </div>
        )}
      </div>
      <ul className="bg-white border border-slate-200 rounded-xl overflow-hidden mb-6">
        {filtered.length ? (
          filtered.map((it) => <ReleaseRow key={it.newsId} item={it} />)
        ) : (
          <li className="px-4 py-10 text-center text-slate-500">조건에 맞는 자료가 없습니다.</li>
        )}
      </ul>
    </div>
  );
}
