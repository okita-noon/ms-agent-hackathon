/**
 * 受注詳細の共通コンテンツ。
 * OrderDetailModal と ExceptionModal の右ペインで再利用する。
 */
import { useEffect, useRef, useState } from "react";
import type {
  AgentExceptionCase,
  AgentExceptionSeverity,
  AgentResolutionPreview,
  Message,
  Order,
} from "../lib/api";
import { fetchOrderMessages, previewAgentResolution, updateOrderMemo, updateOrderStatus } from "../lib/api";
import { SOURCE_COLORS } from "../lib/constants";
import StatusBadge from "./StatusBadge";
import TempBadge from "./TempBadge";

/* ── severity maps ───────────────────────────────────── */

const SEVERITY_DETAIL: Record<
  AgentExceptionSeverity,
  { border: string; bg: string; icon: string; title: string; text: string }
> = {
  high: { border: "border-red-200", bg: "bg-red-50/60", icon: "text-red-500", title: "text-red-800", text: "text-red-700" },
  medium: { border: "border-amber-200", bg: "bg-amber-50/60", icon: "text-amber-500", title: "text-amber-800", text: "text-amber-700" },
  low: { border: "border-slate-200", bg: "bg-slate-50/60", icon: "text-slate-500", title: "text-slate-700", text: "text-slate-600" },
};

const SEVERITY_LABEL: Record<AgentExceptionSeverity, string> = { high: "高", medium: "中", low: "低" };

const TYPE_LABEL: Record<string, string> = {
  quantity_anomaly: "数量異常",
  unit_anomaly: "単位異常",
  inventory_shortage: "在庫不足",
  needs_review: "要確認",
  awaiting_reply: "返信待ち",
};

/* ── sub-components ──────────────────────────────────── */

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
    return d.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Tokyo" });
  } catch {
    return "";
  }
}

function formatMessageText(text: string | undefined | null, channel: string): string {
  if (!text) return "";
  let cleanText = text;

  if (channel === "email") {
    // Remove HTML comments (e.g. <!-- ... -->)
    cleanText = cleanText.replace(/<!--[\s\S]*?-->/g, "");

    // Normalize newlines
    cleanText = cleanText.replace(/\r\n/g, "\n").replace(/\r/g, "\n");

    // Add newlines before headers if not already preceded by a newline or start of string.
    const headerRegex = /(差出人|送信日時|宛先|件名|From|To|Sent|Subject|Date)\s*(:|：)\s*/gi;
    cleanText = cleanText.replace(headerRegex, (_match, p1, p2, offset, string) => {
      let isAtStartOfLine = offset === 0;
      if (offset > 0) {
        let i = offset - 1;
        while (i >= 0 && (string[i] === " " || string[i] === "\t")) {
          i--;
        }
        if (i < 0 || string[i] === "\n") {
          isAtStartOfLine = true;
        }
      }
      return isAtStartOfLine ? `${p1}${p2} ` : `\n${p1}${p2} `;
    });
  }

  return cleanText.trim().replace(/\n{3,}/g, "\n\n");
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

function MemoEditor({
  orderId,
  initialMemo,
  onSaved,
}: {
  orderId: string;
  initialMemo: string;
  onSaved?: (order: Order) => void;
}) {
  const [memo, setMemo] = useState(initialMemo);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dirty = memo !== initialMemo;

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateOrderMemo(orderId, memo.trim() || null);
      onSaved?.(updated);
    } catch {
      setError("メモの保存に失敗しました。時間を置いて再度お試しください。");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h5 className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">
          メモ（アレルギー対応・特別包装など）
        </h5>
        {dirty && !saving && (
          <span className="text-[11px] text-amber-600">未保存の変更があります</span>
        )}
      </div>
      <textarea
        value={memo}
        onChange={(e) => setMemo(e.target.value)}
        placeholder="特殊な対応事項があれば記録してください（例：ギフト包装、アレルギー対応など）"
        rows={3}
        className="input-field w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none bg-white resize-none focus:border-brand-400 focus:ring-1 focus:ring-brand-200"
      />
      {error && <p className="mt-1 text-xs text-rose-600">{error}</p>}
      <div className="mt-2 flex justify-end">
        <button
          type="button"
          onClick={handleSave}
          disabled={!dirty || saving}
          className="btn-press inline-flex items-center gap-1 rounded-lg bg-brand-600 hover:bg-brand-700 text-white px-3 py-1.5 text-xs font-medium disabled:opacity-50 transition-colors"
        >
          {saving ? "保存中..." : "メモを保存"}
        </button>
      </div>
    </div>
  );
}

function MessageThread({ orderId, order }: { orderId: string; order?: Order }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchOrderMessages(orderId, order)
      .then((data) => {
        if (!cancelled) setMessages(data.messages);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
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
        {messages.map((msg) => {
          const isCustomer = msg.role === "user";
          const alignRight = !isCustomer;
          return (
            <div key={msg.id} className={`flex ${alignRight ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-2.5 ${
                  alignRight
                    ? "bg-brand-50 border border-brand-100 rounded-tr-md"
                    : "bg-white border border-gray-200 rounded-tl-md"
                }`}
              >
                <p className="text-sm text-gray-800 whitespace-pre-wrap">{formatMessageText(msg.text, channel)}</p>
                <p className={`text-[10px] mt-1 ${alignRight ? "text-brand-400" : "text-gray-400"}`}>
                  {isCustomer ? (channel === "phone" ? "発注側" : "お客様") : "受注側"} ・ {formatTime(msg.created_at)}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── Exception section ───────────────────────────────── */

export function ExceptionSection({ exceptions }: { exceptions: AgentExceptionCase[] }) {
  const [previewById, setPreviewById] = useState<Record<string, AgentResolutionPreview>>({});
  const [previewingId, setPreviewingId] = useState<string | null>(null);

  async function handlePreview(exc: AgentExceptionCase) {
    setPreviewingId(exc.id);
    try {
      const resp = await previewAgentResolution(exc);
      if (resp.preview) {
        setPreviewById((prev) => ({ ...prev, [exc.id]: resp.preview! }));
      }
    } catch { /* ignore */ }
    finally { setPreviewingId(null); }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <img src="/favicon.png" alt="" className="w-4 h-4" />
        <h5 className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">AI検知</h5>
      </div>
      {exceptions.map((exc) => {
        const sc = SEVERITY_DETAIL[exc.severity];
        const preview = previewById[exc.id];
        return (
          <div key={exc.id} className={`rounded-xl border-2 ${sc.border} ${sc.bg} p-4 space-y-3`}>
            <div className="flex items-start gap-2">
              <svg className={`w-5 h-5 ${sc.icon} shrink-0 mt-0.5`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-bold ${sc.border} ${sc.title}`}>
                    {SEVERITY_LABEL[exc.severity]}
                  </span>
                  <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold ${sc.title}`}>
                    {TYPE_LABEL[exc.type] ?? exc.type}
                  </span>
                </div>
                <p className={`text-sm font-bold ${sc.title}`}>{exc.title}</p>
                <p className={`text-sm ${sc.text} mt-1 leading-relaxed`}>{exc.summary}</p>
                {exc.evidence.length > 0 && (
                  <div className={`mt-2 text-sm ${sc.text}`}>
                    {exc.evidence.map((ev, i) => (
                      <span key={i}>{i > 0 && "、"}{ev.label}: <strong>{ev.value}</strong></span>
                    ))}
                  </div>
                )}
              </div>
            </div>
            {preview ? (
              <div className="ml-7 space-y-2">
                <ul className="space-y-1">
                  {preview.recommended_actions.map((action, i) => (
                    <li key={i} className="flex gap-2 text-sm text-gray-700">
                      <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-brand-500 shrink-0" />
                      <span>{action}</span>
                    </li>
                  ))}
                </ul>
                {preview.customer_message && (
                  <div className="rounded-lg bg-white/80 border border-gray-200 px-3 py-2 text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
                    {preview.customer_message}
                  </div>
                )}
              </div>
            ) : exc.suggested_action ? (
              <div className="ml-7 space-y-2">
                <p className="text-sm text-gray-700">{exc.suggested_action}</p>
                <button
                  type="button"
                  onClick={() => handlePreview(exc)}
                  disabled={previewingId === exc.id}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-brand-200 bg-white px-2.5 py-1.5 text-[11px] font-semibold text-brand-700 hover:bg-brand-50 disabled:opacity-60 transition-colors"
                >
                  <svg className={`w-3 h-3 ${previewingId === exc.id ? "animate-spin" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                  {previewingId === exc.id ? "生成中..." : "AIに対応案を確認"}
                </button>
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

/* ── Main exported content ───────────────────────────── */

export interface OrderDetailContentProps {
  order: Order;
  exceptions?: AgentExceptionCase[];
  onMemoUpdated?: (order: Order) => void;
  /**
   * 「対応済みにする」ボタンを非表示にする（ExceptionModal が footer で同等のアクションを
   * 提供する場合に true）。デフォルト false。
   */
  hideResolveAction?: boolean;
  onWillResolve?: (orderId: string) => void;
}

export default function OrderDetailContent({ order, exceptions, onMemoUpdated, hideResolveAction = false, onWillResolve }: OrderDetailContentProps) {
  const orderId = order.uid || order.id || "";
  const orderExceptions = exceptions?.filter((e) => e.order_id === orderId) ?? [];

  // 「対応済みにする」2タップ式: 1タップ目で confirm 状態に入り、3秒以内の 2タップ目で確定
  const [resolveConfirm, setResolveConfirm] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [resolveError, setResolveError] = useState<string | null>(null);
  const confirmTimerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (confirmTimerRef.current !== null) window.clearTimeout(confirmTimerRef.current);
    };
  }, []);

  // 対象注文が変わったら confirm 状態をリセット
  useEffect(() => {
    setResolveConfirm(false);
    setResolveError(null);
  }, [orderId]);

  function armResolveConfirm() {
    setResolveError(null);
    setResolveConfirm(true);
    if (confirmTimerRef.current !== null) window.clearTimeout(confirmTimerRef.current);
    confirmTimerRef.current = window.setTimeout(() => {
      setResolveConfirm(false);
      confirmTimerRef.current = null;
    }, 3000);
  }

  async function handleResolve() {
    if (confirmTimerRef.current !== null) {
      window.clearTimeout(confirmTimerRef.current);
      confirmTimerRef.current = null;
    }
    onWillResolve?.(orderId);
    setResolving(true);
    setResolveError(null);
    try {
      const updated = await updateOrderStatus(orderId, "受注済み");
      onMemoUpdated?.(updated);
      setResolveConfirm(false);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "対応済み更新に失敗しました";
      setResolveError(msg);
    } finally {
      setResolving(false);
    }
  }

  const showResolveButton = !hideResolveAction && order.status === "要対応" && !!orderId;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="text-lg font-bold text-gray-900 truncate">{order.customer_name}</h4>
          <span className="text-xs font-semibold" style={{ color: SOURCE_COLORS[order.source] ?? "#64748b" }}>{order.source}</span>
        </div>
        <div className="flex flex-col items-end gap-1.5 shrink-0">
          <StatusBadge status={order.status} />
          {showResolveButton && (
            resolveConfirm ? (
              <button
                type="button"
                disabled={resolving}
                onClick={handleResolve}
                className="btn-press inline-flex items-center gap-1 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white px-2 py-1 text-[11px] font-medium transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                {resolving ? "更新中…" : "もう一度押して確定"}
              </button>
            ) : (
              <button
                type="button"
                disabled={resolving}
                onClick={armResolveConfirm}
                className="btn-press inline-flex items-center gap-1 rounded-md border border-emerald-200 bg-white hover:bg-emerald-50 text-emerald-700 px-2 py-1 text-[11px] font-medium transition-colors disabled:opacity-60"
                title="要対応タグを外し、受注済みに変更します"
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                対応済みにする
              </button>
            )
          )}
          {resolveError && (
            <p className="text-[11px] text-red-600 max-w-[180px] text-right" role="alert">
              {resolveError}
            </p>
          )}
        </div>
      </div>

      {orderExceptions.length > 0 && (
        <ExceptionSection exceptions={orderExceptions} />
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-4 bg-gray-50/80 rounded-xl">
        <Field label="受注日" value={order.order_date || ""} />
        <Field label="最終処理" value={order.updated_at ? formatTime(order.updated_at) : ""} />
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

      {orderId && <MessageThread key={orderId} orderId={orderId} order={order} />}

      {order.remarks && (
        <div className="p-4 bg-amber-50/60 rounded-xl border border-amber-100">
          <p className="text-[11px] font-medium text-amber-600 uppercase tracking-wider mb-1">備考</p>
          <p className="text-sm text-amber-900">{order.remarks}</p>
        </div>
      )}

      {orderId && (
        <MemoEditor
          key={`memo-${orderId}`}
          orderId={orderId}
          initialMemo={order.memo || ""}
          onSaved={onMemoUpdated}
        />
      )}
    </div>
  );
}
