import type { CampaignListSection, CampaignSummary, CampaignWorkspace, CampaignProposal } from "../domain/worldbuilding";

export const CAMPAIGN_LISTS: CampaignListSection[] = [
  {
    id: "owned",
    title: "Owned",
    subtitle:
      "Campaign worlds where you control settings, canon, players, and AI memory.",
    campaigns: [
      {
        campaignId: "campaign_ashes_of_kestrel_vale",
        name: "Ashes of Kestrel Vale",
        role: "owner",
        status: "active",
        lastSessionNumber: 10,
        nextSessionLabel: "Session 11 prep needed",
        updatedAt: "2026-07-10T21:00:00Z",
        description:
          "Dark political fantasy about oath law, buried history, and the Flood of Bells.",
        worldStatus: "sealed",
        visibility: "private",
        model: "balanced",
      },
      {
        campaignId: "campaign_glass_moon_exile",
        name: "Glass Moon Exile",
        role: "owner",
        status: "planning",
        lastSessionNumber: 0,
        nextSessionLabel: "Initial world setup incomplete",
        updatedAt: "2026-07-07T18:20:00Z",
        description:
          "Planar survival campaign draft waiting for session 0 worldbuilding notes.",
        worldStatus: "draft",
        visibility: "private",
        model: "balanced",
      },
    ],
  },
  {
    id: "shared",
    title: "Shared",
    subtitle:
      "Campaigns another GM invited you to view or contribute to as a player or collaborator.",
    campaigns: [
      {
        campaignId: "campaign_cinder_archive",
        name: "The Cinder Archive",
        role: "player",
        status: "active",
        lastSessionNumber: 4,
        nextSessionLabel: "Awaiting GM notes",
        updatedAt: "2026-07-08T02:15:00Z",
        description:
          "Library-city mystery shared with you as a player character contributor.",
        worldStatus: "sealed",
        visibility: "shared",
        model: "balanced",
      },
    ],
  },
  {
    id: "running",
    title: "In progress",
    subtitle: "Tables you are actively running or preparing right now.",
    campaigns: [
      {
        campaignId: "campaign_ashes_of_kestrel_vale",
        name: "Ashes of Kestrel Vale",
        role: "gm",
        status: "active",
        lastSessionNumber: 10,
        nextSessionLabel: "Run Session 11 this week",
        updatedAt: "2026-07-10T21:00:00Z",
        description:
          "Current live table with pending review proposals from sessions 9 and 10.",
        worldStatus: "sealed",
        visibility: "private",
        model: "balanced",
      },
    ],
  },
];

const CAMPAIGN_WORKSPACES: Record<string, CampaignWorkspace> = {
  campaign_ashes_of_kestrel_vale: {
    sessionDocCount: 11,
    proposalsWaiting: 2,
    canonMemoryCount: 132,
    recentActivity: [
      {
        actor: "Session 10",
        detail:
          "Bell Vault records were submitted as a separate session JSON document.",
      },
      { actor: "AI Worker", detail: "Created 2 proposals needing GM review." },
      { actor: "GM", detail: "Last opened this campaign workspace today." },
    ],
    proposals: [
      {
        title: "The Iron Court controls river taxes",
        category: "Government Organizations",
        confidence: "High",
        conflicts: [
          "Existing canon already states the Iron Court sets and enforces river-crossing tariffs — check this isn’t a duplicate or a scope change before approving.",
        ],
      },
      {
        title: "Leyline magic requires witnessed vows",
        category: "Magic Systems",
        confidence: "Medium",
      },
      {
        title: "Kestrel Vale food prices doubled after the ash storm",
        category: "Economy",
        confidence: "High",
      },
    ],
    prepGoal: "Recover the relic beneath the drowned bell tower",
    prepMemoriesHint:
      "Approved NPCs, player character hooks, Kestrel Vale regions, recent faction changes",
    prepOutline: [
      "Cold open: ash rain over the vale.",
      "Three clues pointing to the bell tower vault.",
      "Faction pressure from the Iron Court.",
      "Player-specific complications and rewards.",
    ],
  },
};

// Mocked stand-in for the AI worker's extraction step. In the real system the
// Go worker sends notes to the LLM and returns validated structured output;
// here we derive plausible proposals from the note text so the submit -> review
// loop is demonstrable without a backend.
const KEYWORD_CATEGORY: Record<string, string> = {
  tax: "Economy",
  price: "Economy",
  trade: "Economy",
  coin: "Economy",
  tariff: "Economy",
  oath: "Magic Systems",
  magic: "Magic Systems",
  spell: "Magic Systems",
  ley: "Magic Systems",
  ritual: "Magic Systems",
  court: "Government Organizations",
  council: "Government Organizations",
  guard: "Government Organizations",
  guild: "Non-Government Organizations",
  cult: "Non-Government Organizations",
  temple: "Non-Government Organizations",
  law: "Laws",
  ban: "Laws",
  relic: "World Artifacts",
  artifact: "World Artifacts",
  vault: "World Artifacts",
  region: "Regions",
  city: "Regions",
  harbor: "Regions",
  vale: "Regions",
};

function guessCategory(text: string): string {
  const lower = text.toLowerCase();
  for (const keyword of Object.keys(KEYWORD_CATEGORY)) {
    if (lower.includes(keyword)) return KEYWORD_CATEGORY[keyword];
  }
  return "NPCs";
}

export function extractProposalsFromNote(note: string): CampaignProposal[] {
  const sentences = note
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length > 12);
  const source =
    sentences.length > 0 ? sentences : [note.trim()].filter(Boolean);
  return source.slice(0, 3).map((sentence) => ({
    title: sentence.length > 90 ? `${sentence.slice(0, 88)}…` : sentence,
    category: guessCategory(sentence),
    confidence:
      sentence.length > 80 ? "High" : sentence.length > 40 ? "Medium" : "Low",
  }));
}

// Mocked stand-in for the AI prep-generation job. The real system would pull
// approved canon and call the LLM; here we assemble a plausible outline from
// the GM's goal and tone so the "Queue AI prep job" action is demonstrable.
export function buildPrepOutline(input: {
  goal: string;
  tone: string;
}): string[] {
  const goal = input.goal.trim() || "the session objective";
  const opener: Record<string, string> = {
    wonder: "Open on an image of awe that pulls the party in.",
    danger: "Open on immediate tension — something is already going wrong.",
    intrigue: "Open on a secret half-revealed, inviting questions.",
  };
  return [
    opener[input.tone] ?? "Open on a strong hook.",
    `Establish the stakes around ${goal}.`,
    "Introduce a complication drawn from approved canon.",
    `Escalate toward ${goal} as a faction or NPC pushes back.`,
    "Close on a choice that sets up the next session.",
  ];
}

export function getCampaignWorkspace(
  campaign: CampaignSummary,
): CampaignWorkspace {
  return (
    CAMPAIGN_WORKSPACES[campaign.campaignId] ?? {
      sessionDocCount: campaign.lastSessionNumber,
      proposalsWaiting: 0,
      canonMemoryCount: 0,
      recentActivity: [],
      proposals: [],
      prepGoal: "",
      prepMemoriesHint: "",
      prepOutline: [],
      latestNotesTitle: "",
      latestNotesBody: "",
    }
  );
}

