import { useMemo, useState } from "react";
import {
  previewAgentResolution,
  type AgentExceptionCase,
  type AgentExceptionSeverity,
  type AgentExceptionType,
  type AgentResolutionPreview,
} from "../lib/api";

interface DashboardAgentPanelProps {
  exceptions: AgentExceptionCase[];
  loading: boolean;
  date: string;
  executeEnabled?: boolean;
}

const SEVERITY_STYLE: Record<AgentExceptionSeverity, string> = {
  high: "bg-red-50 text-red-700 border-red-100",
  medium: "bg-amber-50 text-amber-700 border-amber-100",
  low: "bg-slate-50 text-slate-600 border-slate-100",
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
  needs_review: "要対応",
  awaiting_reply: "返信待ち",
};

export default function DashboardAgentPanel({
  exceptions,
  loading,
  date,
  executeEnabled = false,
}: DashboardAgentPanelProps) {
  const [previewById, setPreviewById] = useState<Record<string, AgentResolutionPreview>>({});
  const [previewingId, setPreviewingId] = useState<string | null>(null);
  const [errorById, setErrorById] = useState<Record<string, string>>({});

  const counts = useMemo(() => {
    const high = exceptions.filter((c) => c.severity === "high").length;
    return { total: exceptions.length, high };
  }, [exceptions]);

  async function handlePreview(exceptionCase: AgentExceptionCase) {
    setPreviewingId(exceptionCase.id);
    setErrorById((prev) => {
      const next = { ...prev };
      delete next[exceptionCase.id];
      return next;
    });
    try {
      const resp = await previewAgentResolution(exceptionCase);
      if (resp.preview) {
        setPreviewById((prev) => ({ ...prev, [exceptionCase.id]: resp.preview! }));
      } else {
        setErrorById((prev) => ({
          ...prev,
          [exceptionCase.id]: "対応案の生成機能が無効です",
        }));
      }
    } catch {
      setErrorById((prev) => ({
        ...prev,
        [exceptionCase.id]: "プレビューの取得に失敗しました",
      }));
    } finally {
      setPreviewingId(null);
    }
  }

  return (
    <aside className="bg-white rounded-xl border border-gray-100 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-100 flex items-start gap-3">
        <img src="/favicon.png" alt="foogent" className="w-9 h-9 mt-0.5 shrink-0" />
        <div>
          <p className="text-[11px] font-semibold text-brand-600 uppercase tracking-wider">
            foogent AI
          </p>
          <h3 className="text-sm font-bold text-gray-900 mt-1">受注異常チェック</h3>
          <p className="text-[11px] text-gray-400 mt-0.5">
            {date} の配送分から担当者の判断が必要な受注を抽出
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 p-4 border-b border-gray-100">
        <div className="rounded-lg bg-gray-50 px-3 py-2">
          <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wider">未解決</p>
          <p className="text-xl font-bold text-gray-900 tabular-nums mt-1">{counts.total}</p>
        </div>
        <div className="rounded-lg bg-red-50 px-3 py-2">
          <p className="text-[10px] font-medium text-red-400 uppercase tracking-wider">高優先</p>
          <p className="text-xl font-bold text-red-700 tabular-nums mt-1">{counts.high}</p>
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
          <p className="text-xs text-gray-400 mt-1">通常どおり受注一覧をご確認ください</p>
        </div>
      ) : (
        <div className="p-3 space-y-3 max-h-[640px] overflow-y-auto">
          {exceptions.map((exceptionCase) => {
            const severityClass = SEVERITY_STYLE[exceptionCase.severity] ?? SEVERITY_STYLE.medium;
            const preview = previewById[exceptionCase.id];
            const isPreviewing = previewingId === exceptionCase.id;
            const errorMessage = errorById[exceptionCase.id];
            return (
              <article
                key={exceptionCase.id}
                className="rounded-lg border border-gray-100 bg-white p-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5 mb-2">
                      <span
                        className={`rounded-md border px-2 py-0.5 text-[10px] font-semibold ${severityClass}`}
                      >
                        {SEVERITY_LABEL[exceptionCase.severity] ?? exceptionCase.severity}
                      </span>
                      <span className="rounded-md bg-gray-50 border border-gray-100 px-2 py-0.5 text-[10px] font-semibold text-gray-500">
                        {TYPE_LABEL[exceptionCase.type] ?? exceptionCase.type}
                      </span>
                      <span className="text-[11px] font-medium text-gray-500 truncate">
                        {exceptionCase.customer_name}
                      </span>
                    </div>
                    <h4 className="text-sm font-semibold text-gray-900 leading-snug">
                      {exceptionCase.title}
                    </h4>
                    <p className="text-xs text-gray-500 leading-relaxed mt-1">
                      {exceptionCase.summary}
                    </p>
                  </div>
                  <span className="shrink-0 text-[10px] text-gray-400 tabular-nums">
                    #{exceptionCase.order_id}
                  </span>
                </div>

                {exceptionCase.evidence.length > 0 && (
                  <dl className="mt-3 grid grid-cols-2 gap-1.5">
                    {exceptionCase.evidence.slice(0, 4).map((evidence, index) => (
                      <div
                        key={`${evidence.label}-${index}`}
                        className="rounded-md bg-gray-50 px-2.5 py-2"
                      >
                        <dt className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                          {evidence.label}
                        </dt>
                        <dd className="text-xs text-gray-700 mt-0.5 leading-relaxed tabular-nums">
                          {evidence.value}
                        </dd>
                      </div>
                    ))}
                  </dl>
                )}

                {exceptionCase.suggested_action && (
                  <p className="mt-3 text-[11px] text-gray-500 leading-relaxed">
                    <span className="font-semibold text-gray-600">推奨:</span>{" "}
                    {exceptionCase.suggested_action}
                  </p>
                )}

                <button
                  type="button"
                  onClick={() => handlePreview(exceptionCase)}
                  disabled={isPreviewing}
                  className="btn-press mt-3 w-full rounded-lg border border-brand-100 bg-brand-50 px-3 py-2 text-xs font-semibold text-brand-700 hover:bg-brand-100 disabled:opacity-60 transition-colors flex items-center justify-center gap-2"
                >
                  <svg
                    className={`w-3.5 h-3.5 ${isPreviewing ? "animate-spin" : ""}`}
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
                  {isPreviewing ? "対応案を作成中..." : "対応案を確認する"}
                </button>

                {errorMessage && (
                  <p className="mt-2 text-[11px] text-red-500">{errorMessage}</p>
                )}

                {preview && (
                  <div className="mt-3 rounded-lg border border-brand-100 bg-brand-50/50 p-3 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs font-bold text-brand-800">{preview.title}</p>
                      <span className="text-[10px] font-semibold text-brand-600 tabular-nums">
                        信頼度 {Math.round(preview.confidence * 100)}%
                      </span>
                    </div>
                    <p className="text-xs text-gray-700 leading-relaxed">{preview.summary}</p>

                    {preview.recommended_actions.length > 0 && (
                      <ul className="space-y-1">
                        {preview.recommended_actions.map((action, index) => (
                          <li key={`${action}-${index}`} className="flex gap-2 text-xs text-gray-600">
                            <span className="mt-1 h-1.5 w-1.5 rounded-full bg-brand-500 shrink-0" />
                            <span>{action}</span>
                          </li>
                        ))}
                      </ul>
                    )}

                    {preview.customer_message && (
                      <div className="rounded-md bg-white border border-brand-100 px-2.5 py-2 text-xs text-gray-700 leading-relaxed whitespace-pre-wrap">
                        {preview.customer_message}
                      </div>
                    )}

                    <button
                      type="button"
                      disabled
                      title="顧客への自動送信は未実装です"
                      className="mt-1 w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs font-semibold text-gray-400 cursor-not-allowed flex items-center justify-center gap-2"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                      </svg>
                      送信（未実装）
                    </button>
                    <p className="text-[10px] text-gray-400">
                      {executeEnabled
                        ? "送信機能は次期実装予定です。現在は文面の下書きのみ作成します"
                        : "担当者が文面をコピーして手動で送信してください"}
                    </p>
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
