import { useEffect, useState } from "react";
import { ChevronRight, ExternalLink } from "lucide-react";
import type { ReportIndexEntry } from "../types";
import { DATA_BASE, fetchReportIndex, weekday } from "../lib/data";

export function ReportsTab() {
  const [index, setIndex] = useState<ReportIndexEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchReportIndex().then((d) => {
      setIndex((d?.reports || []).slice().sort((a, b) => (a.date < b.date ? 1 : -1)));
      setLoading(false);
    });
  }, []);

  if (loading) return <p className="text-slate-500 py-16 text-center">지난 호 목록을 불러오는 중…</p>;
  if (!index.length)
    return <p className="text-slate-500 py-16 text-center">아직 발행된 지난 호가 없습니다.</p>;

  return (
    <div>
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-slate-900">오늘의 교육동향 · 지난 호</h1>
        <p className="text-slate-500 text-sm mt-1">날짜를 선택하면 그날 발행된 보고서가 새 탭으로 열립니다.</p>
      </div>
      <ul className="bg-white rounded-xl border border-slate-200 overflow-hidden divide-y divide-slate-100">
        {index.map((r) => (
          <li key={r.date}>
            <a
              href={`${DATA_BASE}reports/${r.date}.html`}
              target="_blank"
              rel="noopener noreferrer"
              className="w-full flex items-center gap-4 px-4 sm:px-5 py-4 text-left hover:bg-slate-50 transition-colors"
            >
              <span className="text-blue-700 font-bold text-base sm:text-lg shrink-0 whitespace-nowrap">
                {r.date}
                <span className="text-slate-400 text-sm font-semibold"> ({weekday(r.date)})</span>
              </span>
              <span className="flex-1 text-sm text-slate-600 break-keep">
                <span className="whitespace-nowrap">교육동향 <b className="text-slate-900">{r.trendCount}</b>건</span>
                {r.ownOfficeCount ? (
                  <span className="whitespace-nowrap">
                    {" · "}전북 <b className="text-slate-900">{r.ownOfficeCount}</b>건
                  </span>
                ) : null}
              </span>
              <ExternalLink className="w-4 h-4 text-slate-300 shrink-0 hidden sm:block" />
              <ChevronRight className="w-5 h-5 text-slate-400 shrink-0 sm:hidden" />
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
