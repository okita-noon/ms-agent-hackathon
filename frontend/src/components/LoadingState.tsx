import type { ReactNode } from "react";

type LoadingStateProps = {
  title?: string;
  message?: string;
  icon?: ReactNode;
  compact?: boolean;
};

const defaultIcon = (
  <svg className="w-8 h-8 text-brand-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.7} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
  </svg>
);

export default function LoadingState({
  title = "準備しています",
  message = "最新データを確認中です",
  icon = defaultIcon,
  compact = false,
}: LoadingStateProps) {
  return (
    <div className={`loading-state flex flex-col items-center justify-center text-center ${compact ? "py-16" : "min-h-screen"}`}>
      <div className="relative mb-5">
        <div className="loading-halo absolute inset-0 rounded-full bg-brand-100" />
        <div className="relative w-18 h-18 rounded-2xl bg-white border border-brand-100 shadow-sm flex items-center justify-center">
          {icon}
          <span className="absolute -right-1 -bottom-1 w-6 h-6 rounded-full bg-white border border-brand-100 flex items-center justify-center shadow-sm">
            <span className="loading-spinner w-3.5 h-3.5 rounded-full border-2 border-brand-200 border-t-brand-600" />
          </span>
        </div>
      </div>
      <p className="text-sm font-semibold text-gray-800">{title}</p>
      <p className="text-xs text-gray-400 mt-1">{message}</p>
      <div className="flex items-center gap-1.5 mt-4" aria-hidden="true">
        <span className="loading-dot" />
        <span className="loading-dot" />
        <span className="loading-dot" />
      </div>
    </div>
  );
}
