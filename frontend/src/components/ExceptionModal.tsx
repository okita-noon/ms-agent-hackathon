import { useEffect, useState } from "react";
import {
  previewAgentResolution,
  type AgentExceptionCase,
  type AgentExceptionSeverity,
  type AgentExceptionType,
  type AgentResolutionPreview,
  type Order,
} from "../lib/api";
import StatusBadge from "./StatusBadge";
import TempBadge from "./TempBadge";

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

function formatDate(value?: string): string {
  if (!value) return "-";
  return value.slice(0, 10);
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Tokyo" });
  } catch {
    return "";
  }
}

/* ── Right-pane detail ───────────────────────────────── */

function ExceptionDetail({
  exc,
  order,
  onOpenOrder,
}: {
  exc: AgentExceptionCase;
  order: Order | undefined;
  onOpenOrder: (order: Order) => void;
}) {
  const [preview, setPreview] = useState<AgentResolutionPreview | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setPreview(null);
    setLoadingPreview(true);
    previewAgentResolution(exc)
      .then((resp) => {
        if (!cancelled) setPreview(resp.preview);
      })
      .catch(() => { /* ignore */ })
      .finally(() => {
        if (!cancelled) setLoadingPreview(false);
      });
    return () => { cancelled = true; };
  }, [exc]);

  const sev = SEVERITY_BG[exc.severity];

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* Title */}
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-bold ${sev}`}>
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              {SEVERITY_LABEL[exc.severity]}
            </span>
            <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold ${sev}`}>
              {TYPE_LABEL[exc.type] ?? exc.type}
            </span>
          </div>
          <h4 className="text-base font-bold text-gray-900">{exc.title}</h4>
          <p className="text-xs text-gray-500 mt-1 leading-relaxed">{exc.summary}</p>
        </div>

        {/* 受注情報 */}
        {order && (
          <div>
            <h5 className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-2">受注情報</h5>
            <div className="grid grid-cols-2 gap-3 p-3 bg-gray-50/80 rounded-xl text-sm">
              <div>
                <p className="text-[10px] text-gray-400 font-medium">顧客名</p>
                <p className="font-semibold text-gray-800">{order.customer_name}</p>
              </div>
              <div>
                <p className="text-[10px] text-gray-400 font-medium">ステータス</p>
                <StatusBadge status={order.status} />
              </div>
              <div>
                <p className="text-[10px] text-gray-400 font-medium">受注日</p>
                <p className="text-gray-700">{formatDate(order.order_date)}</p>
              </div>
              <div>
                <p className="text-[10px] text-gray-400 font-medium">配送日</p>
                <p className="text-gray-700">{formatDate(order.delivery_date)}</p>
              </div>
            </div>
          </div>
        )}

        {/* 注文内容 */}
        {order && order.items.length > 0 && (
          <div>
            <h5 className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-2">注文内容</h5>
            <div className="border border-gray-100 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50/80 text-[10px] text-gray-400 uppercase tracking-wider">
                    <th className="text-left px-3 py-2">商品名</th>
                    <th className="text-left px-3 py-2">数量</th>
                    <th className="text-left px-3 py-2">単位</th>
                    <th className="text-left px-3 py-2">温度帯</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {order.items.map((item, i) => (
                    <tr key={i}>
                      <td className="px-3 py-2 font-medium text-gray-800">{item.product_name}</td>
                      <td className="px-3 py-2 tabular-nums">{item.quantity ?? "-"}</td>
                      <td className="px-3 py-2 text-gray-500">{item.unit ?? "-"}</td>
                      <td className="px-3 py-2"><TempBadge zone={item.temperature_zone} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* AI検知内容 */}
        {exc.evidence.length > 0 && (
          <div>
            <h5 className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-2">AI検知内容</h5>
            <div className="rounded-xl border-2 border-red-200 bg-red-50/40 p-3 space-y-1.5">
              {exc.evidence.map((ev, i) => (
                <div key={i} className="flex items-baseline gap-2 text-sm">
                  <span className="text-red-400 font-semibold text-xs shrink-0">{ev.label}</span>
                  <span className="text-red-800">{ev.value}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 推奨対応 */}
        <div>
          <h5 className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-2">推奨対応</h5>
          {loadingPreview ? (
            <div className="flex items-center gap-2 py-3 text-gray-400 text-xs">
              <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              対応案を生成中...
            </div>
          ) : preview ? (
            <div className="space-y-3">
              {preview.confidence > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500">信頼度</span>
                  <span className="text-xs font-bold text-brand-700">{Math.round(preview.confidence * 100)}%</span>
                </div>
              )}
              {preview.recommended_actions.length > 0 && (
                <ul className="space-y-1">
                  {preview.recommended_actions.map((action, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                      <svg className="w-4 h-4 text-brand-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4" />
                      </svg>
                      {action}
                    </li>
                  ))}
                </ul>
              )}
              {preview.customer_message && (
                <div className="p-3 bg-brand-50/60 border border-brand-100 rounded-lg">
                  <p className="text-[10px] font-semibold text-brand-600 uppercase tracking-wider mb-1">顧客向け文面案</p>
                  <p className="text-sm text-brand-900 whitespace-pre-wrap leading-relaxed">{preview.customer_message}</p>
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-gray-400 py-2">{exc.suggested_action || "対応案を取得できませんでした"}</p>
          )}
        </div>

        {/* 備考 */}
        {order?.remarks && (
          <div className="p-3 bg-amber-50/60 rounded-xl border border-amber-100">
            <p className="text-[10px] font-medium text-amber-600 uppercase tracking-wider mb-1">備考</p>
            <p className="text-sm text-amber-900">{order.remarks}</p>
          </div>
        )}
      </div>

      {/* Detail footer */}
      <div className="px-5 py-3 border-t border-gray-100 flex items-center justify-end gap-2 shrink-0">
        {order && (
          <button
            type="button"
            onClick={() => onOpenOrder(order)}
            className="btn-press inline-flex items-center gap-1.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white px-3 py-1.5 text-xs font-medium transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
            受注詳細を開く
          </button>
        )}
      </div>
    </div>
  );
}

/* ── Main modal ──────────────────────────────────────── */

export default function ExceptionModal({ exceptions, orders, onClose, onOpenOrder }: ExceptionModalProps) {
  const [selectedId, setSelectedId] = useState<string>(exceptions.length > 0 ? exceptions[0].id : "");

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

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
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl h-[80vh] overflow-hidden fade-in border border-gray-100 flex flex-col">
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

          {/* Right: selected exception detail */}
          <div className="flex-1 min-w-0">
            {selectedExc ? (
              <ExceptionDetail
                key={selectedExc.id}
                exc={selectedExc}
                order={selectedOrder}
                onOpenOrder={(order) => { onClose(); onOpenOrder(order); }}
              />
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
