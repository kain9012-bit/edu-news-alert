import { useEffect, useState } from "react";
import { Newspaper } from "lucide-react";
import type { ActiveTab } from "../types";

const TABS: { id: ActiveTab; label: string }[] = [
  { id: "reports", label: "오늘의 교육동향" },
  { id: "archive", label: "전체 보도자료" },
  { id: "coverage", label: "언론 보도" },
];

// GoatCounter 공개 카운터로 오늘·누적 방문자 수를 가져온다(응답은 최대 4시간 캐시).
const GC_TOTAL = "https://jbe-edu-trends.goatcounter.com/counter/TOTAL.json";

function VisitorCounts() {
  const [total, setTotal] = useState<string | null>(null);
  const [today, setToday] = useState<string | null>(null);

  useEffect(() => {
    // 한국 시간(KST) 기준 오늘 날짜
    const kstToday = new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10);
    const get = (url: string) =>
      fetch(url)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => (d && typeof d.count === "string" ? d.count : null))
        .catch(() => null);
    get(GC_TOTAL).then(setTotal);
    get(`${GC_TOTAL}?start=${kstToday}&end=${kstToday}`).then(setToday);
  }, []);

  if (total === null && today === null) return null;
  return (
    <span className="shrink-0 text-xs text-slate-500 whitespace-nowrap">
      오늘 <b className="text-slate-700">{today ?? "-"}</b>
      <span className="mx-1.5 text-slate-300">·</span>
      누적 <b className="text-slate-700">{total ?? "-"}</b>
    </span>
  );
}

interface HeaderProps {
  activeTab: ActiveTab;
  setActiveTab: (tab: ActiveTab) => void;
}

export function Header({ activeTab, setActiveTab }: HeaderProps) {
  return (
    <header className="bg-white sticky top-0 z-30 border-b border-slate-200">
      <div className="bg-slate-50 text-slate-600 border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-2 text-xs flex items-center justify-between gap-3">
          <span className="min-w-0 truncate">
            전북특별자치도교육청 · 공개 보도자료를 AI로 선별·분석한 내부 검토 자료
          </span>
          <VisitorCounts />
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-center justify-between gap-x-6">
          <button
            type="button"
            onClick={() => setActiveTab("reports")}
            className="flex items-center gap-2.5 py-3.5 text-left group shrink-0"
          >
            <span className="w-9 h-9 rounded-lg bg-blue-600 flex items-center justify-center text-white shrink-0 group-hover:bg-blue-700 transition-colors">
              <Newspaper className="w-5 h-5" aria-hidden="true" />
            </span>
            <span className="flex items-baseline gap-2">
              <span className="text-lg font-bold text-slate-900 whitespace-nowrap">
                오늘의 교육동향
              </span>
              <span className="hidden sm:inline text-xs font-medium text-slate-400 whitespace-nowrap">
                Education Trends
              </span>
            </span>
          </button>

          <nav aria-label="주 메뉴" className="-mb-px w-full sm:w-auto">
            <ul className="flex" role="tablist">
              {TABS.map(({ id, label }) => {
                const on = activeTab === id;
                return (
                  <li key={id} role="presentation" className="flex-1 sm:flex-none">
                    <button
                      type="button"
                      role="tab"
                      aria-selected={on}
                      onClick={() => setActiveTab(id)}
                      className={`w-full text-center px-2 sm:px-4 py-4 text-sm sm:text-base font-bold whitespace-nowrap border-b-[3px] transition-colors ${
                        on
                          ? "text-blue-700 border-blue-600"
                          : "text-slate-600 border-transparent hover:text-slate-900"
                      }`}
                    >
                      {label}
                    </button>
                  </li>
                );
              })}
            </ul>
          </nav>
        </div>
      </div>
    </header>
  );
}
