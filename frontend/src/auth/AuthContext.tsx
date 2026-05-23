import {
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { readUserFromToken, type AuthUser } from "./token";
import { AuthContext } from "./context";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const TOKEN_KEY = "foogent_token";

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [initialAuth] = useState(() => {
    const stored = localStorage.getItem(TOKEN_KEY);
    const storedUser = stored ? readUserFromToken(stored) : null;
    return {
      token: storedUser ? stored : null,
      user: storedUser,
      isLoading: Boolean(stored && !storedUser),
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
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  // Microsoft 認証から戻ってきた直後にリダイレクト結果を処理する
  useEffect(() => {
    let cancelled = false;

    (async () => {
      const { msalReady, getRedirectResult } = await import("./msalConfig");
      await msalReady;
      if (cancelled) return;

      const redirectResult = getRedirectResult();
      if (!redirectResult?.idToken) return;

      try {
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
      } catch (err) {
        console.error("Microsoft auth callback failed:", err);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [saveToken]);

  // ストレージ済み JWT を /api/auth/me で検証
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
        if (cachedUser && err instanceof Error && err.message === "transient") return;
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
    },
    [saveToken]
  );

  const loginWithMicrosoft = useCallback(async () => {
    try {
      const { msalInstance, msalReady, loginScopes } = await import(
        "./msalConfig"
      );
      await msalReady;
      // loginRedirect doesn't return — the page navigates away to Microsoft
      // and comes back via the redirect callback handled in the useEffect above.
      await msalInstance.loginRedirect({
        scopes: loginScopes,
      });
    } catch (err: unknown) {
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
