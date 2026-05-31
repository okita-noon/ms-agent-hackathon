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

function HelpDrawer({ onClose }: { onClose: () => void }) {
  return (
    <div className="flex flex-col h-full">
      {/* ヘッダー */}
      <div className="flex items-center justify-between px-6 py-5 border-b border-gray-100 shrink-0">
        <div>
          <h2 className="text-base font-bold text-gray-900">foogent の使い方</h2>
          <p className="text-xs text-gray-400 mt-0.5">受注業務をスマートに</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="w-7 h-7 rounded-lg hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-600 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* コンテンツ */}
      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">

        {/* 受注管理 */}
        <div>
          <p className="text-sm font-bold text-gray-800 mb-2">📦 受注管理</p>
          <p className="text-xs text-gray-500 leading-relaxed mb-3">
            LINE・電話・メールから届いた注文をAIが自動解析し、受注一覧に集約します。担当者はチャネルをまたいだすべての受注を1画面で管理できます。
          </p>
          <ul className="space-y-1.5 text-xs text-gray-500">
            <li className="flex gap-2"><span className="text-brand-500 shrink-0">•</span>注文内容・数量・商品名をAIが自動抽出して登録</li>
            <li className="flex gap-2"><span className="text-brand-500 shrink-0">•</span>顧客名・チャネル・配送日でフィルタ・検索が可能</li>
            <li className="flex gap-2"><span className="text-brand-500 shrink-0">•</span>受注詳細を開くとAIとのやり取り全履歴を確認できる</li>
            <li className="flex gap-2"><span className="text-brand-500 shrink-0">•</span>メモ欄に担当者のコメントを記録できる</li>
          </ul>
        </div>

        <hr className="border-gray-100" />

        {/* ステータスの流れ */}
        <div>
          <p className="text-sm font-bold text-gray-800 mb-2">🔄 ステータスの流れ</p>
          <div className="flex items-center gap-1.5 text-[11px] flex-wrap mb-3">
            <span className="bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">受注済み</span>
            <span className="text-gray-400">→</span>
            <span className="bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full font-medium">配送中</span>
            <span className="text-gray-400">→</span>
            <span className="bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">完了</span>
          </div>
          <ul className="space-y-1.5 text-xs text-gray-500">
            <li className="flex gap-2"><span className="text-brand-500 shrink-0">•</span><span><span className="font-medium text-gray-700">受注済み</span>：注文が確定した状態。AIが受注確定メッセージを顧客に自動送信</span></li>
            <li className="flex gap-2"><span className="text-brand-500 shrink-0">•</span><span><span className="font-medium text-gray-700">配送中</span>：受注確定から10分後に自動遷移。商品が出荷・輸送中の状態</span></li>
            <li className="flex gap-2"><span className="text-brand-500 shrink-0">•</span><span><span className="font-medium text-gray-700">完了</span>：配送予定日（到着日）の指定時間以降に自動遷移</span></li>
          </ul>
          <p className="text-[11px] text-gray-400 mt-2">
            ※ <span className="bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-medium">要対応</span> は数量異常・在庫不足など異常時のみ表示。担当者が確認・対処後に受注済みへ移行します。
          </p>
        </div>

        <hr className="border-gray-100" />

        {/* AI例外・要対応 */}
        <div>
          <p className="text-sm font-bold text-gray-800 mb-2">⚠️ AI例外・要対応</p>
          <p className="text-xs text-gray-500 leading-relaxed mb-3">
            受注一覧上部のバナーに、担当者の確認が必要な受注件数をリアルタイムで表示します。「詳細を確認」ボタンで内容を確認できます。
          </p>
          <ul className="space-y-1.5 text-xs text-gray-500">
            <li className="flex gap-2"><span className="text-red-400 shrink-0">•</span><span><span className="font-medium text-gray-700">高（急ぎ）</span>：在庫不足・大幅な数量異常など即対応が必要なケース</span></li>
            <li className="flex gap-2"><span className="text-amber-400 shrink-0">•</span><span><span className="font-medium text-gray-700">中</span>：通常と異なる数量・単位など確認が望ましいケース</span></li>
            <li className="flex gap-2"><span className="text-brand-500 shrink-0">•</span>例外パネルで推奨アクションとAIによる対応文案を確認できる</li>
            <li className="flex gap-2"><span className="text-brand-500 shrink-0">•</span>在庫不足で顧客が数量を減らした場合、機会損失フォロー対象として高で通知</li>
          </ul>
        </div>

        <hr className="border-gray-100" />

        {/* 在庫管理 */}
        <div>
          <p className="text-sm font-bold text-gray-800 mb-2">📊 在庫管理</p>
          <p className="text-xs text-gray-500 leading-relaxed mb-3">
            商品ごとの現在在庫数をリアルタイムで確認できます。受注時にAIが自動で在庫チェックを行い、不足時は顧客に通知します。
          </p>
          <ul className="space-y-1.5 text-xs text-gray-500">
            <li className="flex gap-2"><span className="text-brand-500 shrink-0">•</span>商品名・在庫数・温度帯を一覧で確認</li>
            <li className="flex gap-2"><span className="text-brand-500 shrink-0">•</span>受注が確定すると在庫が自動的に引き当てられる</li>
            <li className="flex gap-2"><span className="text-brand-500 shrink-0">•</span>在庫が注文数に対して不足している場合、AIが顧客に代替案を提案</li>
          </ul>
        </div>

        <hr className="border-gray-100" />

        {/* 顧客管理 */}
        <div>
          <p className="text-sm font-bold text-gray-800 mb-2">👥 顧客管理</p>
          <p className="text-xs text-gray-500 leading-relaxed mb-3">
            顧客ごとの基本情報と納品設定を管理します。設定内容はAIの受注処理に自動反映されます。
          </p>
          <ul className="space-y-1.5 text-xs text-gray-500">
            <li className="flex gap-2"><span className="text-brand-500 shrink-0">•</span>納品リードタイム（当日・翌日・中1日・中2日）を顧客ごとに設定</li>
            <li className="flex gap-2"><span className="text-brand-500 shrink-0">•</span>リードタイムをもとにAIが配送予定日を自動計算</li>
            <li className="flex gap-2"><span className="text-brand-500 shrink-0">•</span>過去の注文パターンをAIが学習し、「いつもの」注文に自動対応</li>
            <li className="flex gap-2"><span className="text-brand-500 shrink-0">•</span>LINE・メール・電話のチャネルを問わず同一顧客として管理</li>
          </ul>
        </div>

      </div>
    </div>
  );
}

export default function Header() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const profileLabel = user ? getProfileLabel(user) : "";
  const profileInitial = user ? getProfileInitial(user) : "U";

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
    <>
      <header className="bg-gradient-to-r from-brand-950 via-brand-900 to-brand-950 text-white sticky top-0 z-40 shadow-[0_1px_3px_rgba(0,0,0,0.3)]">
        <div className="px-4 sm:px-6">
          <div className="flex items-center justify-between h-14">
            <div className="flex items-center gap-3">
              <img src={`${import.meta.env.BASE_URL}logo.png`} alt="foogent" className="h-7" />
            </div>

            <div className="flex items-center gap-3">
              {/* 使い方ボタン */}
              <button
                type="button"
                onClick={() => setHelpOpen((v) => !v)}
                className="flex items-center gap-1 text-xs text-brand-200 hover:text-white transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                使い方
              </button>

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
                        <p className="text-sm font-medium text-gray-900 truncate">{profileLabel}</p>
                        <p className="text-xs text-gray-500 truncate mt-0.5">{user.email}</p>
                        <p className="text-[10px] text-gray-400 mt-1">テナント: {user.tenant_id}</p>
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
        </div>
      </header>

      {/* 右端ドロワー */}
      <div
        className="fixed top-0 right-0 h-full w-96 bg-white shadow-2xl border-l border-gray-200 z-50 transition-transform duration-500 ease-in-out overflow-y-auto"
        style={{ transform: helpOpen ? "translateX(0)" : "translateX(100%)" }}
      >
        <HelpDrawer onClose={() => setHelpOpen(false)} />
      </div>
    </>
  );
}
