import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";

export default function Login() {
  const { login, loginWithMicrosoft } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pwLoading, setPwLoading] = useState(false);
  const [msLoading, setMsLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setPwLoading(true);
    try {
      await login(email, password);
      // setUser と同じタイミングで URL を /orders に変更することで、
      // AuthenticatedRouter が /login → <Navigate> → null → /orders という
      // 中間ステップを踏まずにダッシュボードを直接レンダリングできる
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
      <div className="w-full max-w-sm">
        {/* Logo / Title */}
        <div className="text-center mb-8">
          <img src={`${import.meta.env.BASE_URL}favicon.png`} alt="" className="h-16 mx-auto mb-2" />
          <span className="text-3xl font-bold">
            <span className="text-gray-700">foo</span>
            <span className="text-orange-500">gent</span>
          </span>
          <p className="text-sm text-gray-500 mt-1">
            受注業務をスマートに
          </p>
        </div>

        {/* Login Card */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">
                メールアドレス
              </label>
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
              <label className="block text-xs font-medium text-gray-600 mb-1.5">
                パスワード
              </label>
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

          {/* Divider */}
          <div className="relative my-5">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-200" />
            </div>
            <div className="relative flex justify-center">
              <span className="bg-white px-3 text-xs text-gray-400">
                または
              </span>
            </div>
          </div>

          {/* Microsoft SSO */}
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
        </div>

        {/* Footer */}
        <p className="text-center text-[11px] text-gray-400 mt-4">
          foogent v1.0
        </p>
      </div>
    </div>
  );
}
