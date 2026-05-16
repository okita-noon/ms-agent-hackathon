import { useEffect, useState } from "react";

export default function Header() {
  const [time, setTime] = useState("");

  useEffect(() => {
    const tick = () => {
      setTime(
        new Date().toLocaleString("ja-JP", {
          month: "short",
          day: "numeric",
          weekday: "short",
          hour: "2-digit",
          minute: "2-digit",
        })
      );
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <header className="bg-gradient-to-r from-brand-950 via-brand-900 to-brand-950 text-white sticky top-0 z-40 shadow-[0_1px_3px_rgba(0,0,0,0.3)]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14">
          <div className="flex items-center gap-3">
            <img src="/logo.png" alt="foogent" className="h-8" />
            <span className="hidden sm:block text-[11px] text-brand-300 tracking-widest uppercase font-medium">
              AI Order Management
            </span>
          </div>
          <div className="flex items-center gap-5">
            <div className="flex items-center gap-2">
              <span className="pulse-dot w-2 h-2 bg-green-400 rounded-full inline-block" />
              <span className="text-xs text-green-300 font-medium">稼働中</span>
            </div>
            <div className="text-xs text-brand-300 tabular-nums">{time}</div>
          </div>
        </div>
      </div>
    </header>
  );
}
