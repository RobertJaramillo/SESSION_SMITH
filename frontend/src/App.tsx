import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { LoginPage } from "./pages/LoginPage";
import { ProviderOnboardingModal as ProviderOnboardingDialog } from "./components/ProviderOnboardingModal";
import {
  clearSessionAIProvider,
  getCurrentUser,
  logout as apiLogout,
  setSessionOpenAIKey,
} from "./api/client";
import type { CurrentUser } from "./api/types";
import type { AIProvider } from "./types/providers";
import { DashboardRoute, WorkspaceRoute } from "./routes/AppRoutes";

const PREVIEW_USER: CurrentUser = { email: "drowkiroth@example.com", name: "DrowKiroth" };

export default function App() {
  const startsOnDashboard =
    new URLSearchParams(window.location.search).get("preview") === "dashboard";
  const [authState, setAuthState] = useState<"loading" | "authed" | "anon">(
    startsOnDashboard ? "authed" : "loading",
  );
  const [user, setUser] = useState<CurrentUser | null>(startsOnDashboard ? PREVIEW_USER : null);
  const [providerSetupOpen, setProviderSetupOpen] = useState(false);
  const [provider, setProvider] = useState<AIProvider>("demo");

  useEffect(() => {
    if (startsOnDashboard) return;
    let active = true;
    getCurrentUser()
      .then((current) => {
        if (active) {
          setUser(current);
          setAuthState("authed");
        }
      })
      .catch(() => {
        if (active) setAuthState("anon");
      });
    return () => {
      active = false;
    };
  }, [startsOnDashboard]);

  const configureProvider = (nextProvider: AIProvider, apiKey = "") => {
    if (authState !== "authed") {
      setProviderSetupOpen(false);
      return;
    }
    if (nextProvider === "openai") setSessionOpenAIKey(apiKey);
    else clearSessionAIProvider();
    setProvider(nextProvider);
    setProviderSetupOpen(false);
  };

  const signOut = () => {
    clearSessionAIProvider();
    setProvider("demo");
    setProviderSetupOpen(false);
    apiLogout().finally(() => {
      setUser(null);
      setAuthState("anon");
    });
  };

  if (authState === "loading") {
    return (
      <main className="page-panel">
        <p className="empty-state" role="status">
          Loading…
        </p>
      </main>
    );
  }

  const isAuthenticated = authState === "authed";

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/login"
          element={isAuthenticated ? <Navigate replace to="/campaigns" /> : <LoginPage />}
        />
        <Route
          path="/campaigns"
          element={
            isAuthenticated && user ? (
              <DashboardRoute
                user={user}
                onLogout={signOut}
                provider={provider}
                onManageProvider={() => setProviderSetupOpen(true)}
              />
            ) : (
              <Navigate replace to="/login" />
            )
          }
        />
        <Route
          path="/campaigns/:campaignId/*"
          element={isAuthenticated ? <WorkspaceRoute /> : <Navigate replace to="/login" />}
        />
        <Route
          path="*"
          element={<Navigate replace to={isAuthenticated ? "/campaigns" : "/login"} />}
        />
      </Routes>
      {providerSetupOpen && (
        <ProviderOnboardingDialog
          onClose={() => setProviderSetupOpen(false)}
          onConfigure={configureProvider}
        />
      )}
    </BrowserRouter>
  );
}
