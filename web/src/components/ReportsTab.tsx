import { useEffect, useState } from "react";
import { ArrowLeft, ChevronRight } from "lucide-react";
import type { ReportIndexEntry } from "../types";
import { DATA_BASE, dateLabel, fetchReportIndex, weekday } from "../lib/data";

export function ReportsTab() {
  const [index, setIndex] = useState<ReportIndexEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    fetchReportIndex().then((d) => {
      setIndex((d?.reports || []).slice().sort((a, b) => (a.date < b.date ? 1 : -1)));
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    if (selected) window.scrollTo({ top: 0, behavior: "auto" });
  }, [selected]);

  // 선택 시 실제 배포되는 보고서 HTML(reports/<날짜>.html)을 그대로 전체 화면으로 띄운다.
  if (selected) {
    const url = `${DATA_BASE}reports/${selected}.html`;
    return (
      <div className="-mx-4 sm:-mx-6 lg:-mx-8 -my-6">
        <div className="sticky top-[57px] z-20 bg-white/95 backdrop-blur border-b border-slate-200 px-4 sm:px-6 lg:px-8 py-2.5 flex items-center gap-3">
          <button
            type="button"
            onClick={() => setSelected(null)}
            className="inline-flex items-center gap-1.5 text-sm font-bold text-blue-700 hover:underline underline-offset-4"
          >
            <ArrowLeft className="w-4 h-4" /> 지난 호 목록
          </button>
          <span className="text-sm text-slate-500">{dateLabel(selected)}</span>
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto text-sm font-bold text-slate-500 hover:text-blue-700"
          >
            새 탭에서 열기
          </a>
        </div>
        <iframe
          key={selected}
          src={url}
          title={`오늘의 교육동향 ${selected}`}
          className="w-full border-0 bg-white"
          style={{ height: "calc(100vh - 57px - 45px)" }}
        />
      </div>
    );
  }

  if (loading) return <p className="text-slate-500 py-16 text-center">지난 호 목록을 불러오는 중…</p>;
  if (!index.length)
    return <p className="text-slate-500 py-16 text-center">아직 발행된 지난 호가 없습니다.</p>;

  return (
    <div>
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-slate-900">오늘의 교육동향 · 지난 호</h1>
        <p className="text-slate-500 text-sm mt-1">날짜를 선택하면 그날 발행된 보고서를 그대로 볼 수 있습니다.</p>
      </div>
      <ul className="bg-white rounded-xl border border-slate-200 overflow-hidden divide-y divide-slate-100">
        {index.map((r) => (
          <li key={r.date}>
            <button
              type="button"
              onClick={() => setSelected(r.date)}
              className="w-full flex items-center gap-4 px-4 sm:px-5 py-4 text-left hover:bg-slate-50 transition-colors"
            >
              <span className="text-blue-700 font-bold text-base sm:text-lg shrink-0 whitespace-nowrap">
                {r.date}
                <span className="text-slate-400 text-sm font-semibold"> ({weekday(r.date)})</span>
              </span>
              <span className="flex-1 text-sm text-slate-600">
                교육동향 <b className="text-slate-900">{r.trendCount}</b>건
                {r.ownOfficeCount ? (
                  <>
                    {" · "}전북 <b className="text-slate-900">{r.ownOfficeCount}</b>건
                  </>
                ) : null}
              </span>
              <ChevronRight className="w-5 h-5 text-slate-400 shrink-0" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
