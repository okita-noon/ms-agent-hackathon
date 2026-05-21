import { useState, useEffect, useCallback } from "react";
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from "chart.js";
import { Doughnut } from "react-chartjs-2";
import { fetchOrders } from "../lib/api";
import { getDemoOrders } from "../lib/demo";
import { ACCEPTED_ORDER_STATUSES, STATUS_COLORS, SOURCE_COLORS } from "../lib/constants";
import { SkeletonStatCards, SkeletonCharts } from "../components/Skeleton";

ChartJS.register(ArcElement, Tooltip, Legend);

export default function Analytics() {
  const [date, setDate] = useState(() => new Date().toISOString().split("T")[0]);
  const [orders, setOrders] = useState<ReturnType<typeof getDemoOrders>>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await fetchOrders(date, { limit: 200 });
      setOrders(resp.orders as ReturnType<typeof getDemoOrders>);
    } catch {
      setOrders(getDemoOrders());
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  const statusCounts: Record<string, number> = {};
  const sourceCounts: Record<string, number> = {};
  for (const s of Object.keys(STATUS_COLORS)) statusCounts[s] = 0;
  orders.forEach((o) => {
    statusCounts[o.status] = (statusCounts[o.status] || 0) + 1;
    sourceCounts[o.source] = (sourceCounts[o.source] || 0) + 1;
  });
  const acceptedCount = orders.filter((o) => ACCEPTED_ORDER_STATUSES.has(o.status)).length;
  const reviewCount = orders.length - acceptedCount;

  const statusLabels = Object.keys(statusCounts).filter((s) => statusCounts[s] > 0);
  const sourceLabels = Object.keys(sourceCounts);

  const chartOpts = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: "65%",
    plugins: {
      legend: {
        position: "right" as const,
        labels: { boxWidth: 10, padding: 14, font: { size: 11, family: "Noto Sans JP" }, usePointStyle: true, pointStyle: "circle" },
      },
    },
  };

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div>
          <h2 className="text-lg font-bold text-gray-900 tracking-tight">分析</h2>
          <p className="text-xs text-gray-400 mt-0.5">配送日別の受注統計</p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-gray-500">配送日</label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="input-field border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none bg-white"
          />
          <button
            onClick={load}
            disabled={loading}
            className="btn-press bg-brand-600 hover:bg-brand-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 disabled:opacity-50 shadow-sm shadow-brand-600/20"
          >
            <svg className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            更新
          </button>
        </div>
      </div>

      {loading && orders.length === 0 ? (
        <>
          <SkeletonStatCards count={6} />
          <SkeletonCharts />
        </>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3 mb-6 stagger-in">
            <div className="card-shine bg-white rounded-xl border border-gray-100 p-4">
              <p className="text-[11px] font-medium text-gray-400 uppercase tracking-wider mb-2 whitespace-nowrap">受注合計</p>
              <p className="text-2xl font-bold text-gray-900 tabular-nums">{acceptedCount}</p>
            </div>
            <div className="card-shine bg-white rounded-xl border border-rose-100 p-4">
              <p className="text-[11px] font-medium text-rose-400 uppercase tracking-wider mb-2 whitespace-nowrap">要対応</p>
              <p className="text-2xl font-bold text-rose-700 tabular-nums">{reviewCount}</p>
            </div>
            {Object.entries(STATUS_COLORS).map(([status, color]) => (
              <div key={status} className={`card-shine bg-white rounded-xl border p-4 ${color.border}`}>
                <p className="text-[11px] font-medium text-gray-400 uppercase tracking-wider mb-2 whitespace-nowrap">{status}</p>
                <p className={`text-2xl font-bold tabular-nums ${color.text}`}>{statusCounts[status] || 0}</p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div className="bg-white rounded-xl border border-gray-100 p-5">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">ステータス別</h3>
              <div className="h-48 flex items-center justify-center">
                {statusLabels.length > 0 ? (
                  <Doughnut
                    data={{
                      labels: statusLabels,
                      datasets: [{
                        data: statusLabels.map((s) => statusCounts[s]),
                        backgroundColor: statusLabels.map((s) => STATUS_COLORS[s]?.chart ?? "#d1d5db"),
                        borderWidth: 0,
                        spacing: 2,
                      }],
                    }}
                    options={chartOpts}
                  />
                ) : (
                  <p className="text-sm text-gray-300">データなし</p>
                )}
              </div>
            </div>
            <div className="bg-white rounded-xl border border-gray-100 p-5">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">チャネル別</h3>
              <div className="h-48 flex items-center justify-center">
                {sourceLabels.length > 0 ? (
                  <Doughnut
                    data={{
                      labels: sourceLabels,
                      datasets: [{
                        data: sourceLabels.map((s) => sourceCounts[s]),
                        backgroundColor: sourceLabels.map((s) => SOURCE_COLORS[s] ?? "#d1d5db"),
                        borderWidth: 0,
                        spacing: 2,
                      }],
                    }}
                    options={chartOpts}
                  />
                ) : (
                  <p className="text-sm text-gray-300">データなし</p>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </>
  );
}
