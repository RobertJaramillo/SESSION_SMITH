import { useState } from "react";
import { updateAccount, type Account } from "../api/client";
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
      helper: "Primary address used for account notices and sign in.",
      editable: true,
      inputType: "email",
    },
    {
      id: "password",
      label: "Password reset",
      value: settingValues.password,
      helper: "Enter and confirm a new password before saving.",
      editable: true,
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
    <div className="modal-backdrop" role="presentation">
      <section
        aria-labelledby="settings-modal-title"
        aria-modal="true"
        className="settings-modal"
        role="dialog"
      >
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
          {settingsRows.map((row) => (
            <article className="settings-option" key={row.id}>
              <div>
                <span>{row.label}</span>
                <strong>{row.value}</strong>
                <p>{row.helper}</p>
              </div>
              {row.editable ? (
                <div
                  className="settings-option-actions"
                  aria-label={`${row.label} actions`}
                >
                  <button onClick={() => setEditingSetting(row)} type="button">
                    Update
                  </button>
                </div>
              ) : (
                <span className="settings-readonly-badge">Current plan</span>
              )}
            </article>
          ))}
        </div>
      </section>
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
    </div>
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
    <div className="modal-backdrop nested-modal-backdrop" role="presentation">
      <section
        aria-labelledby="setting-update-title"
        aria-modal="true"
        className="settings-modal setting-update-modal"
        role="dialog"
      >
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
      </section>
    </div>
  );
}
