interface Props {
  total: number;
  page: number;
  pageSize: number;
  onPageChange: (p: number) => void;
  onPageSizeChange: (s: number) => void;
}

export default function Pagination({ total, page, pageSize, onPageChange, onPageSizeChange }: Props) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  return (
    <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-3 border-t border-gray-100 text-sm text-gray-500">
      {/* Left */}
      <span className="tabular-nums whitespace-nowrap">
        {start}–{end} 件を表示（全 {total} 件）
      </span>

      {/* Center */}
      <div className="flex items-center gap-1">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="flex items-center justify-center w-8 h-8 rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>

        {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => onPageChange(p)}
            className={`flex items-center justify-center w-8 h-8 rounded-lg text-sm font-medium transition-colors ${
              p === page
                ? "border border-brand-500 bg-brand-50 text-brand-700"
                : "border border-gray-200 hover:bg-gray-50 text-gray-600"
            }`}
          >
            {p}
          </button>
        ))}

        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          className="flex items-center justify-center w-8 h-8 rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>

      {/* Right */}
      <div className="flex items-center gap-2 whitespace-nowrap">
        <span>表示件数</span>
        <select
          value={pageSize}
          onChange={(e) => onPageSizeChange(Number(e.target.value))}
          className="appearance-none rounded-lg border border-gray-200 bg-white px-2 py-1 text-sm outline-none cursor-pointer"
        >
          <option value={10}>10件</option>
          <option value={20}>20件</option>
          <option value={50}>50件</option>
        </select>
      </div>
    </div>
  );
}
