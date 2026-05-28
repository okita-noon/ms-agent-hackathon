import { useEffect, useState } from "react";

export interface ToastItem {
  id: string;
  order_id: string;
  customer_name?: string;
  source?: string;
  order_date?: string;
  type: "created" | "updated";
}

const SOURCE_ICON: Record<string, string> = {
  line: "💬",
  phone: "📞",
  email: "📧",
  web: "🌐",
};

function formatToastTime(value?: string): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Tokyo" });
}

function SingleToast({ toast, onDismiss }: { toast: ToastItem; onDismiss: (id: string) => void }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // trigger enter animation
    const enterTimer = window.setTimeout(() => setVisible(true), 10);
    // start exit animation slightly before removal
    const exitTimer = window.setTimeout(() => setVisible(false), 4400);
    return () => {
      clearTimeout(enterTimer);
      clearTimeout(exitTimer);
    };
  }, []);

  const icon = SOURCE_ICON[toast.source ?? ""] ?? "📦";
  const time = formatToastTime(toast.order_date);
  const isNew = toast.type === "created";

  return (
    <div
      className={`toast-item flex items-start gap-3 rounded-xl border border-green-200 bg-white shadow-lg shadow-green-100/60 px-4 py-3 min-w-[260px] max-w-xs transition-all duration-300 ${
        visible ? "opacity-100 translate-x-0" : "opacity-0 translate-x-8"
      }`}
    >
      {/* Left accent */}
      <div className="shrink-0 flex flex-col items-center gap-1 pt-0.5">
        <span className="text-xl leading-none">{icon}</span>
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 mb-0.5">
          <span
            className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[9px] font-extrabold tracking-wide uppercase ${
              isNew
                ? "bg-green-500 text-white"
                : "bg-amber-400 text-white"
            }`}
          >
            {isNew ? "NEW" : "更新"}
          </span>
          <span className="text-[10px] text-gray-400 tabular-nums">{time}</span>
        </div>
        <p className="text-sm font-bold text-gray-900 truncate">
          {toast.customer_name ?? "不明な顧客"}
        </p>
        <p className="text-xs text-gray-500 mt-0.5">
          {isNew ? "受注が登録されました" : "受注が更新されました"}
        </p>
      </div>

      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        className="shrink-0 text-gray-300 hover:text-gray-500 transition-colors mt-0.5"
        aria-label="閉じる"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      {/* Progress bar */}
      <div className="absolute bottom-0 left-0 right-0 h-0.5 rounded-b-xl bg-green-100 overflow-hidden">
        <div className="h-full bg-green-400 animate-toast-progress" />
      </div>
    </div>
  );
}

export default function NewOrderToast({
  toasts,
  onDismiss,
}: {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
}) {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col-reverse gap-2 pointer-events-none">
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto relative">
          <SingleToast toast={t} onDismiss={onDismiss} />
        </div>
      ))}
    </div>
  );
}
