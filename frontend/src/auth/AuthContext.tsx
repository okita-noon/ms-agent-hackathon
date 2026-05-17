import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { msalInstance, loginScopes } from "./msalConfig";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const TOKEN_KEY = "foogent_token";

interface AuthUser {
  user_id: string;
  tenant_id: string;
  email: string;
  display_name: string;
}

interface AuthContextType {
  user: AuthUser | null;
  token: string | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  loginWithMicrosoft: () => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

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

  // Validate existing token on mount
  useEffect(() => {
    const stored = localStorage.getItem(TOKEN_KEY);
    if (!stored) {
      setIsLoading(false);
      return;
    }

    fetch(`${API_BASE}/api/auth/me`, {
      headers: { Authorization: `Bearer ${stored}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error("invalid");
        return res.json();
      })
      .then((data) => {
        setToken(stored);
        setUser({
          user_id: data.user_id,
          tenant_id: data.tenant_id,
          email: data.email,
          display_name: data.display_name,
        });
      })
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
      })
      .finally(() => setIsLoading(false));
  }, []);

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
      await msalInstance.initialize();
      const result = await msalInstance.loginPopup({
        scopes: loginScopes,
      });

      if (!result.idToken) {
        throw new Error("Microsoft login failed: no id_token");
      }

      const res = await fetch(`${API_BASE}/api/auth/microsoft`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_token: result.idToken }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Microsoftログインに失敗しました");
      }
      const data = await res.json();
      saveToken(data.access_token, {
        user_id: "",
        tenant_id: data.tenant_id,
        email: data.email,
        display_name: data.display_name,
      });
    } catch (err) {
      if (err instanceof Error && err.message.includes("user_cancelled")) {
        return; // User cancelled popup
      }
      throw err;
    }
  }, [saveToken]);

  return (
    <AuthContext.Provider
      value={{ user, token, isLoading, login, loginWithMicrosoft, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}
