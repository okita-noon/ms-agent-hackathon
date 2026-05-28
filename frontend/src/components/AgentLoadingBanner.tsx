import { useEffect, useState } from "react";

const MESSAGES = [
  "受注データを分析しています",
  "異常パターンを検出中",
  "在庫状況を照合しています",
];

/**
 * foogent AI がバックグラウンドで Exception Triage を実行中に表示するバナー。
 * brand グラデーション背景 + シマー + アイコンパルスグロー + ローテーションメッセージ。
 */
export default function AgentLoadingBanner() {
  const [msgIndex, setMsgIndex] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setMsgIndex((prev) => (prev + 1) % MESSAGES.length);
    }, 2500);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="mb-4 rounded-xl border border-brand-200 bg-gradient-to-r from-brand-50 via-brand-100/60 to-brand-50 px-4 py-3 flex items-center gap-3 ai-banner-shimmer fade-in">
      {/* Icon with pulse ring */}
      <div className="relative w-8 h-8 shrink-0 flex items-center justify-center">
        <span className="absolute inset-0 rounded-full bg-brand-400/20 ai-icon-ring" />
        <img src="/favicon.png" alt="foogent" className="w-8 h-8 relative z-10 ai-icon-glow" />
      </div>

      {/* Text area */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-brand-900">foogent AI</span>
          <span className="inline-flex items-center gap-1 rounded-md bg-brand-100 border border-brand-200 px-1.5 py-0.5 text-[10px] font-bold text-brand-700">
            分析中
          </span>
        </div>
        <p key={msgIndex} className="text-xs text-brand-700 mt-0.5 ai-text-fade-in">
          {MESSAGES[msgIndex]}
          <span className="inline-flex ml-0.5 gap-0.5 align-middle">
            <span className="loading-dot" style={{ width: 3, height: 3 }} />
            <span className="loading-dot" style={{ width: 3, height: 3, animationDelay: "120ms" }} />
            <span className="loading-dot" style={{ width: 3, height: 3, animationDelay: "240ms" }} />
          </span>
        </p>
      </div>
    </div>
  );
}
