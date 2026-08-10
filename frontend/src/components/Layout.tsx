import type { CampaignWorkspacePage, WorldCategory } from '../domain/worldbuilding';
import { campaignWorkspaceNavItems } from '../domain/worldbuilding';

type ShellProps = {
  activePage: CampaignWorkspacePage;
  campaignName: string;
  onNavigate: (page: CampaignWorkspacePage) => void;
  onBackToCampaigns: () => void;
  children: React.ReactNode;
};

export function AppShell({ activePage, campaignName, onNavigate, onBackToCampaigns, children }: ShellProps) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <span className="eyebrow">Campaign Workspace</span>
          <h1>{campaignName}</h1>
          <p>AI can propose. The Game Master decides what becomes canon.</p>
          <button className="secondary wide-button" onClick={onBackToCampaigns} type="button">
            ← All campaigns
          </button>
        </div>
        <nav className="nav-list" aria-label="Campaign workspace pages">
          {campaignWorkspaceNavItems.map((item) => (
            <button
              aria-current={activePage === item.page ? 'page' : undefined}
              className={`nav-item ${activePage === item.page ? 'active' : ''}`}
              key={item.page}
              onClick={() => onNavigate(item.page)}
              type="button"
            >
              <strong>{item.label}</strong>
              <span>{item.description}</span>
            </button>
          ))}
        </nav>
      </aside>
      <main className="page-panel">{children}</main>
    </div>
  );
}

export function PageHeader({ kicker, title, body }: { kicker: string; title: string; body: string }) {
  return (
    <header className="page-header">
      <span className="eyebrow">{kicker}</span>
      <h2>{title}</h2>
      <p>{body}</p>
    </header>
  );
}

export function StatCard({ label, value, tone = 'default' }: { label: string; value: string; tone?: 'default' | 'warn' | 'good' }) {
  return (
    <article className={`stat-card ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

export function CategoryPill({ category, active, onClick }: { category: WorldCategory; active: boolean; onClick: () => void }) {
  return (
    <button className={`category-pill ${active ? 'active' : ''}`} onClick={onClick} type="button">
      {category.label}
    </button>
  );
}
