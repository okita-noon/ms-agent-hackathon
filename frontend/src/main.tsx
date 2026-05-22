import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import App from "./App.tsx";

const isPopup = window.opener && window.opener !== window;
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
