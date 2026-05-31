import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";

function HelpPane({ onClose }: { onClose: () => void }) {
  return (
    <div className="flex flex-col h-full overflow-y-auto">
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

      <div className="px-6 py-5 space-y-6">
        {/* 機能紹介 */}
        <div className="space-y-4">
          <div>
            <p className="text-xs font-bold text-gray-700 mb-1.5">📦 受注管理</p>
            <p className="text-xs text-gray-500 leading-relaxed">
              LINE・電話・メールから届いた注文をAIが自動解析し、受注一覧に集約します。
            </p>
          </div>
          <div>
            <p className="text-xs font-bold text-gray-700 mb-1.5">🔄 ステータスの流れ</p>
            <div className="flex items-center gap-1.5 text-[11px] text-gray-500 flex-wrap mb-2">
              <span className="bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">受注済み</span>
              <span>→</span>
              <span className="bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full font-medium">配送中</span>
              <span>→</span>
              <span className="bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">完了</span>
            </div>
            <p className="text-[11px] text-gray-400">
              ※ <span className="bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-medium">要対応</span> は数量異常・在庫不足など異常時のみ表示。担当者が確認後に受注済みへ移行します。
            </p>
          </div>
          <div>
            <p className="text-xs font-bold text-gray-700 mb-1.5">⚠️ AI例外・要対応</p>
            <p className="text-xs text-gray-500 leading-relaxed">
              数量異常・在庫不足など担当者の判断が必要な受注を自動検出します。「高（急ぎ）」「中」の2段階でアラートを表示します。
            </p>
          </div>
          <div>
            <p className="text-xs font-bold text-gray-700 mb-1.5">📊 在庫・顧客管理</p>
            <p className="text-xs text-gray-500 leading-relaxed">
              商品在庫のリアルタイム確認と、顧客ごとの納品リードタイム・注文パターンを管理できます。
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Login() {
  const { login, loginWithMicrosoft } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pwLoading, setPwLoading] = useState(false);
  const [msLoading, setMsLoading] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setPwLoading(true);
    try {
      await login(email, password);
      navigate("/orders", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "ログインに失敗しました");
    } finally {
      setPwLoading(false);
    }
  }

  async function handleMicrosoft() {
    setError("");
    setMsLoading(true);
    try {
      await loginWithMicrosoft();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Microsoftログインに失敗しました"
      );
    } finally {
      setMsLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-surface flex items-center justify-center px-4">
      {/* 右上固定「使い方」ボタン */}
      <button
        type="button"
        onClick={() => setHelpOpen((v) => !v)}
        className="fixed top-4 right-4 z-30 flex items-center gap-1.5 rounded-full bg-white border border-gray-200 shadow-sm px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 hover:text-brand-600 transition-colors"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        使い方
      </button>

      {/* ログインカード: 常に中央固定 */}
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
          {/* Logo */}
          <div className="text-center mb-6">
            <img src={`${import.meta.env.BASE_URL}favicon.png`} alt="" className="h-14 mx-auto mb-2" />
            <span className="text-3xl font-bold">
              <span className="text-gray-700">foo</span>
              <span className="text-orange-500">gent</span>
            </span>
            <p className="text-sm text-gray-500 mt-1">受注業務をスマートに</p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">メールアドレス</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                placeholder="user@example.com"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">パスワード</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                placeholder="********"
              />
            </div>

            {error && (
              <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={pwLoading || msLoading}
              className="w-full py-2.5 bg-brand-600 text-white text-sm font-medium rounded-lg hover:bg-brand-700 transition-colors disabled:opacity-50"
            >
              {pwLoading ? "ログイン中..." : "ログイン"}
            </button>
          </form>

          <div className="relative my-4">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-200" />
            </div>
            <div className="relative flex justify-center">
              <span className="bg-white px-3 text-xs text-gray-400">または</span>
            </div>
          </div>

          <button
            onClick={handleMicrosoft}
            disabled={msLoading || pwLoading}
            className="w-full flex items-center justify-center gap-2.5 py-2.5 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50"
          >
            <svg className="w-4 h-4" viewBox="0 0 21 21">
              <rect x="1" y="1" width="9" height="9" fill="#f25022" />
              <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
              <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
              <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
            </svg>
            Microsoft アカウントでログイン
          </button>

          <p className="text-center text-[11px] text-gray-400 mt-3">foogent v1.0</p>
        </div>

      {/* 右端ドロワー: fixed で画面右端からにゅるっと出てくる */}
      <div
        className="fixed top-0 right-0 h-full w-80 bg-white shadow-2xl border-l border-gray-200 z-50 transition-transform duration-500 ease-in-out overflow-y-auto"
        style={{ transform: helpOpen ? "translateX(0)" : "translateX(100%)" }}
      >
        <HelpPane onClose={() => setHelpOpen(false)} />
      </div>

    </div>
  );
}
