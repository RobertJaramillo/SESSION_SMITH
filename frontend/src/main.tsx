import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

async function start() {
  // Real accounts use FastAPI by default. Explicitly opt into UI-only mocks
  // with VITE_USE_MOCKS=true.
  if (import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS === "true") {
    const { worker } = await import("./mocks/browser");
    await worker.start({ onUnhandledRequest: "bypass" });
  }
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}

start();
