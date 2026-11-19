import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { LoginPage } from "./pages/LoginPage";
import { ProviderOnboardingModal as ProviderOnboardingDialog } from "./components/ProviderOnboardingModal";
import { clearSessionAIProvider, setSessionOpenAIKey, getAccount, logout, type Account } from "./api/client";
import type { AIProvider } from "./types/providers";
import { DashboardRoute, WorkspaceRoute } from "./routes/AppRoutes";

export default function App() {
  const [account, setAccount] = useState<Account | null>(null);
  const [checking, setChecking] = useState(true);
  const isAuthenticated = account !== null;
  useEffect(() => {
    getAccount().then(setAccount).catch(() => setAccount(null)).finally(() => setChecking(false));
  }, []);
  const [signOutError, setSignOutError] = useState("");
  const [providerSetupOpen, setProviderSetupOpen] = useState(false);
  const [provider, setProvider] = useState<AIProvider>("demo");

  const configureProvider = (nextProvider: AIProvider, apiKey = "") => {
    if (!isAuthenticated) {
      setProviderSetupOpen(false);
      return;
    }
    if (nextProvider === "openai") setSessionOpenAIKey(apiKey);
    else clearSessionAIProvider();
    setProvider(nextProvider);
    setProviderSetupOpen(false);
  };

  const signOut = async () => {
    setSignOutError("");
    try { await logout(); } catch { setSignOutError("Could not sign out. Please try again."); return; }
    clearSessionAIProvider();
    setProvider("demo");
    setProviderSetupOpen(false);
    setAccount(null);
  };

  if (checking) return <main className="page-panel"><p role="status">Checking your session…</p></main>;

  return (
    <BrowserRouter>
      {signOutError && <p role="alert">{signOutError}</p>}
      <Routes>
        <Route
          path="/login"
          element={
            isAuthenticated ? (
              <Navigate replace to="/campaigns" />
            ) : (
              <LoginPage
                onSignIn={(user) => {
                  setAccount(user);
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
                account={account!}
                onAccountUpdated={setAccount}
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
