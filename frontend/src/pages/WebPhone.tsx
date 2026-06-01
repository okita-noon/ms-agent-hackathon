import { useState, useRef, useEffect, useCallback } from "react";
import {
  fetchSpeechToken,
  fetchCustomers,
  webPhoneGreeting,
  webPhoneSendMessage,
  webPhoneDisconnect,
  type Customer,
  type WebPhoneResponse,
} from "../lib/api";

interface Turn {
  role: "user" | "assistant" | "system";
  text: string;
  ts: string;
}

const DEFAULT_CALLER = "+81312345678";
const DEFAULT_CALLED = "+81501234567";

function now() {
  return new Date().toLocaleTimeString("ja-JP", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function playBase64Audio(base64: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const audio = new Audio(`data:audio/mp3;base64,${base64}`);
    audio.onended = () => resolve();
    audio.onerror = () => reject(new Error("Audio playback failed"));
    audio.play().catch(reject);
  });
}

function playRingbackTone(): Promise<void> {
  return new Promise((resolve) => {
    const audioWindow = window as Window & {
      webkitAudioContext?: typeof AudioContext;
    };
    const AudioContextCtor = window.AudioContext || audioWindow.webkitAudioContext;
    if (!AudioContextCtor) {
      resolve();
      return;
    }

    const ctx = new AudioContextCtor();
    const gain = ctx.createGain();
    const toneA = ctx.createOscillator();
    const toneB = ctx.createOscillator();
    const startAt = ctx.currentTime;
    const stopAt = startAt + 0.9;

    toneA.frequency.value = 440;
    toneB.frequency.value = 480;
    toneA.type = "sine";
    toneB.type = "sine";
    gain.gain.setValueAtTime(0.0001, startAt);
    gain.gain.exponentialRampToValueAtTime(0.045, startAt + 0.04);
    gain.gain.setValueAtTime(0.045, startAt + 0.62);
    gain.gain.exponentialRampToValueAtTime(0.0001, stopAt);

    toneA.connect(gain);
    toneB.connect(gain);
    gain.connect(ctx.destination);
    toneA.start(startAt);
    toneB.start(startAt);
    toneA.stop(stopAt);
    toneB.stop(stopAt);
    toneB.onended = () => {
      ctx.close().catch(() => {});
      resolve();
    };
  });
}

type CallPhase = "idle" | "starting" | "connected" | "listening" | "processing";

export default function WebPhone() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>("");
  const [callConnectionId, setCallConnectionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<CallPhase>("idle");
  const [interimText, setInterimText] = useState("");
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [draftMessage, setDraftMessage] = useState("");

  const bottomRef = useRef<HTMLDivElement>(null);
  const recognizerRef = useRef<any>(null);
  const speechTokenRef = useRef<{ token: string; region: string; expiresAt: number } | null>(null);

  const isActive = callConnectionId !== null;
  const loading = phase === "starting" || phase === "processing";

  useEffect(() => {
    fetchCustomers()
      .then((list) => {
        setCustomers(list);
        if (list.length > 0 && !selectedCustomerId) {
          setSelectedCustomerId(list[0].id);
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, interimText]);

  const ensureSpeechToken = useCallback(async () => {
    const cached = speechTokenRef.current;
    if (cached && cached.expiresAt > Date.now()) return cached;
    const result = await fetchSpeechToken();
    const entry = { ...result, expiresAt: Date.now() + 8 * 60 * 1000 };
    speechTokenRef.current = entry;
    return entry;
  }, []);

  function addSystemTurn(text: string) {
    setTurns((prev) => [...prev, { role: "system", text, ts: now() }]);
  }

  async function handleStartCall() {
    setPhase("starting");
    setError(null);
    try {
      const [res] = await Promise.all([
        webPhoneGreeting({
          caller_number: DEFAULT_CALLER,
          called_number: DEFAULT_CALLED,
          customer_id: selectedCustomerId,
        }),
        playRingbackTone().catch(() => {}),
      ]);
      setCallConnectionId(res.call_connection_id);
      addSystemTurn("通話開始");
      setTurns((prev) => [
        ...prev,
        { role: "assistant", text: res.text, ts: now() },
      ]);
      setPhase("connected");
      if (res.audio) {
        setIsSpeaking(true);
        try {
          await playBase64Audio(res.audio);
        } finally {
          setIsSpeaking(false);
        }
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setPhase("idle");
    }
  }

  async function handleDisconnect() {
    if (!callConnectionId || loading) return;
    setPhase("processing");
    setError(null);
    try {
      await webPhoneDisconnect(callConnectionId);
      addSystemTurn("通話終了");
      setCallConnectionId(null);
      setPhase("idle");
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setPhase("connected");
    }
  }

  function handleReset() {
    if (recognizerRef.current) {
      try { recognizerRef.current.close(); } catch { /* ignore */ }
      recognizerRef.current = null;
    }
    setCallConnectionId(null);
    setTurns([]);
    setError(null);
    setInterimText("");
    setPhase("idle");
    setIsSpeaking(false);
  }

  const processResponse = useCallback(
    async (res: WebPhoneResponse) => {
      if (!callConnectionId && res.call_connection_id) {
        setCallConnectionId(res.call_connection_id);
      }

      const text = res.response || (res.error ? `[エラー] ${res.error}` : "[応答なし]");
      setTurns((prev) => [
        ...prev,
        { role: "assistant", text, ts: now() },
      ]);

      if (res.order_id) {
        addSystemTurn("受注確定");
      } else if (res.review_order_id) {
        addSystemTurn("要対応");
      }

      setPhase("connected");

      if (res.response_audio) {
        setIsSpeaking(true);
        try {
          await playBase64Audio(res.response_audio);
        } finally {
          setIsSpeaking(false);
        }
      }
    },
    [callConnectionId],
  );

  async function sendTextMessage(messageText: string) {
    if (!messageText.trim() || loading) return;
    setError(null);
    setPhase("processing");
    setDraftMessage("");
    setTurns((prev) => [
      ...prev,
      { role: "user", text: messageText.trim(), ts: now() },
    ]);

    try {
      const res = await webPhoneSendMessage({
        message: messageText.trim(),
        caller_number: DEFAULT_CALLER,
        called_number: DEFAULT_CALLED,
        call_connection_id: callConnectionId ?? undefined,
        with_audio: true,
        customer_id: selectedCustomerId,
      });
      await processResponse(res);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setTurns((prev) => [
        ...prev,
        { role: "system", text: `送信エラー: ${msg}`, ts: now() },
      ]);
      setPhase(isActive ? "connected" : "idle");
    }
  }

  const startListening = useCallback(async () => {
    if (phase !== "connected") return;
    setError(null);
    setInterimText("");

    try {
      const { token, region } = await ensureSpeechToken();
      const sdk = await import("microsoft-cognitiveservices-speech-sdk");

      const speechConfig = sdk.SpeechConfig.fromAuthorizationToken(token, region);
      speechConfig.speechRecognitionLanguage = "ja-JP";

      const audioConfig = sdk.AudioConfig.fromDefaultMicrophoneInput();
      const recognizer = new sdk.SpeechRecognizer(speechConfig, audioConfig);
      recognizerRef.current = recognizer;

      recognizer.recognizing = (_: unknown, e: any) => {
        if (e.result?.text) setInterimText(e.result.text);
      };

      setPhase("listening");

      recognizer.recognizeOnceAsync(
        async (result: any) => {
          recognizerRef.current = null;
          setInterimText("");

          const text = result.text?.trim();
          if (!text) {
            setPhase("connected");
            return;
          }

          setTurns((prev) => [
            ...prev,
            { role: "user", text, ts: now() },
          ]);
          setPhase("processing");

          try {
            const res = await webPhoneSendMessage({
              message: text,
              caller_number: DEFAULT_CALLER,
              called_number: DEFAULT_CALLED,
              call_connection_id: callConnectionId ?? undefined,
              with_audio: true,
              customer_id: selectedCustomerId,
            });
            await processResponse(res);
          } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            setError(msg);
            setPhase("connected");
          }
        },
        (err: string) => {
          recognizerRef.current = null;
          setInterimText("");
          setError(`音声認識エラー: ${err}`);
          setPhase("connected");
        },
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(`マイク初期化エラー: ${msg}`);
      setPhase("connected");
    }
  }, [phase, callConnectionId, selectedCustomerId, ensureSpeechToken, processResponse]);


  function handleDraftSubmit() {
    void sendTextMessage(draftMessage);
  }

  return (
    <div className="flex flex-col h-[calc(100vh-120px)] max-w-4xl">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900 flex items-center gap-2">
            <svg className="w-6 h-6 text-brand-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
            </svg>
            電話発注（Web）
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            電話注文を想定した音声対話で、AIによる受注処理をその場で体験できます
          </p>
        </div>
        <button
          onClick={handleReset}
          disabled={loading}
          className="px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition-colors"
        >
          リセット
        </button>
      </div>

      {/* Customer selector */}
      <div className="bg-white border border-gray-200 rounded-xl p-4 mb-4">
        <div className="flex flex-wrap gap-4 items-end">
          <div className="flex-1 min-w-60">
            <label className="block text-xs font-medium text-gray-600 mb-1">顧客</label>
            <select
              value={selectedCustomerId}
              onChange={(e) => setSelectedCustomerId(e.target.value)}
              disabled={isActive}
              className="w-full text-sm border border-gray-300 rounded-lg px-3 py-1.5 disabled:bg-gray-50 disabled:text-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.short_name || c.name}（{c.id}）
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Status bar */}
      <div className="mb-3 flex items-center gap-3 text-xs">
        <span
          className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full font-medium ${
            isActive ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"
          }`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${isActive ? "bg-green-500 animate-pulse" : "bg-gray-400"}`} />
          {phase === "idle" && "待機中"}
          {phase === "starting" && "発信中..."}
          {phase === "connected" && "通話中"}
          {phase === "listening" && "音声認識中"}
          {phase === "processing" && "処理中..."}
        </span>
        {isSpeaking && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-purple-100 text-purple-700 font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-500 animate-pulse" />
            読み上げ中
          </span>
        )}
        {selectedCustomerId && (() => {
          const c = customers.find((x) => x.id === selectedCustomerId);
          return c ? (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-medium">
              {c.short_name || c.name}
            </span>
          ) : null;
        })()}
      </div>

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto bg-white border border-gray-200 rounded-xl p-4 space-y-3 mb-4">
        {turns.length === 0 && !interimText && (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-2">
            <svg className="w-10 h-10 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
            </svg>
            <p className="text-sm">「発信」ボタンを押して通話を開始してください</p>
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
                </div>
              </div>
            )}
          </div>
        ))}

        {/* Interim recognition text */}
        {interimText && (
          <div className="flex justify-end">
            <div className="max-w-[70%]">
              <div className="bg-brand-100 text-brand-800 rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed italic">
                {interimText}
                <span className="animate-pulse ml-1">...</span>
              </div>
            </div>
          </div>
        )}

        {phase === "processing" && (
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

      {/* Action buttons */}
      <div className="mb-3 flex items-center gap-3">
        {!isActive ? (
          <button
            onClick={handleStartCall}
            disabled={loading}
            className="flex items-center gap-2 px-6 py-2.5 text-sm font-medium rounded-xl bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
            </svg>
            発信
          </button>
        ) : (
          <>
            <button
              onClick={startListening}
              disabled={phase !== "connected" && phase !== "listening"}
              className={`flex items-center gap-2 px-6 py-2.5 text-sm font-medium rounded-xl transition-all ${
                phase === "listening"
                  ? "bg-red-500 text-white scale-105 shadow-lg shadow-red-200 animate-pulse"
                  : "bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-40"
              }`}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
              {phase === "listening" ? "聞き取り中..." : "音声で注文する"}
            </button>

            <button
              onClick={handleDisconnect}
              disabled={loading}
              className="flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-xl bg-red-50 text-red-700 border border-red-200 hover:bg-red-100 disabled:opacity-50 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
              通話を終了
            </button>
          </>
        )}
      </div>

      {/* Quick messages */}
      {isActive && (
        <>
          <div className="mb-3 rounded-xl border border-gray-200 bg-white p-3">
            <div className="mb-2 flex items-center justify-between">
              <label htmlFor="web-phone-text-input" className="text-xs font-medium text-gray-600">
                テキスト入力
              </label>
              <span className="text-[11px] text-gray-400">音声の代わりにそのまま送信できます</span>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                id="web-phone-text-input"
                type="text"
                value={draftMessage}
                onChange={(e) => setDraftMessage(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    handleDraftSubmit();
                  }
                }}
                disabled={loading}
                placeholder="例: りんご10箱お願いします"
                className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:bg-gray-50 disabled:text-gray-400"
              />
              <button
                onClick={handleDraftSubmit}
                disabled={loading || !draftMessage.trim()}
                className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-700 disabled:opacity-40"
              >
                テキストで送信
              </button>
            </div>
          </div>

          <div className="flex flex-wrap gap-2 mb-3">
            {[
              "りんご10箱お願いします",
              "バナナ20kgとみかん50個",
              "在庫確認したい",
              "キャンセルしたい",
            ].map((msg) => (
              <button
                key={msg}
                onClick={() => sendTextMessage(msg)}
                disabled={loading}
                className="text-xs px-3 py-1 rounded-full border border-gray-300 text-gray-600 hover:bg-gray-50 hover:border-gray-400 disabled:opacity-40 transition-colors"
              >
                {msg}
              </button>
            ))}
          </div>
        </>
      )}

      {/* Error */}
      {error && (
        <div className="mb-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

    </div>
  );
}
