export type CampaignDashboardPage = 'campaign-dashboard';
export type CampaignWorkspacePage =
  | 'campaign-overview'
  | 'world-builder'
  | 'session-prep'
  | 'notes'
  | 'review-queue'
  | 'canon-browser'
  | 'settings';
export type PageId = CampaignDashboardPage | CampaignWorkspacePage;

export type WorldCategoryId =
  | 'economy'
  | 'politics'
  | 'magic_systems'
  | 'world_artifacts'
  | 'npcs'
  | 'government_organizations'
  | 'non_government_organizations'
  | 'laws'
  | 'inhabitants'
  | 'ecosystems'
  | 'cataclysmic_events'
  | 'general_overview'
  | 'races'
  | 'jobs_and_roles'
  | 'technology_systems'
  | 'regions'
  | 'era'
  | 'player_characters';

export type WorldCategory = {
  id: WorldCategoryId;
  label: string;
  prompt: string;
  examples: string[];
};

export const WORLD_CATEGORIES: WorldCategory[] = [
  { id: 'economy', label: 'Economy', prompt: 'Trade, currency, scarcity, wealth, taxes, labor, black markets.', examples: ['coinage and barter', 'trade routes', 'scarce goods'] },
  { id: 'politics', label: 'Politics', prompt: 'Power blocs, alliances, succession, public sentiment, conflicts.', examples: ['current ruler', 'succession crisis', 'rebel factions'] },
  { id: 'magic_systems', label: 'Magic Systems', prompt: 'Rules, limits, costs, schools, taboo magic, magical institutions.', examples: ['spell costs', 'leyline rules', 'forbidden rituals'] },
  { id: 'world_artifacts', label: 'World Artifacts', prompt: 'Legendary objects, relics, cursed items, historic discoveries.', examples: ['artifact origin', 'current holder', 'known powers'] },
  { id: 'npcs', label: 'NPCs', prompt: 'Named characters, motives, relationships, secrets, voice notes.', examples: ['merchant ally', 'hidden agenda', 'relationship map'] },
  { id: 'government_organizations', label: 'Government Organizations', prompt: 'States, ministries, courts, militaries, law enforcement, offices.', examples: ['royal court', 'border guard', 'city council'] },
  { id: 'non_government_organizations', label: 'Non-Government Organizations', prompt: 'Guilds, cults, companies, churches, academic orders, crime groups.', examples: ['thieves guild', 'merchant cartel', 'temple order'] },
  { id: 'laws', label: 'Laws', prompt: 'Written law, customs, punishments, loopholes, enforcement gaps.', examples: ['weapon bans', 'trial process', 'tax law'] },
  { id: 'inhabitants', label: 'Inhabitants', prompt: 'People, demographics, social classes, daily life, languages.', examples: ['commoners', 'minorities', 'regional dialects'] },
  { id: 'ecosystems', label: 'Ecosystems', prompt: 'Biomes, monsters, weather, food chains, environmental hazards.', examples: ['swamp ecology', 'apex predators', 'seasonal storms'] },
  { id: 'cataclysmic_events', label: 'Cataclysmic Events', prompt: 'Past disasters, wars, plagues, divine events, world-changing magic.', examples: ['fallen moon', 'great flood', 'god war'] },
  { id: 'general_overview', label: 'General Overview', prompt: 'High-level world premise, tone, core conflicts, elevator pitch.', examples: ['world tone', 'campaign promise', 'central tension'] },
  { id: 'races', label: 'Races', prompt: 'Ancestries, cultures, histories, tensions, abilities, stereotypes.', examples: ['dwarven diaspora', 'elf courts', 'hybrid ancestry'] },
  { id: 'jobs_and_roles', label: 'Jobs and Roles', prompt: 'Professions, social duties, adventuring roles, class/caste function.', examples: ['monster wardens', 'sky sailors', 'scribe caste'] },
  { id: 'technology_systems', label: 'Technology Systems', prompt: 'Tools, transport, weapons, medicine, industry, communication.', examples: ['airships', 'printing press', 'alchemical engines'] },
  { id: 'regions', label: 'Regions', prompt: 'Places, borders, landmarks, settlements, regional conflicts.', examples: ['frontier valley', 'capital ward', 'lost province'] },
  { id: 'era', label: 'Era', prompt: 'Time period, calendar, recent history, ages, timeline anchors.', examples: ['third empire', 'post-war decade', 'calendar system'] },
  { id: 'player_characters', label: 'Player Characters', prompt: 'PC backstories, goals, bonds, secrets, canon-changing choices.', examples: ['family tie', 'personal quest', 'session decision'] },
];

export type NavItem = { page: CampaignWorkspacePage; label: string; description: string };

export const campaignWorkspaceNavItems: NavItem[] = [
  { page: 'campaign-overview', label: 'Overview', description: 'Campaign status, sessions, and next actions.' },
  { page: 'world-builder', label: 'World Builder', description: 'Category tabs for session documents.' },
  { page: 'session-prep', label: 'Session Prep', description: 'Generate and edit next-session material.' },
  { page: 'notes', label: 'Session Notes', description: 'Submit notes as separate session JSON.' },
  { page: 'review-queue', label: 'Review Queue', description: 'Approve, edit, or reject AI proposals.' },
  { page: 'canon-browser', label: 'Canon Browser', description: 'Search approved memory and RAG chunks.' },
  { page: 'settings', label: 'Settings', description: 'Campaign, model, quota, export controls.' },
];

export const navItems = campaignWorkspaceNavItems;

export type CampaignSummary = {
  campaignId: string;
  name: string;
  role: 'owner' | 'gm' | 'player' | 'viewer';
  status: 'active' | 'planning' | 'paused';
  lastSessionNumber: number;
  nextSessionLabel: string;
  updatedAt: string;
  description: string;
  // World-building lifecycle: 'draft' = World Builder editable; 'sealed' = world
  // built and read-only, further change comes only from session notes.
  worldStatus: 'draft' | 'sealed';
};

export type CampaignListSection = {
  id: 'owned' | 'shared' | 'running';
  title: string;
  subtitle: string;
  campaigns: CampaignSummary[];
};

export const CAMPAIGN_LISTS: CampaignListSection[] = [
  {
    id: 'owned',
    title: 'Owned',
    subtitle: 'Campaign worlds where you control settings, canon, players, and AI memory.',
    campaigns: [
      {
        campaignId: 'campaign_ashes_of_kestrel_vale',
        name: 'Ashes of Kestrel Vale',
        role: 'owner',
        status: 'active',
        lastSessionNumber: 10,
        nextSessionLabel: 'Session 11 prep needed',
        updatedAt: '2026-07-10T21:00:00Z',
        description: 'Dark political fantasy about oath law, buried history, and the Flood of Bells.',
        worldStatus: 'sealed',
      },
      {
        campaignId: 'campaign_glass_moon_exile',
        name: 'Glass Moon Exile',
        role: 'owner',
        status: 'planning',
        lastSessionNumber: 0,
        nextSessionLabel: 'Initial world setup incomplete',
        updatedAt: '2026-07-07T18:20:00Z',
        description: 'Planar survival campaign draft waiting for session 0 worldbuilding notes.',
        worldStatus: 'draft',
      },
    ],
  },
  {
    id: 'shared',
    title: 'Shared',
    subtitle: 'Campaigns another GM invited you to view or contribute to as a player or collaborator.',
    campaigns: [
      {
        campaignId: 'campaign_cinder_archive',
        name: 'The Cinder Archive',
        role: 'player',
        status: 'active',
        lastSessionNumber: 4,
        nextSessionLabel: 'Awaiting GM notes',
        updatedAt: '2026-07-08T02:15:00Z',
        description: 'Library-city mystery shared with you as a player character contributor.',
        worldStatus: 'sealed',
      },
    ],
  },
  {
    id: 'running',
    title: 'In progress',
    subtitle: 'Tables you are actively running or preparing right now.',
    campaigns: [
      {
        campaignId: 'campaign_ashes_of_kestrel_vale',
        name: 'Ashes of Kestrel Vale',
        role: 'gm',
        status: 'active',
        lastSessionNumber: 10,
        nextSessionLabel: 'Run Session 11 this week',
        updatedAt: '2026-07-10T21:00:00Z',
        description: 'Current live table with pending review proposals from sessions 9 and 10.',
        worldStatus: 'sealed',
      },
    ],
  },
];

export type SessionEntry = {
  entry_id: string;
  note: string;
  date_created: string;
  last_updated: string;
  summary: string;
  entry_tags: string[];
};

export function buildSessionEntry(input: {
  entryId: string;
  note: string;
  createdAt: string;
  lastUpdated?: string;
  summary: string;
  tags: string[];
}): SessionEntry {
  return {
    entry_id: input.entryId,
    note: input.note.trim(),
    date_created: input.createdAt,
    last_updated: input.lastUpdated ?? input.createdAt,
    summary: input.summary.trim(),
    entry_tags: input.tags.map((tag) => tag.trim()).filter(Boolean),
  };
}

export type CampaignProposal = {
  title: string;
  category: string;
  confidence: 'High' | 'Medium' | 'Low';
  // Contradictions the AI flagged against established canon at extraction time.
  conflicts?: string[];
};

export type CampaignActivity = {
  actor: string;
  detail: string;
};

// Mocked per-campaign workspace content. Everything a workspace page renders
// comes from here so opening a different campaign shows that campaign's data
// (or empty states) rather than one hardcoded campaign's lore.
export type CampaignWorkspace = {
  sessionDocCount: number;
  proposalsWaiting: number;
  canonMemoryCount: number;
  recentActivity: CampaignActivity[];
  proposals: CampaignProposal[];
  prepGoal: string;
  prepMemoriesHint: string;
  prepOutline: string[];
};

const CAMPAIGN_WORKSPACES: Record<string, CampaignWorkspace> = {
  campaign_ashes_of_kestrel_vale: {
    sessionDocCount: 11,
    proposalsWaiting: 2,
    canonMemoryCount: 132,
    recentActivity: [
      { actor: 'Session 10', detail: 'Bell Vault records were submitted as a separate session JSON document.' },
      { actor: 'AI Worker', detail: 'Created 2 proposals needing GM review.' },
      { actor: 'GM', detail: 'Last opened this campaign workspace today.' },
    ],
    proposals: [
      {
        title: 'The Iron Court controls river taxes',
        category: 'Government Organizations',
        confidence: 'High',
        conflicts: ['Existing canon already states the Iron Court sets and enforces river-crossing tariffs — check this isn’t a duplicate or a scope change before approving.'],
      },
      { title: 'Leyline magic requires witnessed vows', category: 'Magic Systems', confidence: 'Medium' },
      { title: 'Kestrel Vale food prices doubled after the ash storm', category: 'Economy', confidence: 'High' },
    ],
    prepGoal: 'Recover the relic beneath the drowned bell tower',
    prepMemoriesHint: 'Approved NPCs, player character hooks, Kestrel Vale regions, recent faction changes',
    prepOutline: [
      'Cold open: ash rain over the vale.',
      'Three clues pointing to the bell tower vault.',
      'Faction pressure from the Iron Court.',
      'Player-specific complications and rewards.',
    ],
  },
};

// Mocked stand-in for the AI worker's extraction step. In the real system the
// Go worker sends notes to the LLM and returns validated structured output;
// here we derive plausible proposals from the note text so the submit -> review
// loop is demonstrable without a backend.
const KEYWORD_CATEGORY: Record<string, string> = {
  tax: 'Economy', price: 'Economy', trade: 'Economy', coin: 'Economy', tariff: 'Economy',
  oath: 'Magic Systems', magic: 'Magic Systems', spell: 'Magic Systems', ley: 'Magic Systems', ritual: 'Magic Systems',
  court: 'Government Organizations', council: 'Government Organizations', guard: 'Government Organizations',
  guild: 'Non-Government Organizations', cult: 'Non-Government Organizations', temple: 'Non-Government Organizations',
  law: 'Laws', ban: 'Laws',
  relic: 'World Artifacts', artifact: 'World Artifacts', vault: 'World Artifacts',
  region: 'Regions', city: 'Regions', harbor: 'Regions', vale: 'Regions',
};

function guessCategory(text: string): string {
  const lower = text.toLowerCase();
  for (const keyword of Object.keys(KEYWORD_CATEGORY)) {
    if (lower.includes(keyword)) return KEYWORD_CATEGORY[keyword];
  }
  return 'NPCs';
}

export function extractProposalsFromNote(note: string): CampaignProposal[] {
  const sentences = note
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length > 12);
  const source = sentences.length > 0 ? sentences : [note.trim()].filter(Boolean);
  return source.slice(0, 3).map((sentence) => ({
    title: sentence.length > 90 ? `${sentence.slice(0, 88)}…` : sentence,
    category: guessCategory(sentence),
    confidence: sentence.length > 80 ? 'High' : sentence.length > 40 ? 'Medium' : 'Low',
  }));
}

// Mocked stand-in for the AI prep-generation job. The real system would pull
// approved canon and call the LLM; here we assemble a plausible outline from
// the GM's goal and tone so the "Queue AI prep job" action is demonstrable.
export function buildPrepOutline(input: { goal: string; tone: string }): string[] {
  const goal = input.goal.trim() || 'the session objective';
  const opener: Record<string, string> = {
    wonder: 'Open on an image of awe that pulls the party in.',
    danger: 'Open on immediate tension — something is already going wrong.',
    intrigue: 'Open on a secret half-revealed, inviting questions.',
  };
  return [
    opener[input.tone] ?? 'Open on a strong hook.',
    `Establish the stakes around ${goal}.`,
    'Introduce a complication drawn from approved canon.',
    `Escalate toward ${goal} as a faction or NPC pushes back.`,
    'Close on a choice that sets up the next session.',
  ];
}

export function getCampaignWorkspace(campaign: CampaignSummary): CampaignWorkspace {
  return (
    CAMPAIGN_WORKSPACES[campaign.campaignId] ?? {
      sessionDocCount: campaign.lastSessionNumber,
      proposalsWaiting: 0,
      canonMemoryCount: 0,
      recentActivity: [],
      proposals: [],
      prepGoal: '',
      prepMemoriesHint: '',
      prepOutline: [],
      latestNotesTitle: '',
      latestNotesBody: '',
    }
  );
}

// World completeness — the definition of a "gap" the World Builder carousel and
// the AI gap-fill act on. A category is BUILT if it has at least one saved entry
// (matched by WorldCategoryId) OR one approved canon event (matched by label);
// otherwise it is a gap. Pure so tests/domain can share it with the UI.
export type CategoryCompleteness = {
  category: WorldCategory;
  entryCount: number;
  canonCount: number;
  built: boolean;
};

export type WorldCompleteness = {
  perCategory: CategoryCompleteness[];
  builtCount: number;
  gaps: WorldCategory[];
};

export function worldCompleteness(
  entries: { category: string }[],
  canonEvents: { category: string }[],
): WorldCompleteness {
  const entriesByCategoryId = new Map<string, number>();
  entries.forEach((entry) => {
    entriesByCategoryId.set(entry.category, (entriesByCategoryId.get(entry.category) ?? 0) + 1);
  });
  const canonByLabel = new Map<string, number>();
  canonEvents.forEach((event) => {
    const key = event.category.trim().toLowerCase();
    canonByLabel.set(key, (canonByLabel.get(key) ?? 0) + 1);
  });
  const perCategory = WORLD_CATEGORIES.map((category) => {
    const entryCount = entriesByCategoryId.get(category.id) ?? 0;
    const canonCount = canonByLabel.get(category.label.toLowerCase()) ?? 0;
    return { category, entryCount, canonCount, built: entryCount > 0 || canonCount > 0 };
  });
  return {
    perCategory,
    builtCount: perCategory.filter((item) => item.built).length,
    gaps: perCategory.filter((item) => !item.built).map((item) => item.category),
  };
}
