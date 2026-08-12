import { useEffect, useState } from "react";
import { ArrowLeft, ChevronRight, ExternalLink, Star } from "lucide-react";
import type { Report, ReportIndexEntry } from "../types";
import { dateLabel, fetchReport, fetchReportIndex } from "../lib/data";

function Stars({ n = 1 }: { n?: number }) {
  const score = Math.max(1, Math.min(5, n || 1));
  return (
    <span className="inline-flex items-center gap-0.5 text-amber-600" aria-label={`중요도 ${score}점`}>
      {Array.from({ length: 5 }).map((_, i) => (
        <Star key={i} className="w-3.5 h-3.5" fill={i < score ? "currentColor" : "none"} strokeWidth={1.5} />
      ))}
    </span>
  );
}

function Points({ items }: { items?: string[] }) {
  if (!items || !items.length) return <p className="text-slate-400 text-sm">해당 사항 없음</p>;
  return (
    <ul className="space-y-1.5">
      {items.map((p, i) => (
        <li key={i} className="flex gap-2 text-slate-700 leading-relaxed">
          <span className="text-blue-500 shrink-0 mt-1.5 w-1 h-1 rounded-full bg-blue-500" aria-hidden />
          <span>{p}</span>
        </li>
      ))}
    </ul>
  );
}

function ReportView({ report, date, onBack }: { report: Report; date: string; onBack: () => void }) {
  const items = report.items || [];
  const own = report.ownOfficeItems || [];
  return (
    <div>
      <button
        type="button"
        onClick={onBack}
        className="inline-flex items-center gap-1.5 text-sm font-bold text-blue-700 hover:underline underline-offset-4 mb-4"
      >
        <ArrowLeft className="w-4 h-4" /> 지난 호 목록
      </button>

      <div className="border-t-4 border-blue-600 bg-white rounded-b-xl border border-slate-200 p-5 sm:p-7 mb-6">
        <p className="text-blue-700 font-bold text-sm mb-1">전국 교육정책 및 교육행정 동향</p>
        <h1 className="text-2xl sm:text-3xl font-bold text-slate-900">오늘의 교육동향</h1>
        <p className="mt-2 font-bold text-slate-800">{dateLabel(date)}</p>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-slate-500">
          <span>교육동향 <b className="text-slate-900">{items.length}</b>건</span>
          {own.length > 0 && <span>전북 보도자료 <b className="text-slate-900">{own.length}</b>건</span>}
        </div>
      </div>

      <div className="space-y-4">
        {items.map((it, idx) => (
          <article key={idx} className="bg-white rounded-xl border border-slate-200 p-5 sm:p-6">
            <p className="text-blue-700 text-xs font-bold mb-1">
              {it.source} · {it.category}
            </p>
            <h2 className="text-lg sm:text-xl font-bold text-slate-900 leading-snug">{it.title}</h2>
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-500">
              <Stars n={it.importance} />
              <span>{it.date}</span>
              {it.url && (
                <a
                  href={it.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-blue-700 font-bold hover:underline"
                >
                  원문 보도자료 <ExternalLink className="w-3.5 h-3.5" />
                </a>
              )}
            </div>

            <div className="mt-4 pt-4 border-t border-slate-100">
              <h3 className="text-base font-bold text-slate-900 mb-2">내용 요약</h3>
              <Points items={it.summaryPoints} />
            </div>

            {!it.summaryOnly && (
              <>
                <div className="mt-4 pt-4 border-t border-slate-100">
                  <h3 className="text-base font-bold text-slate-900 mb-2">교육동향 분석</h3>
                  <Points items={it.analysisPoints} />
                </div>
                <div className="mt-4 pt-4 border-t border-slate-100">
                  <h3 className="text-base font-bold text-amber-700 mb-2">전북교육 적용 검토</h3>
                  {it.applicationReviewPoints && it.applicationReviewPoints.length ? (
                    <Points items={it.applicationReviewPoints} />
                  ) : (
                    <p className="text-slate-400 text-sm">직접 적용 검토사항 없음</p>
                  )}
                </div>
              </>
            )}
          </article>
        ))}
      </div>

      {own.length > 0 && (
        <div className="mt-8">
          <div className="border-l-4 border-blue-600 pl-3 mb-3">
            <p className="text-blue-700 text-xs font-bold">우리 교육청 주요 발표</p>
            <h2 className="text-xl font-bold text-slate-900">전북교육청 보도자료</h2>
          </div>
          <div className="space-y-3">
            {own.map((it, idx) => (
              <article key={idx} className="bg-white rounded-xl border border-slate-200 p-5">
                <h3 className="font-bold text-slate-900">{it.title}</h3>
                <div className="mt-2"><Points items={it.summaryPoints} /></div>
                {it.url && (
                  <a
                    href={it.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-flex items-center gap-1 text-sm text-blue-700 font-bold hover:underline"
                  >
                    원문 보도자료 <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                )}
              </article>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function ReportsTab() {
  const [index, setIndex] = useState<ReportIndexEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [reportLoading, setReportLoading] = useState(false);

  useEffect(() => {
    fetchReportIndex().then((d) => {
      setIndex((d?.reports || []).slice().sort((a, b) => (a.date < b.date ? 1 : -1)));
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    if (!selected) {
      setReport(null);
      return;
    }
    setReportLoading(true);
    fetchReport(selected).then((r) => {
      setReport(r);
      setReportLoading(false);
      window.scrollTo({ top: 0, behavior: "auto" });
    });
  }, [selected]);

  if (selected) {
    if (reportLoading) return <p className="text-slate-500 py-16 text-center">불러오는 중…</p>;
    if (!report)
      return (
        <div className="py-16 text-center text-slate-500">
          보고서를 불러오지 못했습니다.
          <button className="block mx-auto mt-3 text-blue-700 font-bold" onClick={() => setSelected(null)}>
            목록으로
          </button>
        </div>
      );
    return <ReportView report={report} date={selected} onBack={() => setSelected(null)} />;
  }

  if (loading) return <p className="text-slate-500 py-16 text-center">지난 호 목록을 불러오는 중…</p>;
  if (!index.length)
    return <p className="text-slate-500 py-16 text-center">아직 발행된 지난 호가 없습니다.</p>;

  return (
    <div>
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-slate-900">오늘의 교육동향 · 지난 호</h1>
        <p className="text-slate-500 text-sm mt-1">날짜를 선택하면 그날의 보고서를 볼 수 있습니다.</p>
      </div>
      <ul className="bg-white rounded-xl border border-slate-200 overflow-hidden divide-y divide-slate-100">
        {index.map((r) => (
          <li key={r.date}>
            <button
              type="button"
              onClick={() => setSelected(r.date)}
              className="w-full flex items-center gap-4 px-4 sm:px-5 py-4 text-left hover:bg-slate-50 transition-colors"
            >
              <span className="text-blue-700 font-bold text-base sm:text-lg w-[130px] shrink-0">
                {r.date}
                <span className="text-slate-400 text-sm font-semibold"> ({dateLabel(r.date).slice(-2, -1)})</span>
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
