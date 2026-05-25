import { useRef, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";

function isMissingDisplayName(value: string | undefined): boolean {
  const normalized = value?.trim();
  return !normalized || /^[?？]+$/.test(normalized);
}

function getProfileLabel(user: NonNullable<ReturnType<typeof useAuth>["user"]>): string {
  if (!isMissingDisplayName(user.display_name)) return user.display_name.trim();
  return user.email || user.user_id || "ユーザー";
}

function getProfileInitial(user: NonNullable<ReturnType<typeof useAuth>["user"]>): string {
  const label = getProfileLabel(user).trim();
  const firstAlphaNumeric = label.match(/[A-Za-z0-9]/)?.[0];
  return (firstAlphaNumeric || Array.from(label)[0] || "U").toUpperCase();
}

export default function Header() {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const profileLabel = user ? getProfileLabel(user) : "";
  const profileInitial = user ? getProfileInitial(user) : "U";

  // Close menu on outside click
  useEffect(() => {
    if (!menuOpen) return;
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  return (
    <header className="bg-gradient-to-r from-brand-950 via-brand-900 to-brand-950 text-white sticky top-0 z-40 shadow-[0_1px_3px_rgba(0,0,0,0.3)]">
      <div className="px-4 sm:px-6">
        <div className="flex items-center justify-between h-14">
          <div className="flex items-center gap-3">
            <img src={`${import.meta.env.BASE_URL}logo.png`} alt="foogent" className="h-7" />
          </div>

          {/* Profile dropdown */}
          {user && (
            <div className="relative" ref={menuRef}>
              <button
                onClick={() => setMenuOpen((v) => !v)}
                className="flex items-center gap-2 rounded-full hover:ring-2 hover:ring-brand-400/40 transition-all"
                aria-label="ユーザーメニュー"
              >
                <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-sm font-bold text-white ring-2 ring-brand-400/30">
                  {profileInitial}
                </div>
              </button>

              {menuOpen && (
                <div className="absolute right-0 mt-2 w-56 bg-white rounded-xl shadow-lg border border-gray-200 py-1 z-50">
                  <div className="px-4 py-3 border-b border-gray-100">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {profileLabel}
                    </p>
                    <p className="text-xs text-gray-500 truncate mt-0.5">
                      {user.email}
                    </p>
                    <p className="text-[10px] text-gray-400 mt-1">
                      テナント: {user.tenant_id}
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      setMenuOpen(false);
                      logout();
                      navigate("/login", { replace: true });
                    }}
                    className="w-full text-left px-4 py-2.5 text-sm text-red-600 hover:bg-red-50 transition-colors flex items-center gap-2"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                    </svg>
                    ログアウト
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
