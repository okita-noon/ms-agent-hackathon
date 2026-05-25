import { STATUS_COLORS } from "../lib/constants";

interface Props {
  searchQuery: string;
  onSearchChange: (v: string) => void;
  filterStatus: string;
  onStatusChange: (v: string) => void;
  sortKey: string;
  onSortChange: (v: string) => void;
  onReset: () => void;
}

const statusOptions = ["すべて", ...Object.keys(STATUS_COLORS)];
const sortOptions = [
  { value: "order_date_desc", label: "受注日時：新しい順" },
  { value: "order_date_asc", label: "受注日時：古い順" },
  { value: "customer_name", label: "顧客名" },
  { value: "status", label: "ステータス" },
];

const selectCls =
  "w-full appearance-none rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 outline-none focus:border-brand-400 focus:ring-1 focus:ring-brand-200 cursor-pointer";

export default function OrderFilterBar(props: Props) {
  return (
    <div className="flex flex-wrap items-end gap-3 px-5 py-4 border-b border-gray-100">
      {/* Search */}
      <div className="relative min-w-[220px] flex-1">
        <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          type="text"
          value={props.searchQuery}
          onChange={(e) => props.onSearchChange(e.target.value)}
          placeholder="注文ID・商品・顧客名で検索"
          className="w-full rounded-lg border border-gray-200 bg-white pl-9 pr-3 py-2 text-sm text-gray-700 outline-none placeholder:text-gray-400 focus:border-brand-400 focus:ring-1 focus:ring-brand-200"
        />
      </div>

      {/* Status */}
      <div className="min-w-[120px]">
        <label className="block text-[11px] font-medium text-gray-400 mb-1">ステータス</label>
        <select value={props.filterStatus} onChange={(e) => props.onStatusChange(e.target.value)} className={selectCls}>
          {statusOptions.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {/* Sort */}
      <div className="min-w-[180px]">
        <label className="block text-[11px] font-medium text-gray-400 mb-1">並び順</label>
        <select value={props.sortKey} onChange={(e) => props.onSortChange(e.target.value)} className={selectCls}>
          {sortOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>

      {/* Reset */}
      <button
        type="button"
        onClick={props.onReset}
        className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
        </svg>
        絞り込み
      </button>
    </div>
  );
}
