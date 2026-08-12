import { Newspaper } from "lucide-react";
import type { ActiveTab } from "../types";

const TABS: { id: ActiveTab; label: string }[] = [
  { id: "reports", label: "오늘의 교육동향" },
  { id: "archive", label: "전체 보도자료" },
];

interface HeaderProps {
  activeTab: ActiveTab;
  setActiveTab: (tab: ActiveTab) => void;
}

export function Header({ activeTab, setActiveTab }: HeaderProps) {
  return (
    <header className="bg-white sticky top-0 z-30 border-b border-slate-200">
      <div className="bg-slate-50 text-slate-600 border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-2 text-xs">
          전북특별자치도교육청 · 공개 보도자료를 AI로 선별·분석한 내부 검토 자료
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
            <ul className="flex overflow-x-auto overflow-y-hidden no-scrollbar" role="tablist">
              {TABS.map(({ id, label }) => {
                const on = activeTab === id;
                return (
                  <li key={id} role="presentation" className="shrink-0">
                    <button
                      type="button"
                      role="tab"
                      aria-selected={on}
                      onClick={() => setActiveTab(id)}
                      className={`px-4 py-4 text-base font-bold whitespace-nowrap border-b-[3px] transition-colors ${
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
