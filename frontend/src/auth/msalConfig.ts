import {
  PublicClientApplication,
  BrowserAuthError,
  type AuthenticationResult,
  type Configuration,
} from "@azure/msal-browser";

const msalConfig: Configuration = {
  auth: {
    clientId: import.meta.env.VITE_ENTRA_CLIENT_ID || "",
    authority: `https://login.microsoftonline.com/${import.meta.env.VITE_ENTRA_TENANT_ID || "common"}`,
    redirectUri: window.location.origin + "/",
  },
  cache: {
    cacheLocation: "localStorage",
  },
  system: {
    // OS の native broker (Windows Hello 等) を呼び出すと
    // ブラウザによっては timed_out エラーになるため無効化する
    allowPlatformBroker: false,
  },
};

export const msalInstance = new PublicClientApplication(msalConfig);

// loginRedirect からの戻り時にトークンを AuthContext に渡すための受け渡し
let _redirectResult: AuthenticationResult | null = null;
export function consumeRedirectResult(): AuthenticationResult | null {
  const result = _redirectResult;
  _redirectResult = null; // 取得と同時に消去し、再実行時の誤再ログインを防ぐ
  return result;
}

export const msalReady: Promise<void> = msalInstance
  .initialize()
  .then(() => msalInstance.handleRedirectPromise())
  .then((result) => {
    if (result) {
      _redirectResult = result;
    }
  })
  .catch((err) => {
    if (
      err instanceof BrowserAuthError &&
      err.errorCode === "interaction_in_progress"
    ) {
      sessionStorage.clear();
      return;
    }
    if (
      err instanceof BrowserAuthError &&
      err.errorCode === "no_token_request_cache_error"
    ) {
      // URL に #code= が残っているがキャッシュにリクエストが無い状態。
      // ハッシュを除去して綺麗なログイン画面に戻す
      if (typeof window !== "undefined") {
        window.history.replaceState(null, "", window.location.pathname + window.location.search);
      }
      return;
    }
    console.error("MSAL init error:", err);
  });

export const loginScopes = ["openid", "profile", "email"];
