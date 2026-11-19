import { Dialog } from "./Dialog";
import { useEffect, useState } from "react";
import { getAuthConfig, getAuthConnections, googleLinkUrl, googleLoginUrl, forgotPassword, updateAccount, type Account } from "../api/client";
import type { AIProvider } from "../types/providers";

type EditableSettingId = "name" | "email" | "password";
type SettingsRow = {
  id: EditableSettingId | "tier";
  label: string;
  value: string;
  helper: string;
  editable: boolean;
  inputType?: "text" | "email" | "password";
};

export function SettingsModal({
  accountEmail,
  accountName,
  accountTier,
  onClose,
  provider,
  onManageProvider,
  onAccountUpdated,
}: {
  accountEmail: string;
  accountName: string;
  accountTier: string;
  onClose: () => void;
  provider: AIProvider;
  onManageProvider: () => void;
  onAccountUpdated: (account: Account) => void;
}) {
  const [managed, setManaged] = useState(false);
  const [recoveryNotice, setRecoveryNotice] = useState("");
  const [sendingReset, setSendingReset] = useState(false);
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [googleConnected, setGoogleConnected] = useState<boolean | null>(null);
  const [connectionError, setConnectionError] = useState(false);
  useEffect(() => {
    let active = true;
    getAuthConfig().then((config) => { if (active) { setGoogleEnabled(config.googleEnabled); setManaged(config.provider === "firebase"); } }).catch(() => {});
    getAuthConnections().then((connections) => { if (active) setGoogleConnected(connections.googleConnected); })
      .catch(() => { if (active) setConnectionError(true); });
    return () => { active = false; };
  }, []);
  const [settingValues, setSettingValues] = useState<
    Record<EditableSettingId, string>
  >({ name: accountName, email: accountEmail, password: "Password unchanged" });
  const [editingSetting, setEditingSetting] = useState<SettingsRow | null>(
    null,
  );
  const settingsRows: SettingsRow[] = [
    {
      id: "name",
      label: "User name",
      value: settingValues.name,
      helper: "Display name shown at the top of your campaign dashboard.",
      editable: true,
      inputType: "text",
    },
    {
      id: "tier",
      label: "Account tier",
      value: accountTier,
      helper: "Current access level for Session Smith features.",
      editable: false,
    },
    {
      id: "email",
      label: "Email",
      value: settingValues.email,
      helper: managed ? "Verified sign-in address. Email changes are not available yet." : "Primary address used for account notices and sign in.",
      editable: !managed,
      inputType: "email",
    },
    {
      id: "password",
      label: "Password reset",
      value: settingValues.password,
      helper: managed ? "We’ll email you a secure link to choose a new password." : "Enter and confirm a new password before saving.",
      editable: !managed,
      inputType: "password",
    },
  ];
  const saveSetting = async (settingId: EditableSettingId, value: string, currentPassword: string) => {
    const account = await updateAccount({ [settingId]: value, currentPassword });
    onAccountUpdated(account);
    setSettingValues((current) => ({
      ...current,
      [settingId]: settingId === "password" ? "Password updated" : value,
    }));
    setEditingSetting(null);
  };

  return (
    <Dialog labelledBy="settings-modal-title" onClose={onClose}>
        <div className="settings-modal-header">
          <div>
            <span className="eyebrow">Account settings</span>
            <h2 id="settings-modal-title">Settings</h2>

          </div>
          <button
            aria-label="Close settings"
            className="modal-close-button"
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </div>
        <div className="settings-option-list">
          <article className="settings-option">
            <div>
              <span>AI provider</span>
              <strong>
                {provider === "openai"
                  ? "OpenAI — this browser session"
                  : "No provider connected"}
              </strong>
              <p>
                {provider === "openai"
                  ? "Your key is held only in memory and is cleared when you log out or refresh."
                  : "Connect an AI provider to use live generation."}
              </p>
            </div>
            <div
              className="settings-option-actions"
              aria-label="AI provider actions"
            >
              <button onClick={onManageProvider} type="button">
                Manage
              </button>
            </div>
          </article>
          {googleEnabled && <article className="settings-option">
            <div>
              <span>Google sign-in</span>
              <strong>{googleConnected ? "Google account connected" : "Connect your Google account"}</strong>
              <p>{googleConnected ? "You can sign in using Google." : connectionError ? "Could not check your connected accounts. Reopen settings to try again." : googleConnected === null ? "Checking connection…" : "Use Google to sign in with the same email address."}</p>
            </div>
            <div className="settings-option-actions">
              {googleConnected ? <span className="settings-readonly-badge">Connected</span> : googleConnected === false ? <a className="button-link secondary" href={managed ? googleLinkUrl() : googleLoginUrl()}>Connect Google</a> : null}
            </div>
          </article>}
          {settingsRows.map((row) => (
            <article className="settings-option" key={row.id}>
              <div>
                <span>{row.label}</span>
                <strong>{row.value}</strong>
                <p>{row.helper}</p>
              </div>
              {row.id === "password" && managed ? (
                <div className="settings-option-actions">
                  <button type="button" disabled={sendingReset} onClick={async () => {
                    setSendingReset(true);
                    setRecoveryNotice("");
                    try { setRecoveryNotice((await forgotPassword(accountEmail)).message); }
                    catch (error) { setRecoveryNotice(error instanceof Error ? error.message : "Could not send reset email."); }
                    finally { setSendingReset(false); }
                  }}>{sendingReset ? "Sending…" : "Send reset email"}</button>
                </div>
              ) : row.editable ? (
                <div
                  className="settings-option-actions"
                  aria-label={`${row.label} actions`}
                >
                  <button onClick={() => setEditingSetting(row)} type="button">
                    Update
                  </button>
                </div>
              ) : (
                <span className="settings-readonly-badge">{row.id === "tier" ? "Current plan" : "Read only"}</span>
              )}
            </article>
          ))}
          {recoveryNotice && <p className="settings-feedback" role="status">{recoveryNotice}</p>}
        </div>
      {editingSetting && editingSetting.id !== "tier" && (
        <SettingUpdateModal
          currentValue={editingSetting.value}
          inputType={editingSetting.inputType ?? "text"}
          label={editingSetting.label}
          onClose={() => setEditingSetting(null)}
          onSave={(value, currentPassword) =>
            saveSetting(editingSetting.id as EditableSettingId, value, currentPassword)
          }
        />
      )}
    </Dialog>
  );
}

function SettingUpdateModal({
  currentValue,
  inputType,
  label,
  onClose,
  onSave,
}: {
  currentValue: string;
  inputType: "text" | "email" | "password";
  label: string;
  onClose: () => void;
  onSave: (value: string, currentPassword: string) => Promise<void>;
}) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [newValue, setNewValue] = useState("");
  const [confirmValue, setConfirmValue] = useState("");
  const valuesMatch =
    newValue.length > 0 && confirmValue.length > 0 && newValue === confirmValue;
  return (
    <Dialog labelledBy="setting-update-title" onClose={onClose} className="settings-modal setting-update-modal" overlayClassName="nested-modal-backdrop">
        <div className="settings-modal-header">
          <div>
            <span className="eyebrow">Update setting</span>
            <h2 id="setting-update-title">Update {label}</h2>
          </div>
          <button
            aria-label="Close update setting"
            className="modal-close-button"
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </div>
        <div className="setting-update-body">
          <p>
            Current value:{" "}
            <strong>
              {inputType === "password" ? "Hidden for security" : currentValue}
            </strong>
          </p>
          {inputType !== "text" && <label>Current password<input type="password" autoComplete="current-password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} /></label>}
          <label>
            New {label}
            <input
              autoComplete="off"
              onChange={(event) => setNewValue(event.target.value)}
              placeholder={`Enter new ${label.toLowerCase()}`}
              type={inputType}
              value={newValue}
            />
          </label>
          <label>
            Confirm new {label}
            <input
              autoComplete="off"
              onChange={(event) => setConfirmValue(event.target.value)}
              placeholder={`Confirm new ${label.toLowerCase()}`}
              type={inputType}
              value={confirmValue}
            />
          </label>
          {error && <p role="alert">{error}</p>}
          {inputType === "password" && <p>Use at least 12 characters.</p>}
          {!valuesMatch && (newValue.length > 0 || confirmValue.length > 0) && (
            <p className="settings-validation-message">
              Both fields must be filled in and match before Save is enabled.
            </p>
          )}
        </div>
        <div className="settings-confirm-actions">
          <button
            disabled={!valuesMatch || busy || (inputType !== "text" && !currentPassword) || (inputType === "password" && newValue.length < 12)}
            onClick={async () => {
              setBusy(true); setError("");
              try { await onSave(newValue,currentPassword); }
              catch (error) { setError(error instanceof Error ? error.message : "Could not save account settings."); }
              finally { setBusy(false); }
            }}
            type="button"
          >
            Save
          </button>
        </div>
    </Dialog>
  );
}
