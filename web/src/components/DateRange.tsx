interface DateRangeProps {
  from: string;
  to: string;
  min?: string;
  max?: string;
  onChange: (next: { from: string; to: string }) => void;
}

/** 시작일~종료일을 직접 고르는 기간 필터. 두 탭이 같은 방식으로 쓰도록 공통으로 둔다. */
export function DateRange({ from, to, min, max, onChange }: DateRangeProps) {
  const active = Boolean(from || to);
  return (
    <div className="flex flex-col gap-1 w-full sm:w-auto">
      <span className="flex items-center gap-2 text-xs font-bold text-slate-500">
        기간
        {active && (
          <button
            type="button"
            onClick={() => onChange({ from: "", to: "" })}
            className="font-bold text-blue-700 hover:underline"
          >
            전체로 되돌리기
          </button>
        )}
      </span>
      <span className="flex items-center gap-1.5">
        <input
          type="date"
          value={from}
          min={min}
          max={to || max}
          onChange={(e) => onChange({ from: e.target.value, to })}
          aria-label="시작일"
          className="flex-1 min-w-0 sm:flex-none sm:w-[150px] h-10 border border-slate-200 rounded-lg px-2 sm:px-3 text-sm bg-white"
        />
        <span className="shrink-0 text-slate-400">~</span>
        <input
          type="date"
          value={to}
          min={from || min}
          max={max}
          onChange={(e) => onChange({ from, to: e.target.value })}
          aria-label="종료일"
          className="flex-1 min-w-0 sm:flex-none sm:w-[150px] h-10 border border-slate-200 rounded-lg px-2 sm:px-3 text-sm bg-white"
        />
      </span>
    </div>
  );
}
