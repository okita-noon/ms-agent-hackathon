import { useState, useRef, useEffect, type FormEvent, type KeyboardEvent } from "react";
import {
  phoneDebugSendMessage,
  phoneDebugDisconnect,
  type PhoneDebugResponse,
} from "../lib/api";

interface Turn {
  role: "user" | "assistant" | "system";
  text: string;
  raw?: PhoneDebugResponse;
  ts: string;
}

const DEFAULT_CALLER = "+81312345678";
const DEFAULT_CALLED = "+81501234567";

function ts() {
  return new Date().toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function PhoneDebug() {
  const [callerNumber, setCallerNumber] = useState(DEFAULT_CALLER);
  const [calledNumber, setCalledNumber] = useState(DEFAULT_CALLED);
  const [callConnectionId, setCallConnectionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedRaw, setExpandedRaw] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const isActive = callConnectionId !== null;

  function addSystemTurn(text: string) {
    setTurns((prev) => [...prev, { role: "system", text, ts: ts() }]);
  }

  async function sendMessage(messageText: string) {
    if (!messageText.trim() || loading) return;
    setError(null);
    setLoading(true);

    const userTurn: Turn = { role: "user", text: messageText.trim(), ts: ts() };
    setTurns((prev) => [...prev, userTurn]);
    setInput("");

    try {
      const res = await phoneDebugSendMessage({
        message: messageText.trim(),
        caller_number: callerNumber,
        called_number: calledNumber,
        call_connection_id: callConnectionId ?? undefined,
      });

      if (!callConnectionId && res.call_connection_id) {
        setCallConnectionId(res.call_connection_id);
        addSystemTurn(`通話開始 — Call ID: ${res.call_connection_id}`);
      }

      const assistantText = res.response || (res.error ? `[エラー] ${res.error}` : "[応答なし]");
      const assistantTurn: Turn = {
        role: "assistant",
        text: assistantText,
        raw: res,
        ts: ts(),
      };
      setTurns((prev) => [...prev, assistantTurn]);

      if (res.order_id) {
        addSystemTurn(`受注確定 — 受注ID: ${res.order_id}`);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setTurns((prev) => [
        ...prev,
        { role: "system", text: `送信エラー: ${msg}`, ts: ts() },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function handleDisconnect() {
    if (!callConnectionId || loading) return;
    setLoading(true);
    setError(null);
    try {
      await phoneDebugDisconnect(callConnectionId);
      addSystemTurn(`通話終了 — Call ID: ${callConnectionId}`);
      setCallConnectionId(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    setCallConnectionId(null);
    setTurns([]);
    setInput("");
    setError(null);
    setExpandedRaw(null);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    sendMessage(input);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  }

  const QUICK_MESSAGES = [
    "りんご10箱お願いします",
    "バナナ20kgとみかん50個",
    "いつものお願い",
    "在庫確認したい",
    "キャンセルしたい",
  ];

  return (
    <div className="flex flex-col h-[calc(100vh-120px)] max-w-4xl">
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-gray-900">電話発注デバッグ</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          電話チャネルの音声認識済みテキストを直接注入してAI処理をテストします
        </p>
      </div>

      {/* 設定パネル */}
      <div className="bg-white border border-gray-200 rounded-xl p-4 mb-4">
        <div className="flex flex-wrap gap-4 items-end">
          <div className="flex-1 min-w-40">
            <label className="block text-xs font-medium text-gray-600 mb-1">発信者番号（顧客）</label>
            <input
              type="text"
              value={callerNumber}
              onChange={(e) => setCallerNumber(e.target.value)}
              disabled={isActive}
              className="w-full text-sm border border-gray-300 rounded-lg px-3 py-1.5 font-mono disabled:bg-gray-50 disabled:text-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
              placeholder="+81312345678"
            />
          </div>
          <div className="flex-1 min-w-40">
            <label className="block text-xs font-medium text-gray-600 mb-1">着信番号（自社）</label>
            <input
              type="text"
              value={calledNumber}
              onChange={(e) => setCalledNumber(e.target.value)}
              disabled={isActive}
              className="w-full text-sm border border-gray-300 rounded-lg px-3 py-1.5 font-mono disabled:bg-gray-50 disabled:text-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
              placeholder="+81501234567"
            />
          </div>
          <div className="flex gap-2">
            {isActive ? (
              <button
                onClick={handleDisconnect}
                disabled={loading}
                className="px-4 py-1.5 text-sm font-medium rounded-lg bg-red-50 text-red-700 border border-red-200 hover:bg-red-100 disabled:opacity-50 transition-colors"
              >
                通話切断
              </button>
            ) : null}
            <button
              onClick={handleReset}
              disabled={loading}
              className="px-4 py-1.5 text-sm font-medium rounded-lg bg-gray-100 text-gray-700 hover:bg-gray-200 disabled:opacity-50 transition-colors"
            >
              リセット
            </button>
          </div>
        </div>

        {/* ステータスバー */}
        <div className="mt-3 flex items-center gap-3 text-xs">
          <span
            className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full font-medium ${
              isActive
                ? "bg-green-100 text-green-700"
                : "bg-gray-100 text-gray-500"
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${isActive ? "bg-green-500 animate-pulse" : "bg-gray-400"}`}
            />
            {isActive ? "通話中" : "待機中"}
          </span>
          {callConnectionId && (
            <span className="text-gray-400 font-mono truncate max-w-xs">
              ID: {callConnectionId}
            </span>
          )}
          <span className="text-gray-400">{turns.filter((t) => t.role === "user").length} ターン</span>
        </div>
      </div>

      {/* 会話ログ */}
      <div className="flex-1 overflow-y-auto bg-white border border-gray-200 rounded-xl p-4 space-y-3 mb-4">
        {turns.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-2">
            <svg className="w-10 h-10 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
            </svg>
            <p className="text-sm">メッセージを入力すると通話デバッグが始まります</p>
          </div>
        )}

        {turns.map((turn, i) => (
          <div key={i}>
            {turn.role === "system" ? (
              <div className="flex justify-center">
                <span className="text-xs text-gray-400 bg-gray-50 px-3 py-1 rounded-full border border-gray-200">
                  {turn.ts} — {turn.text}
                </span>
              </div>
            ) : turn.role === "user" ? (
              <div className="flex justify-end">
                <div className="max-w-[70%]">
                  <div className="text-xs text-gray-400 text-right mb-1">{turn.ts} · 発信者</div>
                  <div className="bg-brand-600 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed">
                    {turn.text}
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex justify-start">
                <div className="max-w-[70%]">
                  <div className="text-xs text-gray-400 mb-1">{turn.ts} · AI応答</div>
                  <div className="bg-gray-100 text-gray-900 rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm leading-relaxed">
                    {turn.text}
                  </div>
                  {turn.raw && (
                    <div className="mt-1.5">
                      <button
                        onClick={() => setExpandedRaw(expandedRaw === i ? null : i)}
                        className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1"
                      >
                        <svg
                          className={`w-3 h-3 transition-transform ${expandedRaw === i ? "rotate-90" : ""}`}
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                        レスポンス詳細
                        {turn.raw.order_id && (
                          <span className="ml-1 bg-green-100 text-green-700 px-1.5 py-0.5 rounded text-xs font-medium">
                            受注: {turn.raw.order_id}
                          </span>
                        )}
                        {turn.raw.session_status && (
                          <span className="ml-1 bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded text-xs font-medium">
                            {turn.raw.session_status}
                          </span>
                        )}
                      </button>
                      {expandedRaw === i && (
                        <pre className="mt-1 text-xs bg-gray-900 text-green-400 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-all">
                          {JSON.stringify(turn.raw, null, 2)}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-2xl rounded-tl-sm px-4 py-3">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0ms]" />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:150ms]" />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:300ms]" />
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* クイックメッセージ */}
      <div className="flex flex-wrap gap-2 mb-3">
        {QUICK_MESSAGES.map((msg) => (
          <button
            key={msg}
            onClick={() => sendMessage(msg)}
            disabled={loading}
            className="text-xs px-3 py-1 rounded-full border border-gray-300 text-gray-600 hover:bg-gray-50 hover:border-gray-400 disabled:opacity-40 transition-colors"
          >
            {msg}
          </button>
        ))}
      </div>

      {/* 入力フォーム */}
      {error && (
        <div className="mb-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          {error}
        </div>
      )}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          rows={2}
          placeholder="音声認識テキストを入力（Enter で送信、Shift+Enter で改行）"
          className="flex-1 text-sm border border-gray-300 rounded-xl px-4 py-2.5 resize-none focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:bg-gray-50"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="px-5 py-2.5 text-sm font-medium rounded-xl bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors self-end"
        >
          送信
        </button>
      </form>
    </div>
  );
}
