import { useEffect, useRef, useState } from "react";
import { createCampaign, getCampaignSections } from "../api/client";
import { CreateCampaignDialog } from "../components/CreateCampaignDialog";
import { SettingsModal } from "../components/SettingsModal";
import type {
  CampaignListSection,
  CampaignSummary,
} from "../domain/worldbuilding";
import type { AIProvider } from "../types/providers";

export function CampaignDashboardPage({
  onOpenCampaign,
  onLogout,
  provider,
  onManageProvider,
}: {
  onOpenCampaign: (campaign: CampaignSummary) => void;
  onLogout: () => void;
  provider: AIProvider;
  onManageProvider: () => void;
}) {
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [sections, setSections] = useState<CampaignListSection[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const profileMenuRef = useRef<HTMLDivElement>(null);
  const accountName = "DrowKiroth";
  const accountEmail = "drowkiroth@example.com";
  const accountTier = "Private Beta GM";
  useEffect(() => {
    let active = true;
    getCampaignSections()
      .then((data) => {
        if (active) {
          setSections(data);
          setLoadError("");
          setLoading(false);
        }
      })
      .catch(() => {
        if (active) {
          setLoadError("Could not load your campaigns.");
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    if (!profileMenuOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (
        profileMenuRef.current &&
        !profileMenuRef.current.contains(event.target as Node)
      )
        setProfileMenuOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setProfileMenuOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [profileMenuOpen]);
  return (
    <main className="campaign-dashboard streamlined-dashboard">
      <header className="dashboard-header">
        <div className="dashboard-header-bar">
          <div className="profile-menu-wrap" ref={profileMenuRef}>
            <button
              aria-expanded={profileMenuOpen}
              aria-haspopup="menu"
              aria-label="Open profile menu"
              className="profile-icon-button"
              onClick={() => setProfileMenuOpen((open) => !open)}
              type="button"
            >
              DK
            </button>
            {profileMenuOpen && (
              <div className="profile-menu" role="menu">
                <div className="profile-menu-account">
                  <strong>{accountName}</strong>
                  <span>{accountTier}</span>
                </div>
                <button
                  onClick={() => {
                    setSettingsOpen(true);
                    setProfileMenuOpen(false);
                  }}
                  role="menuitem"
                  type="button"
                >
                  Settings
                </button>
                <button
                  className="secondary"
                  onClick={onLogout}
                  role="menuitem"
                  type="button"
                >
                  Log out
                </button>
              </div>
            )}
          </div>
          <div className="dashboard-account-inline">
            <span className="eyebrow">Signed in as</span>
            <h2 className="account-name">{accountName}</h2>
          </div>
          <button
            className="create-campaign-button"
            onClick={() => setCreateOpen(true)}
            type="button"
          >
            + Create campaign
          </button>
        </div>
        <div className="dashboard-titleblock">
          <h1>Your campaigns</h1>
          <p>Choose a world to open, or start a new campaign.</p>
        </div>
      </header>
      {loadError && (
        <p className="settings-validation-message" role="status">
          {loadError}
        </p>
      )}
      {loading && !loadError && (
        <p className="empty-state" role="status">
          Loading your campaigns…
        </p>
      )}
      <section className="dashboard-columns" aria-label="Campaign groups">
        {sections.map((section) => (
          <section className="dashboard-column" key={section.id}>
            <div className="dashboard-column-header">
              <div>
                <h2>{section.title}</h2>
                <p>{section.subtitle}</p>
              </div>
              <span className="section-count">{section.campaigns.length}</span>
            </div>
            {section.campaigns.length === 0 && (
              <p className="empty-column">No campaigns here yet.</p>
            )}
            <div className="vertical-tile-list">
              {section.campaigns.map((campaign, index) => (
                <article
                  className="campaign-tile"
                  key={`${section.id}-${campaign.campaignId}-${index}`}
                >
                  <div className="campaign-tile-top">
                    <div className="campaign-sigil" aria-hidden="true">
                      {campaign.name
                        .split(" ")
                        .slice(0, 2)
                        .map((word) => word[0])
                        .join("")}
                    </div>
                    <div>
                      <h3>{campaign.name}</h3>
                      <span
                        className={`status-badge status-${campaign.status}`}
                      >
                        {campaign.status}
                      </span>
                    </div>
                  </div>
                  <p>{campaign.description}</p>
                  <div className="campaign-tile-meta">
                    <span>Session {campaign.lastSessionNumber}</span>
                    <span>{campaign.nextSessionLabel}</span>
                  </div>
                  <button
                    onClick={() => onOpenCampaign(campaign)}
                    type="button"
                  >
                    Open campaign
                  </button>
                </article>
              ))}
            </div>
          </section>
        ))}
      </section>
      {settingsOpen && (
        <SettingsModal
          accountEmail={accountEmail}
          accountName={accountName}
          accountTier={accountTier}
          onClose={() => setSettingsOpen(false)}
          provider={provider}
          onManageProvider={() => {
            setSettingsOpen(false);
            onManageProvider();
          }}
        />
      )}
      {createOpen && (
        <CreateCampaignDialog
          onClose={() => setCreateOpen(false)}
          onCreate={async (name, description) => {
            const created = await createCampaign({ name, description });
            setCreateOpen(false);
            onOpenCampaign(created);
          }}
        />
      )}
    </main>
  );
}
