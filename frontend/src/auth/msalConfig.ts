import { PublicClientApplication, type Configuration } from "@azure/msal-browser";

const msalConfig: Configuration = {
  auth: {
    clientId: import.meta.env.VITE_ENTRA_CLIENT_ID || "",
    authority: `https://login.microsoftonline.com/${import.meta.env.VITE_ENTRA_TENANT_ID || "common"}`,
    redirectUri: window.location.origin + "/dashboard",
  },
  cache: {
    cacheLocation: "localStorage",
  },
};

export const msalInstance = new PublicClientApplication(msalConfig);

export const msalReady: Promise<void> = msalInstance
  .initialize()
  .then(() => msalInstance.handleRedirectPromise())
  .then(() => undefined);

export const loginScopes = ["openid", "profile", "email"];
