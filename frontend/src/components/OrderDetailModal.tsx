import { useEffect, useState } from "react";
import type { Message, Order } from "../lib/api";
import { fetchOrderMessages } from "../lib/api";
import StatusBadge from "./StatusBadge";
import TempBadge from "./TempBadge";

interface Props {
  order: Order | null;
  onClose: () => void;
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] font-medium text-gray-400 uppercase tracking-wider mb-1">{label}</p>
      <p className="text-sm font-medium text-gray-800">{value || "-"}</p>
    </div>
  );
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function ChannelIcon({ channel }: { channel: string }) {
  if (channel === "line") {
    return (
      <svg className="w-3.5 h-3.5 text-green-500" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2C6.48 2 2 5.92 2 10.66c0 2.75 1.53 5.18 3.93 6.76-.14.49-.9 3.15-.93 3.37 0 0-.02.15.07.21.09.06.2.03.2.03.27-.04 3.12-2.05 3.61-2.39.69.1 1.4.16 2.12.16 5.52 0 10-3.92 10-8.66S17.52 2 12 2z" />
      </svg>
    );
  }
  if (channel === "phone") {
    return (
      <svg className="w-3.5 h-3.5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
      </svg>
    );
  }
  return (
    <svg className="w-3.5 h-3.5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
    </svg>
  );
}

function MessageThread({ orderId }: { orderId: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchOrderMessages(orderId)
      .then((data) => {
        if (!cancelled) setMessages(data.messages);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [orderId]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-4 justify-center text-gray-400 text-xs">
        <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        会話履歴を読み込み中...
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <div className="flex items-center gap-2 mb-3">
          <h5 className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">注文会話履歴</h5>
        </div>
        <div className="border border-gray-100 rounded-xl bg-gray-50/40 p-4 text-center text-sm text-gray-400">
          会話履歴の読み込みに失敗しました
        </div>
      </div>
    );
  }

  if (messages.length === 0) {
    return (
      <div>
        <div className="flex items-center gap-2 mb-3">
          <h5 className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">注文会話履歴</h5>
        </div>
        <div className="border border-dashed border-gray-200 rounded-xl bg-gray-50/20 p-4 text-center text-sm text-gray-400">
          この注文の会話履歴はありません
        </div>
      </div>
    );
  }

  const channel = messages[0]?.channel || "";

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <h5 className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">注文会話履歴</h5>
        <ChannelIcon channel={channel} />
      </div>
      <div className="border border-gray-100 rounded-xl bg-gray-50/40 p-4 space-y-3 max-h-72 overflow-y-auto">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "user" ? "justify-start" : "justify-end"}`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-2.5 ${
                msg.role === "user"
                  ? "bg-white border border-gray-200 rounded-tl-md"
                  : "bg-brand-50 border border-brand-100 rounded-tr-md"
              }`}
            >
              <p className="text-sm text-gray-800 whitespace-pre-wrap">{msg.text}</p>
              <p className={`text-[10px] mt-1 ${msg.role === "user" ? "text-gray-400" : "text-brand-400"}`}>
                {msg.role === "user" ? "お客様" : "AI"} ・ {formatTime(msg.created_at)}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function OrderDetailModal({ order, onClose }: Props) {
  if (!order) return null;

  const orderId = order.uid || order.id || "";

  return (
    <div
      className="fixed inset-0 z-50 modal-overlay flex items-center justify-center p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden fade-in border border-gray-100">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-brand-50 flex items-center justify-center">
              <svg className="w-4 h-4 text-brand-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <div>
              <h3 className="font-bold text-gray-900 text-sm">受注詳細</h3>
              <p className="text-[11px] text-gray-400 font-mono">{orderId}</p>
            </div>
          </div>
          <button onClick={onClose} className="w-8 h-8 rounded-lg hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-600 transition-colors">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="overflow-y-auto max-h-[calc(90vh-130px)] p-6 space-y-6">
          <div className="flex items-start justify-between">
            <div>
              <h4 className="text-lg font-bold text-gray-900">{order.customer_name}</h4>
              <span className={`text-xs font-semibold ${order.source === "LINE" ? "text-green-600" : "text-brand-600"}`}>{order.source}</span>
            </div>
            <StatusBadge status={order.status} />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-4 bg-gray-50/80 rounded-xl">
            <Field label="受注日" value={order.order_date || ""} />
            <Field label="最終処理" value={order.updated_at ? formatTime(order.updated_at) : ""} />
            <Field label="手配日" value={order.preparation_date || ""} />
            <Field label="配送日" value={order.delivery_date || ""} />
            <Field label="配送時間帯" value={order.delivery_time_slot || "指定なし"} />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 p-4 bg-gray-50/80 rounded-xl">
            <Field label="配送便" value={order.delivery_carrier || ""} />
            <Field label="配送ルート" value={order.delivery_route || ""} />
            <Field label="送り状番号" value={order.yamato_tracking_number || ""} />
          </div>

          <div>
            <h5 className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-3">注文明細</h5>
            <div className="border border-gray-100 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50/80 text-[11px] text-gray-400 uppercase tracking-wider">
                    <th className="text-left px-4 py-2.5">商品名</th>
                    <th className="text-left px-4 py-2.5">数量</th>
                    <th className="text-left px-4 py-2.5">単位</th>
                    <th className="text-left px-4 py-2.5">温度帯</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {order.items.map((item, i) => (
                    <tr key={i}>
                      <td className="px-4 py-2.5 font-medium text-gray-800">{item.product_name}</td>
                      <td className="px-4 py-2.5 tabular-nums">{item.quantity ?? "-"}</td>
                      <td className="px-4 py-2.5 text-gray-500">{item.unit ?? "-"}</td>
                      <td className="px-4 py-2.5"><TempBadge zone={item.temperature_zone} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {order.source !== "手入力" && orderId && (
            <MessageThread key={orderId} orderId={orderId} />
          )}

          {order.remarks && (
            <div className="p-4 bg-amber-50/60 rounded-xl border border-amber-100">
              <p className="text-[11px] font-medium text-amber-600 uppercase tracking-wider mb-1">備考</p>
              <p className="text-sm text-amber-900">{order.remarks}</p>
            </div>
          )}
        </div>

        <div className="px-6 py-3 border-t border-gray-100 flex justify-end">
          <button onClick={onClose} className="btn-press px-4 py-2 text-sm text-gray-500 hover:text-gray-700 hover:bg-gray-50 rounded-lg transition-colors">
            閉じる
          </button>
        </div>
      </div>
    </div>
  );
}
