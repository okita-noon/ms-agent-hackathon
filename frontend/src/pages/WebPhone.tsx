import {
  useState,
  useRef,
  useEffect,
  useCallback,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import {
  webPhoneSendMessage,
  webPhoneDisconnect,
  type WebPhoneResponse,
} from "../lib/api";

interface Turn {
  role: "user" | "assistant" | "system";
  text: string;
  raw?: WebPhoneResponse;
  ts: string;
}

const DEFAULT_CALLER = "+81312345678";
const DEFAULT_CALLED = "+81501234567";
const VOICEVOX_BASE = (
  import.meta.env.VITE_VOICEVOX_URL || "/voicevox"
).replace(/\/$/, "");
const ZUNDAMON_SPEAKER = 3;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const SpeechRecognitionCtor: (new () => SpeechRecognition) | undefined =
  typeof window !== "undefined"
    ? (window.SpeechRecognition ??
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (window as any).webkitSpeechRecognition)
    : undefined;

function now() {
  return new Date().toLocaleTimeString("ja-JP", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function WebPhone() {
  const [callerNumber, setCallerNumber] = useState(DEFAULT_CALLER);
  const [calledNumber, setCalledNumber] = useState(DEFAULT_CALLED);
  const [callConnectionId, setCallConnectionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedRaw, setExpandedRaw] = useState<number | null>(null);

  const [isComposing, setIsComposing] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [voicevoxOk, setVoicevoxOk] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const inputBeforeSpeechRef = useRef("");

  const isActive = callConnectionId !== null;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  useEffect(() => {
    fetch(`${VOICEVOX_BASE}/version`)
      .then((r) => {
        if (r.ok) setVoicevoxOk(true);
      })
      .catch(() => {});
  }, []);

  /* ── TTS ── */

  const stopSpeaking = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current = null;
    }
    if ("speechSynthesis" in window) speechSynthesis.cancel();
    setIsSpeaking(false);
  }, []);

  const speakText = useCallback(
    async (text: string) => {
      if (!ttsEnabled) return;
      stopSpeaking();
      setIsSpeaking(true);

      if (voicevoxOk) {
        try {
          const qr = await fetch(
            `${VOICEVOX_BASE}/audio_query?text=${encodeURIComponent(text)}&speaker=${ZUNDAMON_SPEAKER}`,
            { method: "POST" },
          );
          if (qr.ok) {
            const query = await qr.json();
            const sr = await fetch(
              `${VOICEVOX_BASE}/synthesis?speaker=${ZUNDAMON_SPEAKER}`,
              {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(query),
              },
            );
            if (sr.ok) {
              const blob = await sr.blob();
              const url = URL.createObjectURL(blob);
              const audio = new Audio(url);
              audioRef.current = audio;
              const cleanup = () => {
                setIsSpeaking(false);
                URL.revokeObjectURL(url);
                if (audioRef.current === audio) audioRef.current = null;
              };
              audio.onended = cleanup;
              audio.onerror = cleanup;
              await audio.play();
              return;
            }
          }
        } catch {
          /* fall through to browser TTS */
        }
      }

      if ("speechSynthesis" in window) {
        const utt = new SpeechSynthesisUtterance(text);
        utt.lang = "ja-JP";
        utt.onend = () => setIsSpeaking(false);
        utt.onerror = () => setIsSpeaking(false);
        speechSynthesis.speak(utt);
      } else {
        setIsSpeaking(false);
      }
    },
    [ttsEnabled, voicevoxOk, stopSpeaking],
  );

  /* ── Speech Recognition ── */

  const toggleListening = useCallback(() => {
    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
      return;
    }
    if (!SpeechRecognitionCtor) return;
    stopSpeaking();
    inputBeforeSpeechRef.current = input;

    const recog = new SpeechRecognitionCtor();
    recog.lang = "ja-JP";
    recog.interimResults = true;
    recog.continuous = false;
    recog.maxAlternatives = 1;

    recog.onresult = (ev: SpeechRecognitionEvent) => {
      let transcript = "";
      for (let i = 0; i < ev.results.length; i++) {
        transcript += ev.results[i][0].transcript;
      }
      setInput(inputBeforeSpeechRef.current + transcript);
    };
    recog.onend = () => setIsListening(false);
    recog.onerror = () => setIsListening(false);

    recognitionRef.current = recog;
    recog.start();
    setIsListening(true);
  }, [isListening, input, stopSpeaking]);

  /* ── Helpers ── */

  function addSystemTurn(text: string) {
    setTurns((prev) => [...prev, { role: "system", text, ts: now() }]);
  }

  async function sendMessage(messageText: string) {
    if (!messageText.trim() || loading) return;
    setError(null);
    setLoading(true);
    setTurns((prev) => [
      ...prev,
      { role: "user", text: messageText.trim(), ts: now() },
    ]);
    setInput("");

    try {
      const res = await webPhoneSendMessage({
        message: messageText.trim(),
        caller_number: callerNumber,
        called_number: calledNumber,
        call_connection_id: callConnectionId ?? undefined,
      });

      if (!callConnectionId && res.call_connection_id) {
        setCallConnectionId(res.call_connection_id);
        addSystemTurn(`通話開始 — Call ID: ${res.call_connection_id}`);
      }

      const text =
        res.response || (res.error ? `[エラー] ${res.error}` : "[応答なし]");
      setTurns((prev) => [
        ...prev,
        { role: "assistant", text, raw: res, ts: now() },
      ]);

      if (res.order_id) addSystemTurn(`受注確定 — 受注ID: ${res.order_id}`);
      if (text && !text.startsWith("[")) speakText(text);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setTurns((prev) => [
        ...prev,
        { role: "system", text: `送信エラー: ${msg}`, ts: now() },
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
      await webPhoneDisconnect(callConnectionId);
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
    stopSpeaking();
    if (isListening) recognitionRef.current?.stop();
    setCallConnectionId(null);
    setTurns([]);
    setInput("");
    setError(null);
    setExpandedRaw(null);
    setIsListening(false);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    sendMessage(input);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      e.key === "Enter" &&
      !e.shiftKey &&
      !isComposing &&
      !e.nativeEvent.isComposing
    ) {
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
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900 flex items-center gap-2">
            <svg
              className="w-6 h-6 text-brand-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.8}
                d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z"
              />
            </svg>
            Web 電話
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            音声またはテキストで電話発注をシミュレーションします
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              setTtsEnabled((v) => !v);
              if (ttsEnabled) stopSpeaking();
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
              ttsEnabled
                ? "bg-green-50 text-green-700 border-green-200 hover:bg-green-100"
                : "bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100"
            }`}
            title={ttsEnabled ? "音声読み上げON" : "音声読み上げOFF"}
          >
            {ttsEnabled ? (
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z"
                />
              </svg>
            ) : (
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z"
                />
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2"
                />
              </svg>
            )}
            {voicevoxOk ? "ずんだもん" : "ブラウザ"}
          </button>
          <button
            onClick={() => setShowSettings((v) => !v)}
            className="px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors"
          >
            設定
          </button>
        </div>
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div className="bg-white border border-gray-200 rounded-xl p-4 mb-4">
          <div className="flex flex-wrap gap-4 items-end">
            <div className="flex-1 min-w-40">
              <label className="block text-xs font-medium text-gray-600 mb-1">
                発信者番号（顧客）
              </label>
              <input
                type="text"
                value={callerNumber}
                onChange={(e) => setCallerNumber(e.target.value)}
                disabled={isActive}
                className="w-full text-sm border border-gray-300 rounded-lg px-3 py-1.5 font-mono disabled:bg-gray-50 disabled:text-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div className="flex-1 min-w-40">
              <label className="block text-xs font-medium text-gray-600 mb-1">
                着信番号（自社）
              </label>
              <input
                type="text"
                value={calledNumber}
                onChange={(e) => setCalledNumber(e.target.value)}
                disabled={isActive}
                className="w-full text-sm border border-gray-300 rounded-lg px-3 py-1.5 font-mono disabled:bg-gray-50 disabled:text-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div className="flex gap-2">
              {isActive && (
                <button
                  onClick={handleDisconnect}
                  disabled={loading}
                  className="px-4 py-1.5 text-sm font-medium rounded-lg bg-red-50 text-red-700 border border-red-200 hover:bg-red-100 disabled:opacity-50 transition-colors"
                >
                  通話切断
                </button>
              )}
              <button
                onClick={handleReset}
                disabled={loading}
                className="px-4 py-1.5 text-sm font-medium rounded-lg bg-gray-100 text-gray-700 hover:bg-gray-200 disabled:opacity-50 transition-colors"
              >
                リセット
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Status bar */}
      <div className="mb-3 flex items-center gap-3 text-xs">
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
        {isSpeaking && (
          <button
            onClick={stopSpeaking}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-purple-100 text-purple-700 font-medium hover:bg-purple-200 transition-colors"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-purple-500 animate-pulse" />
            読み上げ中（クリックで停止）
          </button>
        )}
        {callConnectionId && (
          <span className="text-gray-400 font-mono truncate max-w-xs">
            ID: {callConnectionId}
          </span>
        )}
        <span className="text-gray-400">
          {turns.filter((t) => t.role === "user").length} ターン
        </span>
      </div>

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto bg-white border border-gray-200 rounded-xl p-4 space-y-3 mb-4">
        {turns.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-2">
            <svg
              className="w-10 h-10 text-gray-300"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
              />
            </svg>
            <p className="text-sm">
              マイクボタンを押すか、テキストを入力して注文してください
            </p>
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
                  <div className="text-xs text-gray-400 text-right mb-1">
                    {turn.ts} · 発信者
                  </div>
                  <div className="bg-brand-600 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed">
                    {turn.text}
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex justify-start">
                <div className="max-w-[70%]">
                  <div className="text-xs text-gray-400 mb-1">
                    {turn.ts} · AI応答
                  </div>
                  <div className="bg-gray-100 text-gray-900 rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm leading-relaxed">
                    {turn.text}
                  </div>
                  <div className="mt-1.5 flex items-center gap-2">
                    {ttsEnabled && (
                      <button
                        onClick={() => speakText(turn.text)}
                        disabled={isSpeaking}
                        className="text-xs text-gray-400 hover:text-purple-600 disabled:opacity-40"
                        title="再生"
                      >
                        <svg
                          className="w-4 h-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M15.536 8.464a5 5 0 010 7.072M18.364 5.636a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z"
                          />
                        </svg>
                      </button>
                    )}
                    {turn.raw && (
                      <button
                        onClick={() =>
                          setExpandedRaw(expandedRaw === i ? null : i)
                        }
                        className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1"
                      >
                        <svg
                          className={`w-3 h-3 transition-transform ${expandedRaw === i ? "rotate-90" : ""}`}
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M9 5l7 7-7 7"
                          />
                        </svg>
                        詳細
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
                    )}
                  </div>
                  {expandedRaw === i && turn.raw && (
                    <pre className="mt-1 text-xs bg-gray-900 text-green-400 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-all">
                      {JSON.stringify(turn.raw, null, 2)}
                    </pre>
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

      {/* Quick messages */}
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

      {/* Error */}
      {error && (
        <div className="mb-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {/* Input form */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onCompositionStart={() => setIsComposing(true)}
          onCompositionEnd={() => setIsComposing(false)}
          disabled={loading}
          rows={2}
          placeholder={
            isListening
              ? "音声を認識中..."
              : "テキストを入力（Enter で送信、Shift+Enter で改行）"
          }
          className={`flex-1 text-sm border rounded-xl px-4 py-2.5 resize-none focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:bg-gray-50 ${
            isListening ? "border-red-300 bg-red-50/30" : "border-gray-300"
          }`}
        />
        {SpeechRecognitionCtor && (
          <button
            type="button"
            onClick={toggleListening}
            disabled={loading}
            className={`px-4 py-2.5 rounded-xl transition-colors self-end ${
              isListening
                ? "bg-red-500 text-white hover:bg-red-600 animate-pulse"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200 border border-gray-300"
            } disabled:opacity-40`}
            title={isListening ? "認識停止" : "音声入力"}
          >
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              {isListening ? (
                <>
                  <circle cx="12" cy="12" r="9" strokeWidth={2} />
                  <rect
                    x="9"
                    y="9"
                    width="6"
                    height="6"
                    rx="1"
                    strokeWidth={2}
                  />
                </>
              ) : (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
                />
              )}
            </svg>
          </button>
        )}
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="px-5 py-2.5 text-sm font-medium rounded-xl bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors self-end"
        >
          送信
        </button>
      </form>

      {/* VOICEVOX credit */}
      {voicevoxOk && (
        <p className="mt-2 text-[10px] text-gray-400 text-center">
          音声: VOICEVOX ずんだもん
        </p>
      )}
    </div>
  );
}
