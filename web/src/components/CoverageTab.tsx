import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, ExternalLink, Search } from "lucide-react";
import type { Coverage, CoverageItem } from "../types";
import { dateLabel, fetchCoverage } from "../lib/data";

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
          {covered ? `게재 ${item.articleCount}` : "미게재"}
        </span>
      </button>

      {open && covered && (
        <ul className="px-4 pb-3 pl-11 space-y-1.5">
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
  const [period, setPeriod] = useState("all");
  const [dept, setDept] = useState("all");
  const [uncoveredOnly, setUncoveredOnly] = useState(false);

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

  // 최근 N일 기준일은 자료의 최신 날짜에서 되짚는다(수집이 하루 늦어도 어긋나지 않는다).
  const latestDate = useMemo(
    () => items.reduce((max, it) => (it.date > max ? it.date : max), ""),
    [items]
  );

  const filtered = useMemo(() => {
    const query = q.trim().toLowerCase();
    let from = "";
    if (period !== "all" && latestDate) {
      const d = new Date(`${latestDate}T00:00:00+09:00`);
      d.setDate(d.getDate() - (Number(period) - 1));
      from = d.toISOString().slice(0, 10);
    }
    return items.filter((it) => {
      if (from && it.date < from) return false;
      if (dept !== "all" && (it.department || "") !== dept) return false;
      if (uncoveredOnly && it.articleCount > 0) return false;
      if (!query) return true;
      if (it.title.toLowerCase().includes(query)) return true;
      return it.articles.some(
        (a) =>
          a.title.toLowerCase().includes(query) || a.publisher.toLowerCase().includes(query)
      );
    });
  }, [items, q, dept, uncoveredOnly, period, latestDate]);

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
      .sort((a, b) => b.articleCount - a.articleCount || (a.name < b.name ? -1 : 1));
  }, [filtered]);

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
        <h1 className="text-2xl font-bold text-slate-900">언론 게재현황</h1>
        <p className="text-slate-500 text-sm mt-1 break-keep">
          전북교육청 보도자료를 어느 언론사가 기사로 다뤘는지 모아봅니다. 제목을 누르면 기사 목록이 열립니다.
        </p>
        <p className="text-slate-400 text-xs mt-1.5 break-keep">
          ※ 구글 뉴스에 색인된 기사 기준이라 실제 게재 건수보다 적게 잡힐 수 있습니다. 절대 수치보다 자료별·부서별 비교로 보시는 편이 정확합니다.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-2 sm:gap-3 mb-5">
        <Stat label="보도자료" value={`${shown.releases}건`} />
        <Stat label="게재율" value={`${rate}%`} accent />
        <Stat label="게재 기사" value={`${shown.articles}건`} />
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-3 sm:p-4 flex flex-wrap items-end gap-3 mb-5">
        <label className="flex flex-col gap-1 flex-1 min-w-0 sm:flex-none">
          <span className="text-xs font-bold text-slate-500">기간</span>
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            className="w-full h-10 border border-slate-200 rounded-lg px-3 text-sm bg-white sm:max-w-[140px]"
          >
            <option value="all">전체 기간</option>
            <option value="7">최근 7일</option>
            <option value="14">최근 14일</option>
            <option value="30">최근 30일</option>
          </select>
        </label>
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
          미게재만 보기
        </label>
      </div>

      <ul className="bg-white border border-slate-200 rounded-xl overflow-hidden mb-6">
        {filtered.length ? (
          filtered.map((it) => <ReleaseRow key={it.newsId} item={it} />)
        ) : (
          <li className="px-4 py-10 text-center text-slate-500">조건에 맞는 자료가 없습니다.</li>
        )}
      </ul>

      <div className="grid gap-4 sm:grid-cols-2">
        <section className="bg-white border border-slate-200 rounded-xl p-4">
          <h2 className="text-sm font-bold text-blue-700 border-b-2 border-blue-100 pb-1.5 mb-3">
            많이 실어준 매체
          </h2>
          <ul className="space-y-1.5">
            {publisherStats.slice(0, 12).map((p) => (
              <li key={p.name} className="flex items-center gap-2 text-sm">
                <span className="flex-1 min-w-0 truncate text-slate-700">{p.name}</span>
                <span className="h-1.5 rounded-full bg-blue-500 shrink-0"
                  style={{ width: `${Math.max(6, (p.count / (publisherStats[0]?.count || 1)) * 80)}px` }}
                  aria-hidden
                />
                <span className="w-8 text-right font-bold text-slate-900 tabular-nums">{p.count}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="bg-white border border-slate-200 rounded-xl p-4">
          <h2 className="text-sm font-bold text-blue-700 border-b-2 border-blue-100 pb-1.5 mb-3">
            부서별 보도 실적
          </h2>
          <ul className="space-y-1.5">
            {deptStats.map((d) => (
              <li key={d.name} className="flex items-center gap-2 text-sm">
                <span className="flex-1 min-w-0 truncate text-slate-700">{d.name}</span>
                <span className="text-xs text-slate-400 whitespace-nowrap">
                  {d.coveredCount}/{d.releaseCount}건
                </span>
                <span className="w-8 text-right font-bold text-slate-900 tabular-nums">
                  {d.articleCount}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-slate-400 break-keep">
            숫자는 게재된 기사 수입니다. 부서는 보도자료 첨부파일의 담당 부서를 따릅니다.
          </p>
        </section>
      </div>
    </div>
  );
}
