import { useEffect, useState } from "react";
import type {
  AgentExceptionCase,
  AgentExceptionSeverity,
  AgentExceptionType,
  Order,
} from "../lib/api";

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
  onOpenOrder: (order: Order) => void;
}

export default function ExceptionModal({
  exceptions,
  orders,
  onClose,
  onOpenOrder,
}: ExceptionModalProps) {
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const orderMap = new Map(orders.map((o) => [o.uid || o.id, o]));

  const highCount = exceptions.filter((e) => e.severity === "high").length;
  const mediumCount = exceptions.filter((e) => e.severity === "medium").length;

  if (exceptions.length === 0) return null;

  return (
    <div
      className="fixed inset-0 z-50 modal-overlay flex items-center justify-center p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md max-h-[80vh] overflow-hidden fade-in border border-gray-100 flex flex-col">
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

        {/* List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {exceptions.map((exc) => {
            const order = orderMap.get(exc.order_id);
            const isHovered = hoveredId === exc.id;
            return (
              <button
                key={exc.id}
                type="button"
                onMouseEnter={() => setHoveredId(exc.id)}
                onMouseLeave={() => setHoveredId(null)}
                onClick={() => {
                  if (order) {
                    onClose();
                    onOpenOrder(order);
                  }
                }}
                className={`w-full text-left rounded-xl p-3.5 transition-all border ${
                  isHovered
                    ? "bg-brand-50/50 border-brand-200 shadow-sm"
                    : "bg-white border-gray-100 hover:border-gray-200"
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
                  <span className="text-[11px] text-gray-400 tabular-nums shrink-0 ml-2">
                    {(() => {
                      if (!order?.order_date) return "";
                      const time = order.created_at
                        ? new Date(order.created_at).toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Tokyo" })
                        : "";
                      return `${order.order_date.slice(0, 10)} ${time}`;
                    })()}
                  </span>
                </div>
                <p className="text-sm font-semibold text-gray-900">{exc.customer_name} 様</p>
                <p className="text-xs text-gray-500 mt-0.5">
                  {order?.items.map((i) => `${i.product_name} ${i.quantity ?? ""}${i.unit ?? ""}`).join("、") ?? ""}
                </p>
                <p className="mt-1.5 text-[11px] text-gray-500 leading-relaxed line-clamp-2">{exc.summary}</p>
              </button>
            );
          })}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-gray-100 flex justify-end shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-lg transition-colors"
          >
            閉じる
          </button>
        </div>
      </div>
    </div>
  );
}
