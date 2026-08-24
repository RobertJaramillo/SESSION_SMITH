import { useEffect, useState } from "react";
import { updateCampaign } from "../../api/client";
import { PageHeader } from "../../components/Layout";
import {
  getCampaignWorkspace,
  type CampaignSummary,
} from "../../domain/worldbuilding";

export function CampaignSettingsPage({
  campaign,
}: {
  campaign: CampaignSummary;
}) {
  const [status, setStatus] = useState("");
  const [confirmingArchive, setConfirmingArchive] = useState(false);
  const [name, setName] = useState(campaign.name);
  const [visibility, setVisibility] = useState("private");
  const [model, setModel] = useState("balanced");
  const [saving, setSaving] = useState(false);
  const saveSettings = async () => {
    if (!name.trim() || saving) return;
    setSaving(true);
    try {
      await updateCampaign(campaign.campaignId, {
        name: name.trim(),
        visibility,
        model,
      });
      setStatus("Settings saved.");
    } catch {
      setStatus("Could not save settings — please try again.");
    } finally {
      setSaving(false);
    }
  };
  const exportCampaign = () => {
    const payload = {
      campaign,
      workspace: getCampaignWorkspace(campaign),
      exportedAt: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${campaign.campaignId}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    setStatus("Exported campaign JSON to your downloads.");
  };
  const confirmArchive = () => {
    setConfirmingArchive(false);
    setStatus(`"${campaign.name}" archived. (Prototype: no data was changed.)`);
  };
  return (
    <section>
      <PageHeader
        kicker="Campaign Settings"
        title="Model, visibility, and data controls"
        body="Owner controls for this campaign — choose the AI model, set who can see it, and export or archive your data."
      />
      <div className="two-column">
        <article className="card">
          <h3>Campaign</h3>
          <label>
            Campaign name
            <input
              onChange={(event) => setName(event.target.value)}
              value={name}
            />
          </label>
          <label>
            Default visibility
            <select
              onChange={(event) => setVisibility(event.target.value)}
              value={visibility}
            >
              <option value="private">Private</option>
              <option value="shared">Shared with players</option>
            </select>
          </label>
          <label>
            Model profile
            <select
              onChange={(event) => setModel(event.target.value)}
              value={model}
            >
              <option value="cheap">Cheap draft</option>
              <option value="balanced">Balanced</option>
              <option value="premium">Premium prep</option>
            </select>
          </label>
          <button
            disabled={!name.trim() || saving}
            onClick={saveSettings}
            type="button"
          >
            {saving ? "Saving…" : "Save changes"}
          </button>
        </article>
        <article className="card">
          <h3>Data controls</h3>
          <p>
            Export a JSON snapshot of this campaign, or archive it to hide it
            from your active list.
          </p>
          <div className="button-row">
            <button onClick={exportCampaign} type="button">
              Export campaign JSON
            </button>
            <button
              className="secondary"
              onClick={() => setConfirmingArchive(true)}
              type="button"
            >
              Archive campaign
            </button>
          </div>
        </article>
      </div>
      {status && (
        <p className="empty-state" role="status">
          {status}
        </p>
      )}
      {confirmingArchive && (
        <ConfirmDialog
          title="Archive campaign"
          body={`Archive "${campaign.name}"? You can restore it later.`}
          confirmLabel="Archive"
          onCancel={() => setConfirmingArchive(false)}
          onConfirm={confirmArchive}
        />
      )}
    </section>
  );
}

function ConfirmDialog({
  title,
  body,
  confirmLabel,
  onCancel,
  onConfirm,
}: {
  title: string;
  body: string;
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onCancel]);
  return (
    <div className="modal-backdrop" role="presentation">
      <section
        aria-labelledby="confirm-dialog-title"
        aria-modal="true"
        className="settings-modal setting-update-modal"
        role="dialog"
      >
        <div className="settings-modal-header">
          <div>
            <span className="eyebrow">Confirm</span>
            <h2 id="confirm-dialog-title">{title}</h2>
          </div>
          <button
            aria-label="Close dialog"
            className="modal-close-button"
            onClick={onCancel}
            type="button"
          >
            ×
          </button>
        </div>
        <div className="setting-update-body">
          <p>{body}</p>
        </div>
        <div className="settings-confirm-actions">
          <button className="secondary" onClick={onCancel} type="button">
            Cancel
          </button>
          <button onClick={onConfirm} type="button">
            {confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}
