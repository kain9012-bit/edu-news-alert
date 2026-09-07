import { useEffect, useState } from "react";
import { Newspaper } from "lucide-react";
import type { ActiveTab } from "../types";

const TABS: { id: ActiveTab; label: string }[] = [
  { id: "reports", label: "오늘의 교육동향" },
  { id: "archive", label: "전국 보도자료" },
  { id: "coverage", label: "전북 언론 게재현황" },
];

// GoatCounter 공개 카운터로 이번 주·누적 방문자 수를 가져온다.
// 응답이 최대 4시간 캐시돼 '오늘'은 실시간성이 떨어지므로 주 단위로 표시한다.
const GC_TOTAL = "https://jbe-edu-trends.goatcounter.com/counter/TOTAL.json";

// 한국 시간 기준 이번 주(월~일) 범위. 오늘이 주 중이면 끝은 오늘로 둔다.
function kstWeekRange(): { start: string; end: string } {
  const ymd = (d: Date) => d.toISOString().slice(0, 10);
  const now = new Date(Date.now() + 9 * 3600 * 1000);
  // getUTCDay: 0=일 … 6=토 → 월요일까지 거슬러 갈 일수
  const backToMonday = (now.getUTCDay() + 6) % 7;
  const monday = new Date(now.getTime() - backToMonday * 86400000);
  return { start: ymd(monday), end: ymd(now) };
}

function VisitorCounts() {
  const [total, setTotal] = useState<string | null>(null);
  const [week, setWeek] = useState<string | null>(null);

  useEffect(() => {
    const { start, end } = kstWeekRange();
    const get = (url: string) =>
      fetch(url)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => (d && typeof d.count === "string" ? d.count : null))
        .catch(() => null);
    get(GC_TOTAL).then(setTotal);
    get(`${GC_TOTAL}?start=${start}&end=${end}`).then(setWeek);
  }, []);

  if (total === null && week === null) return null;
  return (
    <span className="shrink-0 text-xs text-slate-500 whitespace-nowrap">
      <span title="월요일부터 오늘까지">이번 주</span>{" "}
      <b className="text-slate-700">{week ?? "-"}</b>
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
