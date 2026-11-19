import { Dialog } from "./Dialog";
import { CampaignMembersPanel } from "./CampaignMembersPanel";
import type { CampaignSummary } from "../domain/worldbuilding";

export function ShareCampaignDialog({ campaign, onClose }: {
  campaign: CampaignSummary;
  onClose: () => void;
}) {
  return (
    <Dialog className="share-campaign-dialog" labelledBy="share-campaign-title" onClose={onClose}>
      <div className="settings-modal-header">
        <div>
          <span className="eyebrow">Share your world</span>
          <h2 id="share-campaign-title">Share {campaign.name}</h2>
          <p>Invite a friend or enter an email to welcome someone to your campaign.</p>
        </div>
        <button autoFocus type="button" className="modal-close-button" aria-label="Close sharing" onClick={onClose}>×</button>
      </div>
      <CampaignMembersPanel campaignId={campaign.campaignId} onTransferred={onClose} />
    </Dialog>
  );
}
