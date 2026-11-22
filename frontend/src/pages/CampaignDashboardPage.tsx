import { useEffect, useRef, useState } from "react";
import { ShareCampaignDialog } from "../components/ShareCampaignDialog";
import { FriendsPanel } from "../components/FriendsPanel";
import { createCampaign, getCampaignSections, type Account } from "../api/client";
import { CreateCampaignDialog } from "../components/CreateCampaignDialog";
import { SettingsModal } from "../components/SettingsModal";
import type {
  CampaignListSection,
  CampaignSummary,
} from "../domain/worldbuilding";
import type { AIProvider } from "../types/providers";

export function CampaignDashboardPage({
  account,
  onAccountUpdated,
  onOpenCampaign,
  onLogout,
  provider,
  onManageProvider,
}: {
  account: Account;
  onAccountUpdated: (account: Account) => void;
  onOpenCampaign: (campaign: CampaignSummary) => void;
  onLogout: () => void;
  provider: AIProvider;
  onManageProvider: () => void;
}) {
  const [sharingCampaign, setSharingCampaign] = useState<CampaignSummary | null>(null);
  const [socialOpen, setSocialOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [sections, setSections] = useState<CampaignListSection[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const partyDropdownRef = useRef<HTMLDivElement>(null);
  const friendsButtonRef = useRef<HTMLButtonElement>(null);
  const profileMenuRef = useRef<HTMLDivElement>(null);
  const accountName = account.name;
  const accountEmail = account.email;
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
  }, [refreshKey]);
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
  useEffect(() => {
    if (!socialOpen) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!partyDropdownRef.current?.contains(event.target as Node)) setSocialOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setSocialOpen(false); friendsButtonRef.current?.focus(); }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [socialOpen]);
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
              {account.name.slice(0, 2).toUpperCase()}
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
          <div className="party-dropdown" ref={partyDropdownRef}>
            <button ref={friendsButtonRef} type="button" className={`dashboard-friends-button${socialOpen ? " is-active" : ""}`} aria-expanded={socialOpen} aria-controls="party-dropdown-content" onClick={() => setSocialOpen(!socialOpen)}>
              Friends & invitations
              <svg className="party-dropdown-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
            </button>
            {socialOpen && <div id="party-dropdown-content" className="party-dropdown-content">
              <FriendsPanel onJoined={() => setRefreshKey(key => key + 1)} />
            </div>}
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
                    {campaign.role === "owner" && (
                      <button className="campaign-share-button" type="button" aria-label={`Share ${campaign.name}`} title="Share campaign" onClick={() => setSharingCampaign(campaign)}>
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                          <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
                          <path d="m8.6 10.5 6.8-4M8.6 13.5l6.8 4" />
                        </svg>
                        Share
                      </button>
                    )}
                  </div>
                  <p>{campaign.description}</p>
                  <div className="campaign-ownership"><span>Owned by <strong>{campaign.owner?.name ?? (campaign.role === "owner" ? "you" : "Campaign owner")}</strong></span><span className={`social-role social-role-${campaign.role}`}>{campaign.role}</span></div>
                  <div className="campaign-players" aria-label={`Players in ${campaign.name}`}>
                    <span className="campaign-players-label">{campaign.players?.length ?? 0} {(campaign.players?.length ?? 0) === 1 ? "player" : "players"}</span>
                    {campaign.players?.length ? <ul className="campaign-player-list">
                      {campaign.players.map(player => <li key={player.id}>
                        <span className="campaign-player-avatar" aria-hidden="true">{player.name.trim().split(/\s+/).slice(0, 2).map(word => word[0]).join("").toUpperCase()}</span>
                        <span>{player.name}</span>
                      </li>)}
                    </ul> : <span className="campaign-players-empty">No players yet</span>}
                  </div>
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
      {sharingCampaign && <ShareCampaignDialog campaign={sharingCampaign} onClose={() => { setSharingCampaign(null); setRefreshKey(key => key + 1); }} />}
      {settingsOpen && (
        <SettingsModal
          onAccountUpdated={onAccountUpdated}
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
