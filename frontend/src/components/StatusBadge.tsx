import { STATUS_COLORS, normalizeStatus } from "../lib/constants";

export default function StatusBadge({ status }: { status: string }) {
  const normalized = normalizeStatus(status);
  const sc = STATUS_COLORS[normalized] ?? { bg: "bg-gray-50", text: "text-gray-600", border: "border-gray-200" };
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold border whitespace-nowrap leading-none ${sc.bg} ${sc.text} ${sc.border}`}>
      <span className={`w-1.5 h-1.5 shrink-0 rounded-full ${sc.text.replace("text-", "bg-")}`} />
      {normalized}
    </span>
  );
}
