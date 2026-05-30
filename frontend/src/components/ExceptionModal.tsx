import { useEffect, useRef, useState } from "react";
import {
  updateOrderStatus,
  type AgentExceptionCase,
  type AgentExceptionSeverity,
  type AgentExceptionType,
  type Order,
} from "../lib/api";
import OrderDetailContent from "./OrderDetailContent";

const SEVERITY_BG: Record<AgentExceptionSeverity, string> = {
  high: "bg-red-100 text-red-700 border-red-200",
  medium: "bg-amber-100 text-amber-700 border-amber-200",
  low: "bg-slate-100 text-slate-600 border-slate-200",
};

const SEVERITY_LABEL: Record<AgentExceptionSeverity, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

const TYPE_LABEL: Record<AgentExceptionType, string> = {
  quantity_anomaly: "数量異常",
  unit_anomaly: "単位異常",
  inventory_shortage: "在庫不足",
  needs_review: "要確認",
  awaiting_reply: "返信待ち",
};

interface ExceptionModalProps {
  exceptions: AgentExceptionCase[];
  orders: Order[];
  onClose: () => void;
  onMemoUpdated?: (order: Order) => void;
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Tokyo" });
  } catch {
    return "";
  }
}

/* ── Main modal ──────────────────────────────────────── */

export default function ExceptionModal({ exceptions, orders, onClose, onMemoUpdated }: ExceptionModalProps) {
  const [selectedId, setSelectedId] = useState<string>(exceptions.length > 0 ? exceptions[0].id : "");
  // 2タップ式: 同じ exception に対して1回目を踏むと confirmId にセットされ、
  // 3秒以内に 2 回目を踏むと確定。タイムアウトで自動キャンセル。
  const [resolveConfirmId, setResolveConfirmId] = useState<string | null>(null);
  const [resolving, setResolving] = useState(false);
  const [resolveError, setResolveError] = useState<string | null>(null);
  const confirmTimerRef = useRef<number | null>(null);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // 選択が変わったら確認状態をリセット
  useEffect(() => {
    setResolveConfirmId(null);
    setResolveError(null);
  }, [selectedId]);

  // confirm タイマーのクリーンアップ
  useEffect(() => {
    return () => {
      if (confirmTimerRef.current !== null) {
        window.clearTimeout(confirmTimerRef.current);
      }
    };
  }, []);

  function armResolveConfirm(excId: string) {
    setResolveError(null);
    setResolveConfirmId(excId);
    if (confirmTimerRef.current !== null) {
      window.clearTimeout(confirmTimerRef.current);
    }
    confirmTimerRef.current = window.setTimeout(() => {
      setResolveConfirmId((current) => (current === excId ? null : current));
      confirmTimerRef.current = null;
    }, 3000);
  }

  async function handleResolve(_excId: string, orderId: string) {
    if (confirmTimerRef.current !== null) {
      window.clearTimeout(confirmTimerRef.current);
      confirmTimerRef.current = null;
    }
    setResolving(true);
    setResolveError(null);
    try {
      const updated = await updateOrderStatus(orderId, "受注済み");
      onMemoUpdated?.(updated);
      setResolveConfirmId(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "対応済み更新に失敗しました";
      setResolveError(msg);
    } finally {
      setResolving(false);
    }
  }

  const orderMap = new Map(orders.map((o) => [o.uid || o.id, o]));
  const highCount = exceptions.filter((e) => e.severity === "high").length;
  const mediumCount = exceptions.filter((e) => e.severity === "medium").length;
  const selectedExc = exceptions.find((e) => e.id === selectedId);
  const selectedOrder = selectedExc ? orderMap.get(selectedExc.order_id) : undefined;

  if (exceptions.length === 0) return null;

  return (
    <div
      className="fixed inset-0 z-50 modal-overlay flex items-center justify-center p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl h-[85vh] overflow-hidden fade-in border border-gray-100 flex flex-col">
        {/* Header */}
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <img src="/favicon.png" alt="foogent" className="w-8 h-8 shrink-0" />
            <div>
              <h3 className="font-bold text-gray-900 text-sm">確認が必要な受注</h3>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="text-xs text-gray-500">{exceptions.length}件</span>
                {highCount > 0 && (
                  <span className="inline-flex items-center rounded-md bg-red-100 px-1.5 py-0.5 text-[10px] font-bold text-red-700">
                    高 {highCount}
                  </span>
                )}
                {mediumCount > 0 && (
                  <span className="inline-flex items-center rounded-md bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-700">
                    中 {mediumCount}
                  </span>
                )}
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* 2-pane body */}
        <div className="flex flex-1 min-h-0">
          {/* Left: exception list */}
          <div className="w-80 shrink-0 border-r border-gray-100 overflow-y-auto p-3 space-y-2">
            {exceptions.map((exc) => {
              const order = orderMap.get(exc.order_id);
              const isSelected = selectedId === exc.id;
              return (
                <button
                  key={exc.id}
                  type="button"
                  onClick={() => setSelectedId(exc.id)}
                  className={`w-full text-left rounded-xl p-3 transition-all border ${
                    isSelected
                      ? "bg-brand-50/60 border-brand-200 shadow-sm ring-1 ring-brand-200"
                      : "bg-white border-gray-100 hover:border-gray-200 hover:bg-gray-50/50"
                  }`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-1.5">
                      <span className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-bold ${SEVERITY_BG[exc.severity]}`}>
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                        {SEVERITY_LABEL[exc.severity]}
                      </span>
                      <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold ${SEVERITY_BG[exc.severity]}`}>
                        {TYPE_LABEL[exc.type] ?? exc.type}
                      </span>
                    </div>
                    <span className="text-[10px] text-gray-400 tabular-nums shrink-0 ml-2">
                      {order?.order_date ? order.order_date.slice(5, 10).replace("-", "/") : ""}
                      {order?.created_at ? ` ${formatTime(order.created_at)}` : ""}
                    </span>
                  </div>
                  <p className="text-sm font-semibold text-gray-900 truncate">{exc.customer_name} 様</p>
                  <p className="text-xs text-gray-500 mt-0.5 truncate">
                    {order?.items.map((i) => `${i.product_name} ${i.quantity ?? ""}${i.unit ?? ""}`).join("、") ?? ""}
                  </p>
                </button>
              );
            })}
          </div>

          {/* Right: order detail (reuses OrderDetailContent) */}
          <div className="flex-1 min-w-0 flex flex-col">
            {selectedExc && selectedOrder ? (
              <>
                <div className="flex-1 overflow-y-auto p-5">
                  <OrderDetailContent
                    key={selectedExc.id}
                    order={selectedOrder}
                    exceptions={exceptions}
                    onMemoUpdated={onMemoUpdated}
                    hideResolveAction
                  />
                </div>
                <div className="px-5 py-3 border-t border-gray-100 flex items-center justify-between gap-2 shrink-0">
                  <div className="flex-1 min-w-0">
                    {resolveError && (
                      <p className="text-xs text-red-600 truncate" role="alert">
                        {resolveError}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {selectedOrder.status === "要対応" && (
                      resolveConfirmId === selectedExc.id ? (
                        <button
                          type="button"
                          disabled={resolving}
                          onClick={() => handleResolve(selectedExc.id, selectedExc.order_id)}
                          className="btn-press inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-1.5 text-xs font-semibold shadow-md transition-colors disabled:opacity-60 disabled:cursor-not-allowed ring-2 ring-emerald-500 ring-offset-1"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                          {resolving ? "更新中…" : "もう一度押して確定"}
                        </button>
                      ) : (
                        <button
                          type="button"
                          disabled={resolving}
                          onClick={() => armResolveConfirm(selectedExc.id)}
                          className="btn-press inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 hover:text-emerald-800 px-3 py-1.5 text-xs font-semibold shadow-xs transition-all disabled:opacity-60"
                          title="要対応タグを外し、受注済みに変更します"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                          対応済みにする
                        </button>
                      )
                    )}
                    <button
                      type="button"
                      onClick={onClose}
                      className="btn-press inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 text-gray-600 px-3 py-1.5 text-xs font-medium transition-colors"
                    >
                      閉じる
                    </button>
                  </div>
                </div>
              </>
            ) : selectedExc && !selectedOrder ? (
              <div className="flex items-center justify-center h-full text-sm text-gray-400">
                受注データが見つかりません
              </div>
            ) : (
              <div className="flex items-center justify-center h-full text-sm text-gray-400">
                左のリストから確認事項を選択してください
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
