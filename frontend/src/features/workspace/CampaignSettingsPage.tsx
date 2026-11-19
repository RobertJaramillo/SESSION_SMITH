import { useState } from "react";
import { CampaignMembersPanel } from "../../components/CampaignMembersPanel";
import { exportCampaign as downloadCampaign, updateCampaign } from "../../api/client";
import { PageHeader } from "../../components/Layout";
import {
  type CampaignSummary,
} from "../../domain/worldbuilding";

export function CampaignSettingsPage({
  campaign,
  onOwnershipTransferred,
}: {
  campaign: CampaignSummary;
  onOwnershipTransferred?: () => void;
}) {
  const [status, setStatus] = useState("");
  const [exporting, setExporting] = useState(false);
  const [name, setName] = useState(campaign.name);
  const [model, setModel] = useState(campaign.model);
  const [saving, setSaving] = useState(false);
  const saveSettings = async () => {
    if (!name.trim() || saving) return;
    setSaving(true);
    try {
      await updateCampaign(campaign.campaignId, {
        name: name.trim(),
        model,
      });
      setStatus("Settings saved.");
    } catch {
      setStatus("Could not save settings — please try again.");
    } finally {
      setSaving(false);
    }
  };
  const exportCampaign = async () => {
    if (exporting) return;
    setExporting(true);
    try {
      const payload = await downloadCampaign(campaign.campaignId);
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
      setStatus("Exported saved campaign data to your downloads.");
    } catch { setStatus("Could not export campaign data. Please try again."); }
    finally { setExporting(false); }
  };
  return (
    <section>
      <PageHeader
        kicker="Campaign Settings"
        title="Campaign settings and data controls"
        body="Manage campaign members, choose the AI model, and export your campaign data."
      />
      <CampaignMembersPanel campaignId={campaign.campaignId} onTransferred={onOwnershipTransferred} />
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
            Model profile
            <select
              onChange={(event) =>
                setModel(event.target.value as CampaignSummary["model"])
              }
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
            Export a JSON snapshot of the saved campaign data.
          </p>
          <div className="button-row">
            <button onClick={() => void exportCampaign()} disabled={exporting} type="button">
              Export campaign JSON
            </button>

          </div>
        </article>
      </div>
      {status && (
        <p className="empty-state" role="status">
          {status}
        </p>
      )}

    </section>
  );
}
