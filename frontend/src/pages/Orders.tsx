import { useState, useEffect, useCallback, useMemo } from "react";
import {
  createOrderEventSource,
  fetchAgentExceptions,
  fetchAgentFeatures,
  fetchOrders,
  type AgentExceptionCase,
  type AgentFeatures,
  type Order,
  type OrderEventPayload,
} from "../lib/api";
import { getDemoOrders } from "../lib/demo";
import { ACCEPTED_ORDER_STATUSES, normalizeStatus } from "../lib/constants";
import LoadingState from "../components/LoadingState";
import StatusBadge from "../components/StatusBadge";
import TempBadge from "../components/TempBadge";
import ChannelBadge from "../components/ChannelBadge";
import OrderFilterBar from "../components/OrderFilterBar";
import Pagination from "../components/Pagination";
import OrderDetailModal from "../components/OrderDetailModal";
import DashboardAgentPanel from "../components/DashboardAgentPanel";
import { offsetDate, todayJst } from "../lib/date";

const PAGE_SIZE = 50;

type DateField = "delivery_date" | "order_date";

function formatDate(value?: string): string {
  if (!value) return "-";
  return value.slice(0, 10);
}

function formatTime(value?: string): string {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Tokyo" });
}

export default function Orders() {
  const [dateFilterEnabled, setDateFilterEnabled] = useState(false);
  const [date, setDate] = useState(() => todayJst());
  const [dateField, setDateField] = useState<DateField>("delivery_date");
  const [orders, setOrders] = useState<Order[]>([]);
  const [totalOrders, setTotalOrders] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [sortKey, setSortKey] = useState("order_date_desc");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Order | null>(null);
  const [agentFeatures, setAgentFeatures] = useState<AgentFeatures | null>(null);
  const [agentExceptions, setAgentExceptions] = useState<AgentExceptionCase[]>([]);
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentPanelVisible, setAgentPanelVisible] = useState(true);
  const [, setLiveStatus] = useState<"connecting" | "live" | "reconnecting" | "offline">("connecting");
  const [recentOrderIds, setRecentOrderIds] = useState<Set<string>>(() => new Set());

  const triageAvailable = Boolean(agentFeatures?.dashboard_agent && agentFeatures.exception_triage);
  const agentPanelOpen = triageAvailable && agentPanelVisible;
  const executeEnabled = Boolean(agentFeatures?.resolution_execute);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await fetchOrders(dateFilterEnabled ? date : null, {
        status: statusFilter || undefined,
        q: query || undefined,
        limit: PAGE_SIZE,
        offset,
        date_field: dateFilterEnabled ? dateField : undefined,
      });
      setOrders(resp.orders);
      setTotalOrders(resp.total);
    } catch {
      const demoOrders = getDemoOrders().filter((order) => {
        const normalizedQuery = query.trim().toLowerCase();
        const matchesStatus = !statusFilter || order.status === statusFilter;
        const matchesQuery =
          !normalizedQuery ||
          order.customer_name.toLowerCase().includes(normalizedQuery) ||
          order.customer_id.toLowerCase().includes(normalizedQuery) ||
          order.items.some((item) => item.product_name.toLowerCase().includes(normalizedQuery));
        return matchesStatus && matchesQuery;
      });
      setOrders(demoOrders.slice(offset, offset + PAGE_SIZE));
      setTotalOrders(demoOrders.length);
    } finally {
      setLoading(false);
    }
  }, [dateFilterEnabled, date, dateField, statusFilter, query, offset]);

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
    if (!agentPanelOpen) {
      setAgentExceptions([]);
      return;
    }
    setAgentLoading(true);
    try {
      const resp = await fetchAgentExceptions(dateFilterEnabled ? date : null, {
        status: statusFilter || undefined,
        q: query || undefined,
        limit: PAGE_SIZE,
        offset,
        date_field: dateFilterEnabled ? dateField : undefined,
      });
      setAgentExceptions(resp.enabled ? resp.cases : []);
    } catch {
      setAgentExceptions([]);
    } finally {
      setAgentLoading(false);
    }
  }, [agentPanelOpen, dateFilterEnabled, date, dateField, statusFilter, query, offset]);

  useEffect(() => {
    void Promise.resolve().then(loadAgentExceptions);
  }, [loadAgentExceptions]);

  useEffect(() => {
    const events = createOrderEventSource();
    setLiveStatus("connecting");

    function handleConnected() {
      setLiveStatus("live");
    }

    function handleOrderEvent(event: MessageEvent<string>) {
      setLiveStatus("live");
      const payload = JSON.parse(event.data || "{}") as OrderEventPayload;
      if (dateFilterEnabled) {
        const eventDate = dateField === "order_date" ? payload.order_date : payload.delivery_date;
        if (eventDate && eventDate !== date) return;
      }

      if (payload.order_id) {
        setRecentOrderIds((current) => new Set(current).add(payload.order_id || ""));
        window.setTimeout(() => {
          setRecentOrderIds((current) => {
            const next = new Set(current);
            next.delete(payload.order_id || "");
            return next;
          });
        }, 6000);
      }
      void load();
      void loadAgentExceptions();
    }

    events.addEventListener("connected", handleConnected);
    events.addEventListener("order_created", handleOrderEvent);
    events.addEventListener("order_updated", handleOrderEvent);
    events.onerror = () => setLiveStatus("reconnecting");

    return () => {
      events.removeEventListener("connected", handleConnected);
      events.removeEventListener("order_created", handleOrderEvent);
      events.removeEventListener("order_updated", handleOrderEvent);
      events.close();
      setLiveStatus("offline");
    };
  }, [dateFilterEnabled, date, dateField, load, loadAgentExceptions]);

  const displayOrders = useMemo(() => {
    const result = [...orders];
    result.sort((a, b) => {
      switch (sortKey) {
        case "order_date_desc": return (b.order_date || "").localeCompare(a.order_date || "");
        case "order_date_asc": return (a.order_date || "").localeCompare(b.order_date || "");
        case "customer_name": return a.customer_name.localeCompare(b.customer_name);
        case "status": return a.status.localeCompare(b.status);
        default: return 0;
      }
    });
    return result;
  }, [orders, sortKey]);

  const acceptedOrderCount = orders.filter((o) =>
    ACCEPTED_ORDER_STATUSES.has(normalizeStatus(o.status))
  ).length;
  const reviewOrderCount = orders.length - acceptedOrderCount;
  const hasFilters = Boolean(dateFilterEnabled || statusFilter || query.trim());
  const pageStart = totalOrders === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + orders.length, totalOrders);
  const page = Math.floor(offset / PAGE_SIZE) + 1;

  function resetFilters() {
    setDateFilterEnabled(false);
    setStatusFilter("");
    setQuery("");
    setSortKey("order_date_desc");
    setOffset(0);
  }

  function changeDate(newDate: string) {
    setDate(newDate);
    setOffset(0);
  }

  function changeDateField(field: DateField) {
    setDateField(field);
    setOffset(0);
  }

  const filterStatusUI = statusFilter || "すべて";
  const todayStr = todayJst();
  const agentScopeLabel = dateFilterEnabled
    ? `${date} の${dateField === "order_date" ? "受注分" : "配送分"}`
    : "現在表示中の受注";

  return (
    <>
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-bold text-gray-900 tracking-tight">受注一覧</h2>
          <span className="inline-flex items-center gap-1 rounded-md border border-brand-200 bg-brand-50 px-2 py-1 text-xs font-bold text-brand-700">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
            受注 <span className="tabular-nums">{acceptedOrderCount}</span>
          </span>
          <span className="inline-flex items-center gap-1 rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-xs font-bold text-rose-700">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
            要対応 <span className="tabular-nums">{reviewOrderCount}</span>
          </span>
          <span className="text-xs text-gray-400">
            {loading && orders.length === 0
              ? "読み込み中..."
              : `${pageStart}-${pageEnd} / ${totalOrders}件`}
          </span>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {triageAvailable && (
            <button
              type="button"
              role="switch"
              aria-checked={agentPanelVisible}
              onClick={() => setAgentPanelVisible((visible) => !visible)}
              className={`btn-press inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold transition-colors ${
                agentPanelVisible
                  ? "border-brand-200 bg-brand-50 text-brand-700"
                  : "border-gray-200 bg-white text-gray-500 hover:bg-gray-50"
              }`}
            >
              <span
                className={`flex h-4 w-7 items-center rounded-full p-0.5 transition-colors ${
                  agentPanelVisible ? "bg-brand-600" : "bg-gray-300"
                }`}
              >
                <span
                  className={`h-3 w-3 rounded-full bg-white shadow-sm transition-transform ${
                    agentPanelVisible ? "translate-x-3" : "translate-x-0"
                  }`}
                />
              </span>
              foogent AI
            </button>
          )}

          {/* Date filter toggle */}
          <button
            type="button"
            role="switch"
            aria-checked={dateFilterEnabled}
            onClick={() => { setDateFilterEnabled((prev) => !prev); setOffset(0); }}
            className={`btn-press inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold transition-colors ${
              dateFilterEnabled
                ? "border-brand-200 bg-brand-50 text-brand-700"
                : "border-gray-200 bg-white text-gray-500 hover:bg-gray-50"
            }`}
          >
            <span
              className={`flex h-4 w-7 items-center rounded-full p-0.5 transition-colors ${
                dateFilterEnabled ? "bg-brand-600" : "bg-gray-300"
              }`}
            >
              <span
                className={`h-3 w-3 rounded-full bg-white shadow-sm transition-transform ${
                  dateFilterEnabled ? "translate-x-3" : "translate-x-0"
                }`}
              />
            </span>
            日付で絞り込み
          </button>

          {dateFilterEnabled && (
            <>
              {/* Date field toggle */}
              <div className="inline-flex rounded-lg border border-gray-200 bg-white overflow-hidden text-xs font-medium">
                <button
                  type="button"
                  onClick={() => changeDateField("delivery_date")}
                  className={`px-3 py-2 transition-colors ${
                    dateField === "delivery_date"
                      ? "bg-brand-600 text-white"
                      : "text-gray-500 hover:bg-gray-50"
                  }`}
                >
                  配送日
                </button>
                <button
                  type="button"
                  onClick={() => changeDateField("order_date")}
                  className={`px-3 py-2 border-l border-gray-200 transition-colors ${
                    dateField === "order_date"
                      ? "bg-brand-600 text-white"
                      : "text-gray-500 hover:bg-gray-50"
                  }`}
                >
                  受注日
                </button>
              </div>

              {/* Quick date buttons */}
              <div className="inline-flex rounded-lg border border-gray-200 bg-white overflow-hidden text-xs font-medium">
                <button
                  type="button"
                  onClick={() => changeDate(offsetDate(date, -1))}
                  className="px-3 py-2 text-gray-500 hover:bg-gray-50 transition-colors"
                >
                  前日
                </button>
                <button
                  type="button"
                  onClick={() => changeDate(todayStr)}
                  className={`px-3 py-2 border-l border-gray-200 transition-colors ${
                    date === todayStr
                      ? "bg-brand-50 text-brand-700 font-semibold"
                      : "text-gray-500 hover:bg-gray-50"
                  }`}
                >
                  本日
                </button>
                <button
                  type="button"
                  onClick={() => changeDate(offsetDate(date, 1))}
                  className="px-3 py-2 border-l border-gray-200 text-gray-500 hover:bg-gray-50 transition-colors"
                >
                  翌日
                </button>
              </div>

              {/* Date picker */}
              <input
                type="date"
                value={date}
                onChange={(e) => changeDate(e.target.value)}
                className="input-field border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none bg-white"
              />
            </>
          )}

          <button
            onClick={() => {
              load();
              if (agentPanelOpen) loadAgentExceptions();
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

      <div className={agentPanelOpen ? "grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px] gap-5 items-start" : ""}>
        <div className="min-w-0">
      {/* Order table */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        {/* Filter bar */}
        <OrderFilterBar
          searchQuery={query}
          onSearchChange={(v) => { setQuery(v); setOffset(0); }}
          filterStatus={filterStatusUI}
          onStatusChange={(v) => { setStatusFilter(v === "すべて" ? "" : v); setOffset(0); }}
          onReset={resetFilters}
        />

        {loading && orders.length === 0 ? (
          <LoadingState
            compact
            title="受注を集計しています"
            message="今日の注文とステータスを読み込んでいます"
          />
        ) : displayOrders.length === 0 ? (
          <div className="py-20 text-center">
            <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-gray-50 flex items-center justify-center">
              <svg className="w-6 h-6 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <p className="text-sm text-gray-400">
              {hasFilters ? "条件に一致する受注データはありません" : "受注データはありません"}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50/80 text-left text-[11px] font-medium text-gray-400 uppercase tracking-wider">
                  <th className="px-5 py-3">
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 hover:text-gray-600 transition-colors"
                      onClick={() => setSortKey(sortKey === "order_date_desc" ? "order_date_asc" : "order_date_desc")}
                    >
                      受注日時
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        {sortKey === "order_date_asc"
                          ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                          : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />}
                      </svg>
                    </button>
                  </th>
                  <th className="px-5 py-3">
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 hover:text-gray-600 transition-colors"
                      onClick={() => setSortKey(sortKey === "customer_name" ? "order_date_desc" : "customer_name")}
                    >
                      顧客名
                      {sortKey === "customer_name" && (
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                        </svg>
                      )}
                    </button>
                  </th>
                  <th className="px-5 py-3">商品（温度帯）</th>
                  <th className="px-5 py-3">
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 hover:text-gray-600 transition-colors"
                      onClick={() => setSortKey(sortKey === "status" ? "order_date_desc" : "status")}
                    >
                      ステータス
                      {sortKey === "status" && (
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                        </svg>
                      )}
                    </button>
                  </th>
                  <th className="px-5 py-3">配送日</th>
                  <th className="px-5 py-3">備考</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {displayOrders.map((o) => {
                  const items = o.items || [];
                  return (
                    <tr
                      key={o.uid || o.id}
                      className={`row-hover cursor-pointer group ${
                        recentOrderIds.has(o.uid || o.id || "") ? "bg-green-50 animate-new-order" : ""
                      }`}
                      onClick={() => setSelected(o)}
                    >
                      <td className="px-5 py-3.5 whitespace-nowrap tabular-nums">
                        <div className="text-gray-700 font-medium">{formatDate(o.order_date)}</div>
                        <div className="mt-0.5 text-xs text-gray-500 font-medium">{formatTime(o.created_at || o.updated_at)}</div>
                        <div className="mt-1.5"><ChannelBadge source={o.source} /></div>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className="font-medium text-gray-900 group-hover:text-brand-700 transition-colors">{o.customer_name}</span>
                      </td>
                      <td className="px-5 py-3.5 max-w-xs">
                        <div className="flex flex-col gap-1">
                          {items.map((item, idx) => (
                            <div key={idx} className="flex items-center gap-1.5">
                              <span className="font-semibold text-gray-900">{item.product_name}</span>
                              <span className="text-gray-500 text-sm">{item.quantity}{item.unit}</span>
                              <TempBadge zone={item.temperature_zone} />
                            </div>
                          ))}
                        </div>
                      </td>
                      <td className="px-5 py-3.5"><StatusBadge status={o.status} /></td>
                      <td className="px-5 py-3.5 whitespace-nowrap tabular-nums">
                        <div className="text-gray-700 font-medium">{formatDate(o.delivery_date)}</div>
                        {o.delivery_time_slot && (
                          <div className="mt-0.5 text-xs text-gray-500 font-medium">{o.delivery_time_slot}</div>
                        )}
                      </td>
                      <td className="px-5 py-3.5">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-gray-400 text-xs truncate max-w-[80px]">{o.remarks || "-"}</span>
                          <svg className="w-4 h-4 shrink-0 text-gray-300 group-hover:text-gray-500 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                          </svg>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {totalOrders > 0 && (
          <Pagination
            total={totalOrders}
            page={page}
            pageSize={PAGE_SIZE}
            onPageChange={(p) => setOffset((p - 1) * PAGE_SIZE)}
            onPageSizeChange={() => {}}
          />
        )}
      </div>

        </div>
        {agentPanelOpen && (
          <div className="xl:sticky xl:top-5">
            <DashboardAgentPanel
              exceptions={agentExceptions}
              loading={agentLoading}
              scopeLabel={agentScopeLabel}
              executeEnabled={executeEnabled}
            />
          </div>
        )}
      </div>

      <OrderDetailModal
        order={selected}
        onClose={() => setSelected(null)}
        onMemoUpdated={(updated) => {
          setOrders((current) =>
            current.map((o) => ((o.uid || o.id) === (updated.uid || updated.id) ? updated : o))
          );
          setSelected(updated);
        }}
      />
    </>
  );
}
