import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import App from "./App.tsx";
import { msalReady } from "./auth/msalConfig.ts";

const isPopup = window.opener && window.opener !== window;

// msalReady must run in ALL contexts (including popups).
// In popup mode, handleRedirectPromise() processes the auth code
// and sends the result back to the parent via postMessage.
msalReady.catch(() => undefined);

if (isPopup) {
  document.title = "サインイン中…";
} else {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <BrowserRouter basename="/dashboard">
        <App />
      </BrowserRouter>
    </StrictMode>
  );
}
