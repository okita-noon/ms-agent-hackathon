export const STATUS_COLORS: Record<string, { bg: string; text: string; chart: string; border: string }> = {
  "未処理": { bg: "bg-amber-50", text: "text-amber-700", chart: "#f59e0b", border: "border-amber-200" },
  "要対応": { bg: "bg-rose-50", text: "text-rose-700", chart: "#e11d48", border: "border-rose-200" },
  "製造": { bg: "bg-blue-50", text: "text-blue-700", chart: "#3b82f6", border: "border-blue-200" },
  "配送": { bg: "bg-orange-50", text: "text-orange-700", chart: "#f97316", border: "border-orange-200" },
  "完了": { bg: "bg-emerald-50", text: "text-emerald-700", chart: "#10b981", border: "border-emerald-200" },
  "キャンセル": { bg: "bg-gray-50", text: "text-gray-500", chart: "#9ca3af", border: "border-gray-200" },
  "返信待ち": { bg: "bg-rose-50", text: "text-rose-700", chart: "#f43f5e", border: "border-rose-200" },
};

export const ACCEPTED_ORDER_STATUSES = new Set(["未処理", "製造", "配送", "完了"]);

export const SOURCE_COLORS: Record<string, string> = {
  LINE: "#06c755",
  Phone: "#3366ff",
  Email: "#8b5cf6",
  FAX: "#78716c",
  Web: "#f59e42",
  "手入力": "#64748b",
};

export const SOURCE_BADGE_CONFIG: Record<string, { bg: string; text: string; border: string; icon: string }> = {
  "LINE":   { bg: "bg-green-50",  text: "text-green-700",  border: "border-green-200",  icon: "line" },
  "Phone":  { bg: "bg-blue-50",   text: "text-blue-700",   border: "border-blue-200",   icon: "phone" },
  "Email":  { bg: "bg-purple-50", text: "text-purple-700", border: "border-purple-200",  icon: "mail" },
  "FAX":    { bg: "bg-stone-50",  text: "text-stone-600",  border: "border-stone-200",   icon: "document" },
  "Web":    { bg: "bg-amber-50",  text: "text-amber-700",  border: "border-amber-200",   icon: "globe" },
  "手入力": { bg: "bg-slate-50",  text: "text-slate-700",  border: "border-slate-200",   icon: "clipboard" },
};
