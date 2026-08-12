import { useEffect, useState } from "react";
import { ArrowUp } from "lucide-react";
import type { ActiveTab } from "./types";
import { Header } from "./components/Header";
import { ReportsTab } from "./components/ReportsTab";
import { ArchiveTab } from "./components/ArchiveTab";

function initialTab(): ActiveTab {
  const params = new URLSearchParams(window.location.search);
  const value = (params.get("tab") || window.location.hash.replace("#", "")).toLowerCase();
  return value === "archive" ? "archive" : "reports";
}

export default function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>(initialTab);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
    // 현재 탭을 URL에 반영해 새로고침·공유 시에도 같은 탭이 열리게 한다.
    const url = new URL(window.location.href);
    url.searchParams.set("tab", activeTab);
    window.history.replaceState(null, "", url);
  }, [activeTab]);

  return (
    <div className="min-h-screen bg-white text-slate-800 font-sans antialiased flex flex-col selection:bg-blue-600 selection:text-white">
      <a href="#container" className="krds-skip">
        본문 바로가기
      </a>

      <Header activeTab={activeTab} setActiveTab={setActiveTab} />

      <main id="container" className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {activeTab === "reports" ? <ReportsTab /> : <ArchiveTab />}
      </main>

      <footer className="border-t border-slate-200 bg-slate-50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6 text-xs text-slate-500 leading-relaxed">
          <p>이 문서는 공개 보도자료를 AI로 요약·분석한 내부 검토 자료입니다. 적용 검토안은 확정된 정책이나 업무 지시가 아닙니다.</p>
          <p className="mt-1">보도자료 제목과 원문 링크의 저작권은 각 기관에 있습니다.</p>
        </div>
      </footer>

      <button
        type="button"
        onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
        aria-label="맨 위로"
        className="fixed bottom-5 right-5 w-11 h-11 rounded-full bg-slate-900 text-white flex items-center justify-center shadow-lg hover:bg-slate-700 transition-colors"
      >
        <ArrowUp className="w-5 h-5" />
      </button>
    </div>
  );
}
