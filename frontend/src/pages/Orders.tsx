import { useState, useEffect, useCallback } from "react";
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from "chart.js";
import { Doughnut } from "react-chartjs-2";
import {
  fetchAgentExceptions,
  fetchAgentFeatures,
  fetchOrders,
  type AgentExceptionCase,
  type AgentFeatures,
  type Order,
} from "../lib/api";
import { getDemoOrders } from "../lib/demo";
import { ACCEPTED_ORDER_STATUSES, STATUS_COLORS, SOURCE_COLORS } from "../lib/constants";
import LoadingState from "../components/LoadingState";
import StatusBadge from "../components/StatusBadge";
import TempBadge from "../components/TempBadge";
import OrderDetailModal from "../components/OrderDetailModal";
import DashboardAgentPanel from "../components/DashboardAgentPanel";
import { SkeletonStatCards, SkeletonCharts } from "../components/Skeleton";

ChartJS.register(ArcElement, Tooltip, Legend);

const PAGE_SIZE = 50;

export default function Orders() {
  const [date, setDate] = useState(() => new Date().toISOString().split("T")[0]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [totalOrders, setTotalOrders] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Order | null>(null);
  const [agentFeatures, setAgentFeatures] = useState<AgentFeatures | null>(null);
  const [agentExceptions, setAgentExceptions] = useState<AgentExceptionCase[]>([]);
  const [agentLoading, setAgentLoading] = useState(false);

  const triageEnabled = Boolean(agentFeatures?.dashboard_agent && agentFeatures.exception_triage);
  const executeEnabled = Boolean(agentFeatures?.resolution_execute);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await fetchOrders(date, {
        status: statusFilter || undefined,
        source: sourceFilter || undefined,
        q: query || undefined,
        limit: PAGE_SIZE,
        offset,
      });
      setOrders(resp.orders);
      setTotalOrders(resp.total);
    } catch {
      const demoOrders = getDemoOrders().filter((order) => {
        const normalizedQuery = query.trim().toLowerCase();
        const matchesStatus = !statusFilter || order.status === statusFilter;
        const matchesSource = !sourceFilter || order.source === sourceFilter;
        const matchesQuery =
          !normalizedQuery ||
          order.customer_name.toLowerCase().includes(normalizedQuery) ||
          order.customer_id.toLowerCase().includes(normalizedQuery) ||
          order.items.some((item) => item.product_name.toLowerCase().includes(normalizedQuery));
        return matchesStatus && matchesSource && matchesQuery;
      });
      setOrders(demoOrders.slice(offset, offset + PAGE_SIZE));
      setTotalOrders(demoOrders.length);
    } finally {
      setLoading(false);
    }
  }, [date, statusFilter, sourceFilter, query, offset]);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  useEffect(() => {
    let active = true;
    fetchAgentFeatures()
      .then((features) => {
        if (active) setAgentFeatures(features);
      })
      .catch(() => {
        if (active) setAgentFeatures(null);
      });
    return () => {
      active = false;
    };
  }, []);

  const loadAgentExceptions = useCallback(async () => {
    if (!triageEnabled) {
      setAgentExceptions([]);
      return;
    }
    setAgentLoading(true);
    try {
      const resp = await fetchAgentExceptions(date);
      setAgentExceptions(resp.enabled ? resp.cases : []);
    } catch {
      setAgentExceptions([]);
    } finally {
      setAgentLoading(false);
    }
  }, [triageEnabled, date]);

  useEffect(() => {
    void Promise.resolve().then(loadAgentExceptions);
  }, [loadAgentExceptions]);

  const statusCounts: Record<string, number> = {};
  const sourceCounts: Record<string, number> = {};
  for (const s of Object.keys(STATUS_COLORS)) statusCounts[s] = 0;
  orders.forEach((o) => {
    statusCounts[o.status] = (statusCounts[o.status] || 0) + 1;
    sourceCounts[o.source] = (sourceCounts[o.source] || 0) + 1;
  });
  const acceptedOrderCount = orders.filter((o) => ACCEPTED_ORDER_STATUSES.has(o.status)).length;
  const reviewOrderCount = orders.length - acceptedOrderCount;
  const hasFilters = Boolean(statusFilter || sourceFilter || query.trim());
  const pageStart = totalOrders === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + orders.length, totalOrders);
  const canPrev = offset > 0;
  const canNext = offset + PAGE_SIZE < totalOrders;

  function resetFilters() {
    setStatusFilter("");
    setSourceFilter("");
    setQuery("");
    setOffset(0);
  }

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

  const statusLabels = Object.keys(statusCounts).filter((s) => statusCounts[s] > 0);
  const sourceLabels = Object.keys(sourceCounts);

  return (
    <>
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div>
          <h2 className="text-lg font-bold text-gray-900 tracking-tight">受注ダッシュボード</h2>
          <p className="text-xs text-gray-400 mt-0.5">
            {loading && orders.length === 0
              ? "データを読み込み中..."
              : `表示 ${pageStart}-${pageEnd}件 / 全${totalOrders}件`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-gray-500">配送日</label>
          <input
            type="date"
            value={date}
            onChange={(e) => {
              setDate(e.target.value);
              setOffset(0);
            }}
            className="input-field border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none bg-white"
          />
          <button
            onClick={() => {
              load();
              loadAgentExceptions();
            }}
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

      <div className={triageEnabled ? "grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px] gap-5 items-start" : ""}>
        <div className="min-w-0">
      {/* Stats cards */}
      {loading && orders.length === 0 ? (
        <SkeletonStatCards count={8} />
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3 mb-6 stagger-in">
          <div className="card-shine bg-white rounded-xl border border-gray-100 p-4">
            <p className="text-[11px] font-medium text-gray-400 uppercase tracking-wider mb-2">受注合計</p>
            <p className="text-2xl font-bold text-gray-900 tabular-nums">{acceptedOrderCount}</p>
          </div>
          {Object.entries(STATUS_COLORS).map(([status, color]) => (
            <button
              key={status}
              type="button"
              onClick={() => {
                setStatusFilter((current) => current === status ? "" : status);
                setOffset(0);
              }}
              className={`card-shine bg-white rounded-xl border p-4 text-left transition-all hover:-translate-y-0.5 ${
                statusFilter === status ? "ring-2 ring-brand-400 " : ""
              } ${color.border}`}
            >
              <p className="text-[11px] font-medium text-gray-400 uppercase tracking-wider mb-2">{status}</p>
              <p className={`text-2xl font-bold tabular-nums ${color.text}`}>{statusCounts[status] || 0}</p>
            </button>
          ))}
        </div>
      )}

      {/* Charts */}
      {loading && orders.length === 0 ? (
        <SkeletonCharts />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-6">
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
      )}

      {/* Order table */}
      <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">注文一覧</h3>
            <span className="text-xs text-gray-300 tabular-nums">
              表示 {pageStart}-{pageEnd}件 / 全{totalOrders}件
              <span className="ml-2">ページ内 受注 {acceptedOrderCount}件 / 要対応 {reviewOrderCount}件</span>
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-[minmax(220px,1fr)_160px_160px_auto] gap-3">
            <input
              type="search"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setOffset(0);
              }}
              placeholder="顧客名・商品名で検索"
              className="input-field border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none bg-white"
            />
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setOffset(0);
              }}
              className="input-field border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none bg-white"
            >
              <option value="">全ステータス</option>
              {Object.keys(STATUS_COLORS).map((status) => (
                <option key={status} value={status}>{status}</option>
              ))}
            </select>
            <select
              value={sourceFilter}
              onChange={(e) => {
                setSourceFilter(e.target.value);
                setOffset(0);
              }}
              className="input-field border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none bg-white"
            >
              <option value="">全チャネル</option>
              {Object.keys(SOURCE_COLORS).map((source) => (
                <option key={source} value={source}>{source}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={resetFilters}
              disabled={!hasFilters}
              className="btn-press px-4 py-2 text-sm text-gray-500 hover:text-gray-700 hover:bg-gray-50 rounded-lg border border-gray-200 transition-colors disabled:opacity-40"
            >
              解除
            </button>
          </div>
        </div>
        {loading && orders.length === 0 ? (
          <LoadingState
            compact
            title="受注を集計しています"
            message="今日の注文とステータスを読み込んでいます"
          />
        ) : orders.length === 0 ? (
          <div className="py-20 text-center">
            <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-gray-50 flex items-center justify-center">
              <svg className="w-6 h-6 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <p className="text-sm text-gray-400">
              {hasFilters ? "条件に一致する受注データはありません" : "この日の受注データはありません"}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50/80 text-left text-[11px] font-medium text-gray-400 uppercase tracking-wider">
                  <th className="px-5 py-3">受注日</th>
                  <th className="px-5 py-3">顧客名</th>
                  <th className="px-5 py-3">チャネル</th>
                  <th className="px-5 py-3">商品</th>
                  <th className="px-5 py-3">ステータス</th>
                  <th className="px-5 py-3">配送</th>
                  <th className="px-5 py-3">備考</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {orders.map((o) => {
                  const items = o.items || [];
                  const summary = items.map((i) => `${i.product_name} ${i.quantity ?? ""}${i.unit ?? ""}`).join(", ");
                  const zones = [...new Set(items.map((i) => i.temperature_zone))];
                  return (
                    <tr key={o.uid || o.id} className="row-hover cursor-pointer group" onClick={() => setSelected(o)}>
                      <td className="px-5 py-3.5 whitespace-nowrap text-gray-500 tabular-nums">{o.order_date || "-"}</td>
                      <td className="px-5 py-3.5 font-medium text-gray-900 group-hover:text-brand-700 transition-colors">{o.customer_name}</td>
                      <td className="px-5 py-3.5">
                        <span className={`text-xs font-semibold ${o.source === "LINE" ? "text-green-600" : "text-brand-600"}`}>{o.source}</span>
                      </td>
                      <td className="px-5 py-3.5 text-gray-600 max-w-xs truncate">
                        <span className="mr-1">{summary}</span>
                        {zones.map((z) => <TempBadge key={z} zone={z} />)}
                      </td>
                      <td className="px-5 py-3.5"><StatusBadge status={o.status} /></td>
                      <td className="px-5 py-3.5 text-gray-400 text-xs leading-relaxed">
                        {o.delivery_carrier || "-"}<br />{o.delivery_route || ""}
                        {o.delivery_time_slot && (
                          <span className="inline-flex items-center gap-0.5 mt-0.5 text-brand-600 font-medium">
                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                            {o.delivery_time_slot}
                          </span>
                        )}
                      </td>
                      <td className="px-5 py-3.5 text-gray-400 text-xs max-w-[120px] truncate">{o.remarks || "-"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {totalOrders > PAGE_SIZE && (
          <div className="px-5 py-3 border-t border-gray-100 flex items-center justify-between">
            <span className="text-xs text-gray-400 tabular-nums">
              {pageStart}-{pageEnd} / {totalOrders}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                disabled={!canPrev}
                className="btn-press px-3 py-1.5 text-xs text-gray-500 hover:text-gray-700 hover:bg-gray-50 rounded-lg border border-gray-200 disabled:opacity-40"
              >
                前へ
              </button>
              <button
                type="button"
                onClick={() => setOffset(offset + PAGE_SIZE)}
                disabled={!canNext}
                className="btn-press px-3 py-1.5 text-xs text-gray-500 hover:text-gray-700 hover:bg-gray-50 rounded-lg border border-gray-200 disabled:opacity-40"
              >
                次へ
              </button>
            </div>
          </div>
        )}
      </div>

        </div>
        {triageEnabled && (
          <div className="xl:sticky xl:top-5">
            <DashboardAgentPanel
              exceptions={agentExceptions}
              loading={agentLoading}
              date={date}
              executeEnabled={executeEnabled}
            />
          </div>
        )}
      </div>

      <OrderDetailModal order={selected} onClose={() => setSelected(null)} />
    </>
  );
}
