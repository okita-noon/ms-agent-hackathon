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
import ExceptionModal from "../components/ExceptionModal";
import AgentLoadingBanner from "../components/AgentLoadingBanner";
import NewOrderToast, { type ToastItem } from "../components/NewOrderToast";
import { offsetDate, todayJst } from "../lib/date";

const PAGE_SIZE = 50;

type DateField = "delivery_date" | "order_date";

const TYPE_LABEL: Record<string, string> = {
  quantity_anomaly: "数量",
  unit_anomaly: "単位",
  inventory_shortage: "在庫",
  needs_review: "要確認",
  awaiting_reply: "返信待ち",
};

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
  const [, setLiveStatus] = useState<"connecting" | "live" | "reconnecting" | "offline">("connecting");
  const [recentOrderIds, setRecentOrderIds] = useState<Set<string>>(() => new Set());
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [exceptionModalOpen, setExceptionModalOpen] = useState(false);

  const triageAvailable = Boolean(agentFeatures?.dashboard_agent && agentFeatures.exception_triage);

  // Build order_id → exceptions lookup
  const exceptionsByOrderId = useMemo(() => {
    const map = new Map<string, AgentExceptionCase[]>();
    for (const exc of agentExceptions) {
      const arr = map.get(exc.order_id) || [];
      arr.push(exc);
      map.set(exc.order_id, arr);
    }
    return map;
  }, [agentExceptions]);

  // 要対応ステータスの受注に紐づく severity=high 例外数（バナー表示用）
  const reviewOrderIds = useMemo(
    () => new Set(orders.filter((o) => normalizeStatus(o.status) === "要対応").map((o) => o.id)),
    [orders]
  );
  const highExceptionCount = agentExceptions.filter(
    (e) => e.severity === "high" && reviewOrderIds.has(e.order_id)
  ).length;

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
    if (!triageAvailable) {
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
  }, [triageAvailable, dateFilterEnabled, date, dateField, statusFilter, query, offset]);

  useEffect(() => {
    void Promise.resolve().then(loadAgentExceptions);
  }, [loadAgentExceptions]);

  useEffect(() => {
    const events = createOrderEventSource();
    setLiveStatus("connecting");

    function handleConnected() {
      setLiveStatus("live");
    }

    function handleOrderEvent(eventType: "created" | "updated") {
      return (event: MessageEvent<string>) => {
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

          const toastId = `${payload.order_id}-${Date.now()}`;
          const toast: ToastItem = {
            id: toastId,
            order_id: payload.order_id,
            customer_name: payload.customer_name,
            source: payload.source,
            received_at: new Date().toISOString(),
            type: eventType,
          };
          setToasts((current) => [...current.slice(-3), toast]);
          window.setTimeout(() => {
            setToasts((current) => current.filter((t) => t.id !== toastId));
          }, 5000);
        }
        void load();
        void loadAgentExceptions();
      };
    }

    const handleCreated = handleOrderEvent("created");
    const handleUpdated = handleOrderEvent("updated");

    events.addEventListener("connected", handleConnected);
    events.addEventListener("order_created", handleCreated);
    events.addEventListener("order_updated", handleUpdated);
    events.onerror = () => setLiveStatus("reconnecting");

    return () => {
      events.removeEventListener("connected", handleConnected);
      events.removeEventListener("order_created", handleCreated);
      events.removeEventListener("order_updated", handleUpdated);
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
  // キャンセルを除外し、status=要対応 のみ正確にカウント
  const reviewOrderCount = orders.filter(
    (o) => normalizeStatus(o.status) === "要対応"
  ).length;
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

  function openExceptionModal() {
    setExceptionModalOpen(true);
  }

  const filterStatusUI = statusFilter || "すべて";
  const todayStr = todayJst();

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
              <div className="inline-flex rounded-lg border border-gray-200 bg-white overflow-hidden text-xs font-medium">
                <button type="button" onClick={() => changeDateField("delivery_date")} className={`px-3 py-2 transition-colors ${dateField === "delivery_date" ? "bg-brand-600 text-white" : "text-gray-500 hover:bg-gray-50"}`}>配送日</button>
                <button type="button" onClick={() => changeDateField("order_date")} className={`px-3 py-2 border-l border-gray-200 transition-colors ${dateField === "order_date" ? "bg-brand-600 text-white" : "text-gray-500 hover:bg-gray-50"}`}>受注日</button>
              </div>
              <div className="inline-flex rounded-lg border border-gray-200 bg-white overflow-hidden text-xs font-medium">
                <button type="button" onClick={() => changeDate(offsetDate(date, -1))} className="px-3 py-2 text-gray-500 hover:bg-gray-50 transition-colors">前日</button>
                <button type="button" onClick={() => changeDate(todayStr)} className={`px-3 py-2 border-l border-gray-200 transition-colors ${date === todayStr ? "bg-brand-50 text-brand-700 font-semibold" : "text-gray-500 hover:bg-gray-50"}`}>本日</button>
                <button type="button" onClick={() => changeDate(offsetDate(date, 1))} className="px-3 py-2 border-l border-gray-200 text-gray-500 hover:bg-gray-50 transition-colors">翌日</button>
              </div>
              <input type="date" value={date} onChange={(e) => changeDate(e.target.value)} className="input-field border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none bg-white" />
            </>
          )}

        </div>
      </div>

      {/* foogent AI banner: loading → result → hidden */}
      {triageAvailable && agentLoading && agentExceptions.length === 0 && (
        <AgentLoadingBanner />
      )}
      {triageAvailable && (reviewOrderCount > 0 || agentExceptions.length > 0) && (
        <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 flex items-center gap-3 fade-in">
          <img src="/favicon.png" alt="foogent" className="w-8 h-8 shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-amber-900">
                foogent AI: 要対応 {reviewOrderCount} 件
              </span>
              {highExceptionCount > 0 ? (
                <span className="inline-flex items-center rounded-md bg-red-100 px-1.5 py-0.5 text-[10px] font-bold text-red-700">
                  うち急ぎ {highExceptionCount} 件
                </span>
              ) : (
                <span className="inline-flex items-center rounded-md bg-green-100 px-1.5 py-0.5 text-[10px] font-bold text-green-700">
                  急ぎなし
                </span>
              )}
            </div>
            <p className="text-xs text-amber-700 mt-0.5">
              数量異常・在庫不足など、担当者の確認が必要な受注があります
            </p>
          </div>
          <button
            type="button"
            onClick={() => openExceptionModal()}
            className="shrink-0 rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs font-semibold text-amber-800 hover:bg-amber-100 transition-colors"
          >
            詳細を確認
          </button>
        </div>
      )}

      {/* Order table */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
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
                    <button type="button" className="inline-flex items-center gap-1 hover:text-gray-600 transition-colors" onClick={() => setSortKey(sortKey === "order_date_desc" ? "order_date_asc" : "order_date_desc")}>
                      受注日時
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        {sortKey === "order_date_asc"
                          ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                          : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />}
                      </svg>
                    </button>
                  </th>
                  <th className="px-5 py-3">
                    <button type="button" className="inline-flex items-center gap-1 hover:text-gray-600 transition-colors" onClick={() => setSortKey(sortKey === "customer_name" ? "order_date_desc" : "customer_name")}>
                      顧客名
                      {sortKey === "customer_name" && (
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" /></svg>
                      )}
                    </button>
                  </th>
                  <th className="px-5 py-3">商品（温度帯）</th>
                  <th className="px-5 py-3">
                    <button type="button" className="inline-flex items-center gap-1 hover:text-gray-600 transition-colors" onClick={() => setSortKey(sortKey === "status" ? "order_date_desc" : "status")}>
                      ステータス
                      {sortKey === "status" && (
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" /></svg>
                      )}
                    </button>
                  </th>
                  <th className="px-5 py-3">配送日</th>
                  {triageAvailable && (agentExceptions.length > 0 || agentLoading) && (
                    <th className="px-5 py-3">
                      <span className="inline-flex items-center gap-1">
                        <img src="/favicon.png" alt="" className={`w-3 h-3 ${agentLoading ? "ai-icon-glow" : ""}`} />
                        AI検知
                      </span>
                    </th>
                  )}
                  <th className="px-5 py-3">備考</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {displayOrders.map((o) => {
                  const items = o.items || [];
                  const orderId = o.uid || o.id || "";
                  const excList = exceptionsByOrderId.get(orderId);
                  return (
                    <tr
                      key={orderId}
                      className={`row-hover cursor-pointer group ${
                        recentOrderIds.has(orderId)
                          ? "bg-green-50 animate-new-order"
                          : normalizeStatus(o.status) === "要対応"
                          ? "row-review"
                          : ""
                      }`}
                      onClick={() => setSelected(o)}
                    >
                      <td className="px-5 py-3.5 whitespace-nowrap tabular-nums">
                        <div className="text-gray-700 font-medium">{formatDate(o.order_date)}</div>
                        <div className="mt-0.5 text-xs text-gray-500 font-medium">{formatTime(o.created_at || o.updated_at)}</div>
                        <div className="mt-1.5"><ChannelBadge source={o.source} /></div>
                      </td>
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-1.5">
                          <span className="font-medium text-gray-900 group-hover:text-brand-700 transition-colors">{o.customer_name}</span>
                          {recentOrderIds.has(orderId) && (
                            <span className="inline-flex items-center rounded-full bg-green-500 px-1.5 py-0.5 text-[9px] font-extrabold tracking-widest text-white uppercase animate-bounce-once">
                              NEW
                            </span>
                          )}
                        </div>
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
                      {triageAvailable && (agentExceptions.length > 0 || agentLoading) && (
                        <td className="px-5 py-3.5">
                          {agentLoading && !excList ? (
                            <div className="ai-cell-shimmer h-5 w-16" />
                          ) : excList ? (
                            <div className="flex flex-wrap gap-1">
                              {excList.map((exc) => (
                                <span
                                  key={exc.id}
                                  className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-bold ${
                                    exc.severity === "high"
                                      ? "bg-red-100 text-red-700"
                                      : "bg-amber-100 text-amber-700"
                                  }`}
                                >
                                  {TYPE_LABEL[exc.type] ?? exc.type}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-gray-300 text-xs">—</span>
                          )}
                        </td>
                      )}
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

      {/* Order detail modal */}
      <OrderDetailModal
        order={selected}
        onClose={() => setSelected(null)}
        onMemoUpdated={(updated) => {
          setOrders((current) =>
            current.map((o) => ((o.uid || o.id) === (updated.uid || updated.id) ? updated : o))
          );
          setSelected(updated);
        }}
        exceptions={agentExceptions}
      />

      {exceptionModalOpen && (reviewOrderCount > 0 || agentExceptions.length > 0) && (
        <ExceptionModal
          exceptions={(() => {
            // AI例外に紐づかない要対応注文を擬似ケースとして後続に追加
            const exceptionOrderIds = new Set(agentExceptions.map((e) => e.order_id));
            const pseudoCases = orders
              .filter(
                (o) =>
                  normalizeStatus(o.status) === "要対応" &&
                  !exceptionOrderIds.has(o.uid ?? o.id ?? "")
              )
              .map((o) => ({
                id: `pseudo-needs-review-${o.uid ?? o.id ?? ""}`,
                order_id: o.uid ?? o.id ?? "",
                customer_id: o.customer_id ?? "",
                customer_name: o.customer_name ?? "",
                type: "needs_review" as const,
                severity: "medium" as const,
                title: "担当者確認が必要な受注",
                summary: "AIが自動処理できず「要対応」となっています。",
                suggested_action:
                  "注文内容と会話履歴を確認し、必要なら顧客へ問い合わせてください。",
                evidence: [{ label: "ステータス", value: "要対応" }],
                metadata: {},
              }));
            return [...agentExceptions, ...pseudoCases];
          })()}
          orders={orders}
          onClose={() => setExceptionModalOpen(false)}
          onMemoUpdated={(updated) => {
            setOrders((current) =>
              current.map((o) => ((o.uid || o.id) === (updated.uid || updated.id) ? updated : o))
            );
          }}
        />
      )}

      <NewOrderToast
        toasts={toasts}
        onDismiss={(id) => setToasts((current) => current.filter((t) => t.id !== id))}
      />
    </>
  );
}
