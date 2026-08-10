import { describe, expect, it } from 'vitest';
import {
  CAMPAIGN_LISTS,
  WORLD_CATEGORIES,
  buildSessionEntry,
  campaignWorkspaceNavItems,
  worldCompleteness,
} from '../src/domain/worldbuilding';

describe('worldbuilding domain', () => {
  it('defines every requested worldbuilding category as a UI page/tab', () => {
    expect(WORLD_CATEGORIES.map((category) => category.label)).toEqual([
      'Economy',
      'Politics',
      'Magic Systems',
      'World Artifacts',
      'NPCs',
      'Government Organizations',
      'Non-Government Organizations',
      'Laws',
      'Inhabitants',
      'Ecosystems',
      'Cataclysmic Events',
      'General Overview',
      'Races',
      'Jobs and Roles',
      'Technology Systems',
      'Regions',
      'Era',
      'Player Characters',
    ]);
  });

  it('creates the repeated entry object used inside separate session JSON documents', () => {
    const entry = buildSessionEntry({
      entryId: 'magic_systems_s1_001',
      note: 'The first session established that false oaths sound like cracked bells.',
      createdAt: '2026-01-11T20:15:00Z',
      summary: 'False oaths sound like cracked bells.',
      tags: ['session_01', 'oath_magic'],
    });

    expect(entry).toEqual({
      entry_id: 'magic_systems_s1_001',
      note: 'The first session established that false oaths sound like cracked bells.',
      date_created: '2026-01-11T20:15:00Z',
      last_updated: '2026-01-11T20:15:00Z',
      summary: 'False oaths sound like cracked bells.',
      entry_tags: ['session_01', 'oath_magic'],
    });
  });

  it('starts users on a campaign dashboard grouped by owned, shared, and running campaigns', () => {
    expect(CAMPAIGN_LISTS.map((section) => section.id)).toEqual(['owned', 'shared', 'running']);
    expect(CAMPAIGN_LISTS.every((section) => section.campaigns.length > 0)).toBe(true);
    expect(CAMPAIGN_LISTS[0].campaigns[0]).toMatchObject({
      role: 'owner',
      status: 'active',
      lastSessionNumber: 10,
    });
  });

  it('keeps campaign workspace navigation separate from the login/campaign dashboard', () => {
    expect(campaignWorkspaceNavItems.map((item) => item.page)).toEqual([
      'campaign-overview',
      'world-builder',
      'session-prep',
      'notes',
      'review-queue',
      'canon-browser',
      'settings',
    ]);
  });

  it('marks a category built by either a saved entry or an approved canon event with a matching label', () => {
    const completeness = worldCompleteness(
      [{ category: 'economy' }],
      [{ category: 'Magic Systems' }],
    );
    const economy = completeness.perCategory.find((item) => item.category.id === 'economy');
    const magic = completeness.perCategory.find((item) => item.category.id === 'magic_systems');
    const politics = completeness.perCategory.find((item) => item.category.id === 'politics');

    expect(economy).toMatchObject({ entryCount: 1, canonCount: 0, built: true });
    expect(magic).toMatchObject({ entryCount: 0, canonCount: 1, built: true });
    expect(politics).toMatchObject({ entryCount: 0, canonCount: 0, built: false });
    expect(completeness.builtCount).toBe(2);
    expect(completeness.gaps.map((category) => category.id)).not.toContain('economy');
    expect(completeness.gaps.map((category) => category.id)).toContain('politics');
  });
});
