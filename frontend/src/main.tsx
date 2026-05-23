import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import App from "./App.tsx";

const isPopup = window.opener && window.opener !== window;
const hasMsalResponse = /[#&](code|error)=/.test(window.location.hash);

if (isPopup || hasMsalResponse) {
  document.title = "サインイン中…";
  // msalReady runs handleRedirectPromise() to process the auth code and
  // postMessage the result back to the parent's loginPopup() call.
  // Also handles the case where window.opener is lost but the URL hash
  // contains an MSAL auth response (code= or error=).
  // Force-close after 1s so the parent detects popup.closed and rejects
  // with user_cancelled instead of hanging on MSAL failure.
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
