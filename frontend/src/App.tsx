import { useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { LoginPage } from "./pages/LoginPage";
import { ProviderOnboardingModal as ProviderOnboardingDialog } from "./components/ProviderOnboardingModal";
import { clearSessionAIProvider, setSessionOpenAIKey } from "./api/client";
import type { AIProvider } from "./types/providers";
import { DashboardRoute, WorkspaceRoute } from "./routes/AppRoutes";

export default function App() {
  const startsOnDashboard =
    new URLSearchParams(window.location.search).get("preview") === "dashboard";
  const [isAuthenticated, setIsAuthenticated] = useState(startsOnDashboard);
  const [providerSetupOpen, setProviderSetupOpen] = useState(false);
  const [provider, setProvider] = useState<AIProvider>("demo");

  const configureProvider = (nextProvider: AIProvider, apiKey = "") => {
    if (nextProvider === "openai") setSessionOpenAIKey(apiKey);
    else clearSessionAIProvider();
    setProvider(nextProvider);
    setProviderSetupOpen(false);
  };

  const signOut = () => {
    clearSessionAIProvider();
    setProvider("demo");
    setIsAuthenticated(false);
  };

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/login"
          element={
            isAuthenticated ? (
              <Navigate replace to="/campaigns" />
            ) : (
              <LoginPage
                onSignIn={() => {
                  setIsAuthenticated(true);
                  setProviderSetupOpen(true);
                }}
              />
            )
          }
        />
        <Route
          path="/campaigns"
          element={
            isAuthenticated ? (
              <DashboardRoute
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
          element={
            isAuthenticated ? (
              <WorkspaceRoute />
            ) : (
              <Navigate replace to="/login" />
            )
          }
        />
        <Route
          path="*"
          element={
            <Navigate replace to={isAuthenticated ? "/campaigns" : "/login"} />
          }
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
