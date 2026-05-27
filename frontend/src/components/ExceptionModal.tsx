import { useState } from "react";
import {
  previewAgentResolution,
  type AgentExceptionCase,
  type AgentExceptionSeverity,
  type AgentExceptionType,
  type AgentResolutionPreview,
  type Order,
} from "../lib/api";
import TempBadge from "./TempBadge";

/* ------------------------------------------------------------------ */
/*  定数                                                                */
/* ------------------------------------------------------------------ */

const SEVERITY_BG: Record<AgentExceptionSeverity, string> = {
  high: "bg-red-100 text-red-700 border-red-200",
  medium: "bg-amber-100 text-amber-700 border-amber-200",
  low: "bg-slate-100 text-slate-600 border-slate-200",
};

const SEVERITY_DETAIL: Record<AgentExceptionSeverity, { border: string; bg: string; icon: string; title: string; text: string; evidence: string }> = {
  high:   { border: "border-red-200",   bg: "bg-red-50/60",   icon: "text-red-500",   title: "text-red-800",   text: "text-red-700",   evidence: "text-red-700" },
  medium: { border: "border-amber-200", bg: "bg-amber-50/60", icon: "text-amber-500", title: "text-amber-800", text: "text-amber-700", evidence: "text-amber-700" },
  low:    { border: "border-slate-200", bg: "bg-slate-50/60", icon: "text-slate-500", title: "text-slate-700", text: "text-slate-600", evidence: "text-slate-600" },
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

const CHANNEL_LABEL: Record<string, { label: string; icon: string }> = {
  LINE: { label: "LINE", icon: "💬" },
  Phone: { label: "電話発注", icon: "📞" },
  Email: { label: "メール", icon: "✉" },
};

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

interface ExceptionModalProps {
  exceptions: AgentExceptionCase[];
  orders: Order[];
  onClose: () => void;
  onOpenOrder: (order: Order) => void;
  initialExceptionId?: string;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function ExceptionModal({
  exceptions,
  orders,
  onClose,
  onOpenOrder,
  initialExceptionId,
}: ExceptionModalProps) {
  const [selectedId, setSelectedId] = useState<string>(
    initialExceptionId || exceptions[0]?.id || ""
  );
  const [previewById, setPreviewById] = useState<
    Record<string, AgentResolutionPreview>
  >({});
  const [previewingId, setPreviewingId] = useState<string | null>(null);
  const [memos, setMemos] = useState<Record<string, string>>({});

  const selected = exceptions.find((e) => e.id === selectedId) || null;
  const orderMap = new Map(orders.map((o) => [o.uid || o.id, o]));
  const selectedOrder = selected ? orderMap.get(selected.order_id) : null;

  const highCount = exceptions.filter((e) => e.severity === "high").length;
  const mediumCount = exceptions.filter((e) => e.severity === "medium").length;

  async function handlePreview(exc: AgentExceptionCase) {
    setPreviewingId(exc.id);
    try {
      const resp = await previewAgentResolution(exc);
      if (resp.preview) {
        setPreviewById((prev) => ({ ...prev, [exc.id]: resp.preview! }));
      }
    } catch {
      /* ignore */
    } finally {
      setPreviewingId(null);
    }
  }

  if (exceptions.length === 0) return null;

  return (
    <div
      className="fixed inset-0 z-50 modal-overlay flex items-center justify-center p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl max-h-[90vh] overflow-hidden fade-in border border-gray-100 flex flex-col">
        {/* ── Header ─────────────────────────────────── */}
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <img
              src="/favicon.png"
              alt="foogent"
              className="w-9 h-9 shrink-0"
            />
            <div>
              <h3 className="font-bold text-gray-900 text-base">
                確認が必要な受注
              </h3>
              <p className="text-xs text-gray-500 mt-0.5">
                AIが検知した{" "}
                <span className="font-semibold">{exceptions.length}件</span>
                の確認事項
              </p>
            </div>
            <div className="flex items-center gap-1.5 ml-2">
              {highCount > 0 && (
                <span className="inline-flex items-center rounded-md bg-red-100 border border-red-200 px-2 py-0.5 text-xs font-bold text-red-700">
                  高 {highCount}
                </span>
              )}
              {mediumCount > 0 && (
                <span className="inline-flex items-center rounded-md bg-amber-100 border border-amber-200 px-2 py-0.5 text-xs font-bold text-amber-700">
                  中 {mediumCount}
                </span>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* ── Body: 2 panes ──────────────────────────── */}
        <div className="flex flex-1 min-h-0">
          {/* Left: exception list */}
          <div className="w-[340px] shrink-0 border-r border-gray-100 overflow-y-auto bg-gray-50/40">
            <div className="p-3 space-y-2">
              {exceptions.map((exc) => {
                const isActive = exc.id === selectedId;
                return (
                  <button
                    key={exc.id}
                    type="button"
                    onClick={() => setSelectedId(exc.id)}
                    className={`w-full text-left rounded-xl p-3.5 transition-all ${
                      isActive
                        ? "bg-white border-2 border-brand-300 shadow-sm"
                        : "bg-white border border-gray-100 hover:border-gray-200 hover:shadow-sm"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-bold ${SEVERITY_BG[exc.severity]}`}
                        >
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                          </svg>
                          {SEVERITY_LABEL[exc.severity]}
                        </span>
                        <span
                          className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold ${SEVERITY_BG[exc.severity]}`}
                        >
                          {TYPE_LABEL[exc.type] ?? exc.type}
                        </span>
                      </div>
                      <span className="text-[11px] text-gray-400 tabular-nums shrink-0 ml-2">
                        {(() => {
                          const o = orderMap.get(exc.order_id);
                          return o?.order_date
                            ? `${o.order_date.slice(0, 10)} ${
                                o.created_at
                                  ? new Date(o.created_at).toLocaleTimeString(
                                      "ja-JP",
                                      {
                                        hour: "2-digit",
                                        minute: "2-digit",
                                        timeZone: "Asia/Tokyo",
                                      }
                                    )
                                  : ""
                              }`
                            : "";
                        })()}
                      </span>
                    </div>
                    <p className="text-sm font-semibold text-gray-900">
                      {exc.customer_name} 様
                    </p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {(() => {
                        const o = orderMap.get(exc.order_id);
                        if (!o) return "";
                        return o.items
                          .map(
                            (i) =>
                              `${i.product_name} ${i.quantity ?? ""}${i.unit ?? ""}`
                          )
                          .join("、");
                      })()}
                    </p>
                    <p className="mt-1.5 text-[11px] text-gray-500 leading-relaxed line-clamp-2">
                      {exc.summary}
                    </p>
                    {isActive && (
                      <div className="mt-1.5 flex justify-end">
                        <svg
                          className="w-4 h-4 text-brand-500"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M9 5l7 7-7 7"
                          />
                        </svg>
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Right: detail pane */}
          <div className="flex-1 overflow-y-auto p-6 space-y-5">
            {selected && selectedOrder ? (
              <>
                {/* 受注情報 */}
                <div>
                  <h4 className="text-sm font-bold text-gray-900 mb-3">
                    受注情報
                  </h4>
                  <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
                    <div className="flex gap-2">
                      <span className="text-gray-400 shrink-0 w-16">
                        受注ID
                      </span>
                      <span className="font-mono text-gray-700">
                        {selectedOrder.uid || selectedOrder.id}
                      </span>
                    </div>
                    <div className="flex gap-2">
                      <span className="text-gray-400 shrink-0 w-16">
                        顧客名
                      </span>
                      <span className="font-medium text-gray-900">
                        {selectedOrder.customer_name} 様
                      </span>
                    </div>
                    <div className="flex gap-2">
                      <span className="text-gray-400 shrink-0 w-16">
                        受注日時
                      </span>
                      <span className="text-gray-700 tabular-nums">
                        {selectedOrder.order_date?.slice(0, 10)}{" "}
                        {selectedOrder.created_at
                          ? new Date(
                              selectedOrder.created_at
                            ).toLocaleTimeString("ja-JP", {
                              hour: "2-digit",
                              minute: "2-digit",
                              timeZone: "Asia/Tokyo",
                            })
                          : ""}
                      </span>
                    </div>
                    <div className="flex gap-2">
                      <span className="text-gray-400 shrink-0 w-16">
                        配送日時
                      </span>
                      <span className="text-gray-700 tabular-nums">
                        {selectedOrder.delivery_date?.slice(0, 10) || "-"}
                        {selectedOrder.delivery_time_slot
                          ? ` ${selectedOrder.delivery_time_slot}`
                          : ""}
                      </span>
                    </div>
                    <div className="flex gap-2">
                      <span className="text-gray-400 shrink-0 w-16">
                        チャネル
                      </span>
                      <span className="text-gray-700">
                        {CHANNEL_LABEL[selectedOrder.source]?.icon || ""}{" "}
                        {CHANNEL_LABEL[selectedOrder.source]?.label ||
                          selectedOrder.source}
                      </span>
                    </div>
                  </div>
                </div>

                {/* 注文内容 */}
                <div>
                  <h4 className="text-sm font-bold text-gray-900 mb-3">
                    注文内容
                  </h4>
                  <div className="border border-gray-100 rounded-xl overflow-hidden">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-gray-50/80 text-[11px] text-gray-400 uppercase tracking-wider">
                          <th className="text-left px-4 py-2.5">商品名</th>
                          <th className="text-left px-4 py-2.5">
                            規格・温度帯
                          </th>
                          <th className="text-right px-4 py-2.5">数量</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-50">
                        {selectedOrder.items.map((item, i) => (
                          <tr key={i}>
                            <td className="px-4 py-2.5 font-medium text-gray-800">
                              {item.product_name}
                            </td>
                            <td className="px-4 py-2.5">
                              <div className="flex items-center gap-1.5">
                                <span className="text-gray-500">
                                  {item.quantity}
                                  {item.unit}
                                </span>
                                <span className="text-gray-400">/</span>
                                <TempBadge zone={item.temperature_zone} />
                              </div>
                            </td>
                            <td className="px-4 py-2.5 text-right tabular-nums font-medium">
                              {item.quantity}
                              {item.unit}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* AI検知内容 */}
                <div>
                  <h4 className="text-sm font-bold text-gray-900 mb-3">
                    AI検知内容
                  </h4>
                  {(() => {
                    const sc = SEVERITY_DETAIL[selected.severity];
                    return (
                      <div className={`rounded-xl border-2 ${sc.border} ${sc.bg} p-4`}>
                        <div className="flex items-start gap-2">
                          <svg
                            className={`w-5 h-5 ${sc.icon} shrink-0 mt-0.5`}
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                            />
                          </svg>
                          <div>
                            <p className={`text-sm font-bold ${sc.title}`}>
                              {selected.title}
                            </p>
                            <p className={`text-sm ${sc.text} mt-1 leading-relaxed`}>
                              {selected.summary}
                            </p>
                            {selected.evidence.length > 0 && (
                              <div className={`mt-2 text-sm ${sc.evidence}`}>
                                {selected.evidence.map((ev, i) => (
                                  <span key={i}>
                                    {i > 0 && "、"}
                                    {ev.label}: <strong>{ev.value}</strong>
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })()}
                </div>

                {/* 推奨対応 */}
                <div>
                  <h4 className="text-sm font-bold text-gray-900 mb-3">
                    推奨対応
                  </h4>
                  {previewById[selected.id] ? (
                    <div className="space-y-3">
                      <ul className="space-y-1.5">
                        {previewById[selected.id].recommended_actions.map(
                          (action, i) => (
                            <li
                              key={i}
                              className="flex gap-2 text-sm text-gray-700"
                            >
                              <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-brand-500 shrink-0" />
                              <span>{action}</span>
                            </li>
                          )
                        )}
                      </ul>
                      {previewById[selected.id].customer_message && (
                        <div className="rounded-lg bg-gray-50 border border-gray-200 px-4 py-3 text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
                          {previewById[selected.id].customer_message}
                        </div>
                      )}
                    </div>
                  ) : selected.suggested_action ? (
                    <div className="space-y-3">
                      <ul className="space-y-1.5">
                        <li className="flex gap-2 text-sm text-gray-700">
                          <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-brand-500 shrink-0" />
                          <span>{selected.suggested_action}</span>
                        </li>
                      </ul>
                      <button
                        type="button"
                        onClick={() => handlePreview(selected)}
                        disabled={previewingId === selected.id}
                        className="inline-flex items-center gap-2 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-xs font-semibold text-brand-700 hover:bg-brand-100 disabled:opacity-60 transition-colors"
                      >
                        <svg
                          className={`w-3.5 h-3.5 ${previewingId === selected.id ? "animate-spin" : ""}`}
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                          />
                        </svg>
                        {previewingId === selected.id
                          ? "対応案を生成中..."
                          : "AIに詳しい対応案を確認する"}
                      </button>
                    </div>
                  ) : (
                    <p className="text-sm text-gray-400">
                      推奨対応はありません
                    </p>
                  )}
                </div>

                {/* 担当メモ */}
                <div>
                  <h4 className="text-sm font-bold text-gray-900 mb-2">
                    担当メモ
                  </h4>
                  <textarea
                    value={memos[selected.id] || ""}
                    onChange={(e) =>
                      setMemos((prev) => ({
                        ...prev,
                        [selected.id]: e.target.value,
                      }))
                    }
                    placeholder="メモを入力してください（任意）"
                    maxLength={200}
                    rows={3}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none bg-white resize-none focus:border-brand-400 focus:ring-1 focus:ring-brand-200"
                  />
                  <p className="text-right text-[11px] text-gray-400 mt-1 tabular-nums">
                    {(memos[selected.id] || "").length} / 200
                  </p>
                </div>
              </>
            ) : (
              <div className="flex items-center justify-center h-full text-gray-400 text-sm">
                左のリストから確認事項を選択してください
              </div>
            )}
          </div>
        </div>

        {/* ── Footer ─────────────────────────────────── */}
        <div className="px-6 py-3 border-t border-gray-100 flex items-center justify-end shrink-0">
          <button
            onClick={onClose}
            className="px-5 py-2 text-sm font-medium text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-lg transition-colors"
          >
            閉じる
          </button>
        </div>
      </div>
    </div>
  );
}
