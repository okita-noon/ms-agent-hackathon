import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import App from "./App.tsx";

const isPopup = window.opener && window.opener !== window;

if (isPopup) {
  document.title = "サインイン中…";
  // msalReady runs handleRedirectPromise() to process the auth code and
  // postMessage the result back to the parent's loginPopup() call.
  // If MSAL fails (network error, state mismatch), the popup stays open and
  // the parent hangs forever. Force-close after 1s so the parent detects
  // popup.closed and rejects with user_cancelled instead of hanging.
  import("./auth/msalConfig.ts").then(({ msalReady }) => {
    msalReady.finally(() => setTimeout(() => window.close(), 1_000));
  });
} else {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <BrowserRouter basename="">
        <App />
      </BrowserRouter>
    </StrictMode>
  );
}
