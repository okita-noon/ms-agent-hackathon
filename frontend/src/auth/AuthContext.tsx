import {
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import { readUserFromToken, type AuthUser } from "./token";
import { AuthContext } from "./context";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const TOKEN_KEY = "foogent_token";
const SSO_PENDING_KEY = "sso_redirect_pending";

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const navigate = useNavigate();
  const [initialAuth] = useState(() => {
    const stored = localStorage.getItem(TOKEN_KEY);
    const storedUser = stored ? readUserFromToken(stored) : null;
    // Microsoft loginRedirect から戻ってきた直後は URL に code= が残る。
    // sessionStorage フラグ（loginRedirect 前にセット）も合わせてチェックすることで
    // URL だけでは検知できないケースでもローディング状態を維持し、
    // ログイン画面の一瞬表示（フラッシュ）を防ぐ。
    const hasMsalRedirect =
      /[?&]code=/.test(window.location.search) ||
      /[#&](code|error)=/.test(window.location.hash) ||
      sessionStorage.getItem(SSO_PENDING_KEY) === "1";
    return {
      token: storedUser ? stored : null,
      user: storedUser,
      // ユーザーが未確定 かつ (未検証トークンあり OR MSALリダイレクト中) → 読み込み中
      isLoading: !storedUser && Boolean(stored || hasMsalRedirect),
      stored,
    };
  });
  const [user, setUser] = useState<AuthUser | null>(initialAuth.user);
  const [token, setToken] = useState<string | null>(initialAuth.token);
  const [isLoading, setIsLoading] = useState(initialAuth.isLoading);

  const saveToken = useCallback((t: string, u: AuthUser) => {
    localStorage.setItem(TOKEN_KEY, t);
    setToken(t);
    setUser(u);
    // user と同じバッチで isLoading を落とし、LoadingScreen → Dashboard の
    // 遷移を1回のレンダリングに収める（中間状態でログイン画面が見えるのを防ぐ）
    setIsLoading(false);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  // Microsoft loginRedirect から戻ってきた直後にリダイレクト結果を処理する
  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const { msalReady, getRedirectResult } = await import("./msalConfig");
        await msalReady;
        if (cancelled) return;

        const redirectResult = getRedirectResult();
        if (!redirectResult?.idToken) return;

        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 30_000);
        const res = await fetch(`${API_BASE}/api/auth/microsoft`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id_token: redirectResult.idToken }),
          signal: controller.signal,
        }).finally(() => clearTimeout(timeout));

        if (!res.ok) {
          console.error("Microsoft auth callback rejected by server:", res.status);
          return;
        }
        const data = await res.json();
        if (cancelled) return;
        saveToken(data.access_token, {
          user_id: "",
          tenant_id: data.tenant_id,
          email: data.email,
          display_name: data.display_name,
        });
        // ログイン画面が再表示されずに直接 /orders へ遷移する
        navigate("/orders", { replace: true });
      } catch (err) {
        console.error("Microsoft auth callback failed:", err);
      } finally {
        // リダイレクト処理完了後にフラグとローディングを解除（成功・失敗どちらでも）
        sessionStorage.removeItem(SSO_PENDING_KEY);
        if (!cancelled) setIsLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [saveToken, navigate]);

  // 401 イベントでトークン期限切れを検知してログアウト
  useEffect(() => {
    function handleTokenExpired() {
      setToken(null);
      setUser(null);
    }
    window.addEventListener("auth:token-expired", handleTokenExpired);
    return () => window.removeEventListener("auth:token-expired", handleTokenExpired);
  }, []);

  useEffect(() => {
    let active = true;
    const stored = initialAuth.stored;
    if (!stored) {
      return undefined;
    }

    const cachedUser = initialAuth.user;

    fetch(`${API_BASE}/api/auth/me`, {
      headers: { Authorization: `Bearer ${stored}` },
    })
      .then((res) => {
        if (res.status === 401 || res.status === 403) throw new Error("invalid");
        if (!res.ok) throw new Error("transient");
        return res.json();
      })
      .then((data) => {
        if (!active) return;
        setToken(stored);
        setUser({
          user_id: data.user_id,
          tenant_id: data.tenant_id,
          email: data.email,
          display_name: data.display_name,
        });
      })
      .catch((err: unknown) => {
        const isAuthRejected = err instanceof Error && err.message === "invalid";
        if (cachedUser && !isAuthRejected) return;
        localStorage.removeItem(TOKEN_KEY);
        if (!active) return;
        setToken(null);
        setUser(null);
      })
      .finally(() => {
        if (active && !cachedUser) setIsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [initialAuth.stored, initialAuth.user]);

  const login = useCallback(
    async (email: string, password: string) => {
      // ログイン処理中は LoadingScreen を出しておき、フォームが消えた瞬間に
      // ログイン画面が再表示されるフラッシュを防ぐ
      setIsLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || "ログインに失敗しました");
        }
        const data = await res.json();
        saveToken(data.access_token, {
          user_id: "",
          tenant_id: data.tenant_id,
          email: data.email,
          display_name: data.display_name,
        });
        // saveToken 内で setIsLoading(false) が呼ばれる
      } catch (err) {
        setIsLoading(false); // エラー時はローディングを解除してフォームを再表示
        throw err;
      }
    },
    [saveToken]
  );

  const loginWithMicrosoft = useCallback(async () => {
    try {
      const { msalInstance, msalReady, loginScopes } = await import(
        "./msalConfig"
      );
      await msalReady;
      // loginRedirect はページ遷移するため戻らない。
      // 遷移前にフラグをセットしておき、戻り時の isLoading 検知を確実にする。
      sessionStorage.setItem(SSO_PENDING_KEY, "1");
      await msalInstance.loginRedirect({
        scopes: loginScopes,
      });
    } catch (err: unknown) {
      sessionStorage.removeItem(SSO_PENDING_KEY);
      if (err instanceof Error) {
        if (err.message.includes("interaction_in_progress")) {
          sessionStorage.clear();
          throw new Error(
            "ブラウザの状態をリセットしました。もう一度お試しください。",
            { cause: err }
          );
        }
      }
      throw err;
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, token, isLoading, login, loginWithMicrosoft, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}
