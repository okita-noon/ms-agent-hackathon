import { useMemo, useState } from "react";
import {
  previewAgentResolution,
  type AgentExceptionCase,
  type AgentResolutionPreview,
} from "../lib/api";

interface DashboardAgentPanelProps {
  exceptions: AgentExceptionCase[];
  loading: boolean;
  date: string;
}

const severityStyles: Record<string, string> = {
  critical: "bg-red-50 text-red-700 border-red-100",
  high: "bg-orange-50 text-orange-700 border-orange-100",
  medium: "bg-amber-50 text-amber-700 border-amber-100",
  low: "bg-slate-50 text-slate-600 border-slate-100",
};

function severityLabel(severity: string): string {
  switch (severity.toLowerCase()) {
    case "critical":
      return "最優先";
    case "high":
      return "高";
    case "medium":
      return "中";
    case "low":
      return "低";
    default:
      return severity;
  }
}

export default function DashboardAgentPanel({ exceptions, loading, date }: DashboardAgentPanelProps) {
  const [previewById, setPreviewById] = useState<Record<string, AgentResolutionPreview>>({});
  const [previewingId, setPreviewingId] = useState<string | null>(null);
  const [previewErrorId, setPreviewErrorId] = useState<string | null>(null);

  const counts = useMemo(() => {
    const urgent = exceptions.filter((item) => ["critical", "high"].includes(item.severity.toLowerCase())).length;
    return { total: exceptions.length, urgent };
  }, [exceptions]);

  async function handlePreview(exceptionCase: AgentExceptionCase) {
    setPreviewingId(exceptionCase.id);
    setPreviewErrorId(null);
    try {
      const preview = await previewAgentResolution(exceptionCase);
      setPreviewById((current) => ({ ...current, [exceptionCase.id]: preview }));
    } catch {
      setPreviewErrorId(exceptionCase.id);
    } finally {
      setPreviewingId(null);
    }
  }

  return (
    <aside className="bg-white rounded-xl border border-gray-100 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-100 flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold text-brand-600 uppercase tracking-wider">Dashboard Agent</p>
          <h3 className="text-sm font-bold text-gray-900 mt-1">Exception Triage Agent</h3>
          <p className="text-[11px] text-gray-400 mt-0.5">{date} の要対応候補を優先度順に集約</p>
        </div>
        <span className="inline-flex items-center rounded-lg border border-green-100 bg-green-50 px-2 py-1 text-[11px] font-semibold text-green-700">
          有効
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 p-4 border-b border-gray-100">
        <div className="rounded-lg bg-gray-50 px-3 py-2">
          <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wider">未解決</p>
          <p className="text-xl font-bold text-gray-900 tabular-nums mt-1">{counts.total}</p>
        </div>
        <div className="rounded-lg bg-red-50 px-3 py-2">
          <p className="text-[10px] font-medium text-red-400 uppercase tracking-wider">高優先</p>
          <p className="text-xl font-bold text-red-700 tabular-nums mt-1">{counts.urgent}</p>
        </div>
      </div>

      {loading ? (
        <div className="p-4 space-y-3">
          {[0, 1, 2].map((item) => (
            <div key={item} className="rounded-lg border border-gray-100 p-3">
              <div className="skeleton h-3 w-24 rounded mb-3" />
              <div className="skeleton h-4 w-4/5 rounded mb-2" />
              <div className="skeleton h-3 w-full rounded" />
            </div>
          ))}
        </div>
      ) : exceptions.length === 0 ? (
        <div className="px-4 py-10 text-center">
          <div className="w-10 h-10 mx-auto mb-3 rounded-full bg-green-50 flex items-center justify-center">
            <svg className="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <p className="text-sm font-medium text-gray-700">対応が必要な例外はありません</p>
          <p className="text-xs text-gray-400 mt-1">注文一覧は通常どおり確認できます</p>
        </div>
      ) : (
        <div className="p-3 space-y-3">
          {exceptions.map((exceptionCase) => {
            const severityClass = severityStyles[exceptionCase.severity.toLowerCase()] ?? severityStyles.medium;
            const preview = previewById[exceptionCase.id];
            const isPreviewing = previewingId === exceptionCase.id;
            return (
              <article key={exceptionCase.id} className="rounded-lg border border-gray-100 bg-white p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5 mb-2">
                      <span className={`rounded-md border px-2 py-0.5 text-[10px] font-semibold ${severityClass}`}>
                        {severityLabel(exceptionCase.severity)}
                      </span>
                      {exceptionCase.customer_name && (
                        <span className="text-[11px] font-medium text-gray-500 truncate">{exceptionCase.customer_name}</span>
                      )}
                    </div>
                    <h4 className="text-sm font-semibold text-gray-900 leading-snug">{exceptionCase.title}</h4>
                    {exceptionCase.summary && (
                      <p className="text-xs text-gray-500 leading-relaxed mt-1">{exceptionCase.summary}</p>
                    )}
                  </div>
                  {exceptionCase.order_id && (
                    <span className="shrink-0 text-[10px] text-gray-400 tabular-nums">#{exceptionCase.order_id}</span>
                  )}
                </div>

                {exceptionCase.evidence && exceptionCase.evidence.length > 0 && (
                  <div className="mt-3 space-y-1.5">
                    {exceptionCase.evidence.slice(0, 3).map((evidence, index) => (
                      <div key={`${evidence.label}-${index}`} className="rounded-md bg-gray-50 px-2.5 py-2">
                        <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">{evidence.label}</p>
                        <p className="text-xs text-gray-700 mt-0.5 leading-relaxed">{evidence.value}</p>
                      </div>
                    ))}
                  </div>
                )}

                <button
                  type="button"
                  onClick={() => handlePreview(exceptionCase)}
                  disabled={isPreviewing}
                  className="btn-press mt-3 w-full rounded-lg border border-brand-100 bg-brand-50 px-3 py-2 text-xs font-semibold text-brand-700 hover:bg-brand-100 disabled:opacity-60 transition-colors flex items-center justify-center gap-2"
                >
                  <svg className={`w-3.5 h-3.5 ${isPreviewing ? "animate-spin" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                  {isPreviewing ? "プレビュー生成中" : "Resolution Agent プレビュー"}
                </button>

                {previewErrorId === exceptionCase.id && (
                  <p className="mt-2 text-[11px] text-red-500">プレビューを取得できませんでした</p>
                )}

                {preview && (
                  <div className="mt-3 rounded-lg border border-brand-100 bg-brand-50/50 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs font-bold text-brand-800">{preview.title}</p>
                      {preview.confidence !== undefined && (
                        <span className="text-[10px] font-semibold text-brand-600 tabular-nums">
                          {Math.round(preview.confidence * 100)}%
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-700 leading-relaxed mt-2">{preview.summary}</p>
                    {preview.recommended_actions && preview.recommended_actions.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {preview.recommended_actions.slice(0, 3).map((action, index) => (
                          <li key={`${action}-${index}`} className="flex gap-2 text-xs text-gray-600">
                            <span className="mt-1 h-1.5 w-1.5 rounded-full bg-brand-500 shrink-0" />
                            <span>{action}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                    {preview.customer_message && (
                      <div className="mt-2 rounded-md bg-white px-2.5 py-2 text-xs text-gray-600 leading-relaxed">
                        {preview.customer_message}
                      </div>
                    )}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </aside>
  );
}
