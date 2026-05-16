import type { Order } from "../lib/api";
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

export default function OrderDetailModal({ order, onClose }: Props) {
  if (!order) return null;

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
              <p className="text-[11px] text-gray-400 font-mono">{order.uid || order.id}</p>
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
            <Field label="手配日" value={order.preparation_date || ""} />
            <Field label="配送日" value={order.delivery_date || ""} />
            <Field label="チャネル" value={order.source} />
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
