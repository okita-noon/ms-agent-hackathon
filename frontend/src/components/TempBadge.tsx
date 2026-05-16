const TEMP_CONFIG: Record<string, { cls: string; icon: string }> = {
  "冷凍": { cls: "bg-indigo-50 text-indigo-600 border-indigo-200", icon: "***" },
  "冷蔵": { cls: "bg-sky-50 text-sky-600 border-sky-200", icon: "***" },
  "常温": { cls: "bg-amber-50 text-amber-600 border-amber-200", icon: "***" },
};

export default function TempBadge({ zone }: { zone: string }) {
  const cfg = TEMP_CONFIG[zone] ?? { cls: "bg-gray-50 text-gray-600 border-gray-200", icon: "?" };
  return (
    <span className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded border text-[10px] font-medium ${cfg.cls}`}>
      {zone}
    </span>
  );
}
