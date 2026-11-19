import { Dialog } from "./Dialog";
import { useState } from "react";

export function CreateCampaignDialog({
  onClose,
  onCreate,
}: {
  onClose: () => void;
  onCreate: (name: string, description: string) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const submit = async () => {
    if (!name.trim() || saving) return;
    setSaving(true);
    try {
      await onCreate(name.trim(), description.trim());
    } catch {
      setSaving(false);
    }
  };
  return (
    <Dialog labelledBy="create-campaign-title" onClose={onClose} className="settings-modal setting-update-modal">
        <div className="settings-modal-header">
          <div>
            <span className="eyebrow">New campaign</span>
            <h2 id="create-campaign-title">Create a campaign</h2>
          </div>
          <button
            aria-label="Close dialog"
            className="modal-close-button"
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </div>
        <div className="setting-update-body">
          <label>
            Campaign name
            <input
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Shadows of Vaeloria"
              value={name}
            />
          </label>
          <label>
            Description
            <textarea
              onChange={(event) => setDescription(event.target.value)}
              placeholder="A one-line premise for this world."
              value={description}
            />
          </label>
        </div>
        <div className="settings-confirm-actions">
          <button className="secondary" onClick={onClose} type="button">
            Cancel
          </button>
          <button
            disabled={!name.trim() || saving}
            onClick={submit}
            type="button"
          >
            {saving ? "Creating…" : "Create campaign"}
          </button>
        </div>
    </Dialog>
  );
}
