import {
  PublicClientApplication,
  BrowserAuthError,
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
};

export const msalInstance = new PublicClientApplication(msalConfig);

export const msalReady: Promise<void> = msalInstance
  .initialize()
  .then(() => msalInstance.handleRedirectPromise())
  .then(() => undefined)
  .catch((err) => {
    if (
      err instanceof BrowserAuthError &&
      err.errorCode === "interaction_in_progress"
    ) {
      sessionStorage.clear();
      return;
    }
    console.error("MSAL init error:", err);
  });

export const loginScopes = ["openid", "profile", "email"];
