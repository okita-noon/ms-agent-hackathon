import { STATUS_COLORS } from "../lib/constants";

const ICON_PATHS: Record<string, string> = {
  未処理: "M12 6v6l4 2m6-2a10 10 0 11-20 0 10 10 0 0120 0z",
  要対応: "M12 9v4m0 4h.01M10.3 3.9L2.6 17.3A2 2 0 004.3 20h15.4a2 2 0 001.7-2.7L13.7 3.9a2 2 0 00-3.4 0z",
  製造: "M10.3 3.4l.5 2.1a7 7 0 012.4 0l.5-2.1 2.2.9-.9 2a7 7 0 011.7 1.7l2-.9.9 2.2-2.1.5a7 7 0 010 2.4l2.1.5-.9 2.2-2-.9a7 7 0 01-1.7 1.7l.9 2-2.2.9-.5-2.1a7 7 0 01-2.4 0l-.5 2.1-2.2-.9.9-2a7 7 0 01-1.7-1.7l-2 .9-.9-2.2 2.1-.5a7 7 0 010-2.4l-2.1-.5.9-2.2 2 .9A7 7 0 019 6.4l-.9-2 2.2-.9zM12 9a3 3 0 100 6 3 3 0 000-6z",
  配送: "M3 7h11v8H3V7zm11 3h3l3 3v2h-6v-5zM6.5 18a1.5 1.5 0 100-3 1.5 1.5 0 000 3zm11 0a1.5 1.5 0 100-3 1.5 1.5 0 000 3z",
  完了: "M9 12l2 2 4-5m6 3a9 9 0 11-18 0 9 9 0 0118 0z",
  キャンセル: "M15 9l-6 6m0-6l6 6m6-3a9 9 0 11-18 0 9 9 0 0118 0z",
  返信待ち: "M4 5h16v10H8l-4 4V5zm5 4h6m-6 3h4",
};

export function StatusIcon({ status, className = "h-3.5 w-3.5" }: { status: string; className?: string }) {
  const path = ICON_PATHS[status];
  if (!path) {
    return <span className={`inline-block rounded-full ${className}`} aria-hidden="true" />;
  }
  return (
    <svg className={`${className} shrink-0`} fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} viewBox="0 0 24 24" aria-hidden="true">
      <path d={path} />
    </svg>
  );
}

export default function StatusBadge({ status, responsive = false }: { status: string; responsive?: boolean }) {
  const sc = STATUS_COLORS[status] ?? { bg: "bg-gray-50", text: "text-gray-600", border: "border-gray-200" };
  return (
    <span
      className={`status-badge inline-flex max-w-full items-center justify-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold border whitespace-nowrap leading-none ${sc.bg} ${sc.text} ${sc.border}`}
      title={status}
      aria-label={status}
      data-responsive={responsive ? "true" : "false"}
    >
      <StatusIcon status={status} />
      <span className="status-badge-label">{status}</span>
    </span>
  );
}
