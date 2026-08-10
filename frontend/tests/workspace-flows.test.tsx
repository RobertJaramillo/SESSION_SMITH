/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import App from '../src/App';

// Glass Moon Exile is a session-0 campaign that starts with no proposals,
// prep, or entries — so these flows exercise creation from an empty state.
const GLASS_MOON = 'campaign_glass_moon_exile';

function openAt(path: string) {
  window.history.pushState({}, '', `${path}?preview=dashboard`);
  render(<App />);
}

describe('workspace flows (via the /v1 mock API)', () => {
  afterEach(cleanup);

  it('submits session notes, gets AI proposals, and approves one into canon', async () => {
    openAt(`/campaigns/${GLASS_MOON}/notes`);

    const notes = await screen.findByPlaceholderText(/paste this session's raw table notes/i);
    fireEvent.change(notes, { target: { value: 'The Iron Court raised bridge tariffs on the river crossing.' } });
    fireEvent.click(screen.getByRole('button', { name: /submit notes for ai review/i }));

    // The job runs asynchronously, then proposals land in the review queue.
    const approve = await screen.findByRole('button', { name: /^approve$/i }, { timeout: 4000 });
    fireEvent.click(approve);

    expect(await screen.findByText(/added to canon/i)).toBeTruthy();
  });

  it('flags a pending proposal that conflicts with existing canon', async () => {
    window.history.pushState({}, '', '/campaigns/campaign_ashes_of_kestrel_vale/review-queue?preview=dashboard');
    render(<App />);

    expect(await screen.findByRole('heading', { name: /the iron court controls river taxes/i })).toBeTruthy();
    expect(await screen.findByText(/possible conflict with existing canon/i)).toBeTruthy();
    expect(await screen.findByText(/already states the iron court sets and enforces river-crossing tariffs/i)).toBeTruthy();
  });

  it('generates a session prep outline from a goal', async () => {
    openAt(`/campaigns/${GLASS_MOON}/session-prep`);

    const goal = await screen.findByPlaceholderText(/what should the next session accomplish/i);
    fireEvent.change(goal, { target: { value: 'Cross the shattered bridge' } });
    fireEvent.click(screen.getByRole('button', { name: /queue ai prep job/i }));

    expect(
      await screen.findByDisplayValue(/establish the stakes around cross the shattered bridge/i, undefined, { timeout: 4000 }),
    ).toBeTruthy();
  });

  it('saves campaign settings', async () => {
    openAt(`/campaigns/${GLASS_MOON}/settings`);

    const nameInput = await screen.findByDisplayValue(/glass moon exile/i);
    fireEvent.change(nameInput, { target: { value: 'Glass Moon Reborn' } });
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));

    expect(await screen.findByText(/settings saved/i)).toBeTruthy();
  });

  it('filters canon in the browser by search text', async () => {
    window.history.pushState({}, '', '/campaigns/campaign_ashes_of_kestrel_vale/canon-browser?preview=dashboard');
    render(<App />);

    expect(await screen.findByText(/iron court sets and enforces/i)).toBeTruthy();

    fireEvent.change(screen.getByPlaceholderText(/npc, faction, region/i), { target: { value: 'oath' } });

    expect(await screen.findByText(/binding oaths require a witnessed vow/i)).toBeTruthy();
    expect(screen.queryByText(/iron court sets and enforces/i)).toBeNull();
  });

  it('adds a world-builder entry as a tile while the world is draft', async () => {
    openAt(`/campaigns/${GLASS_MOON}/world-builder`);

    // The card/tile view hides the form behind an explicit "+ Add" affordance;
    // Economy is the default active category for an empty (draft) world.
    fireEvent.click(await screen.findByRole('button', { name: /add economy detail/i }));

    const title = await screen.findByPlaceholderText(/entry title/i);
    fireEvent.change(title, { target: { value: 'Coin shortage' } });
    const body = screen.getByPlaceholderText(/paste world setup/i);
    fireEvent.change(body, { target: { value: 'Silver is scarce after the mines flooded.' } });
    fireEvent.click(screen.getByRole('button', { name: /save entry to this session/i }));

    // Exact match targets the tile's title node, not the "Economy: Coin shortage"
    // summary line in the saved-this-session list.
    expect(await screen.findByText('Coin shortage')).toBeTruthy();
  });

  it('builds the world (without sealing), reviews inline, approves into canon, then seals explicitly', async () => {
    openAt(`/campaigns/${GLASS_MOON}/world-builder`);

    // Build drafts every category (no per-category selection needed).
    fireEvent.click(await screen.findByRole('button', { name: /build world/i }));

    // Build returns proposals for inline review WITHOUT sealing (Seal world is offered).
    const approveButtons = await screen.findAllByRole('button', { name: /^approve$/i }, { timeout: 4000 });
    fireEvent.click(approveButtons[0]);
    expect(await screen.findByText(/added to canon/i)).toBeTruthy();

    // Still editable/reviewing — sealing is a separate, explicit action.
    fireEvent.click(screen.getByRole('button', { name: /^seal world$/i }));
    expect(await screen.findByText(/your world is sealed/i)).toBeTruthy();
  });

  it('shows a sealed world as read-only, with no add or build controls', async () => {
    window.history.pushState({}, '', '/campaigns/campaign_ashes_of_kestrel_vale/world-builder?preview=dashboard');
    render(<App />);

    // Ashes is a played campaign — its world is sealed.
    expect(await screen.findByText(/your world is sealed/i)).toBeTruthy();
    expect(await screen.findByText(/5\/18 categories built/i)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /build world/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /add .*detail/i })).toBeNull();

    // The sealed world can be exported (for evaluation).
    const exportLink = screen.getByRole('link', { name: /export world \(pdf\)/i });
    expect(exportLink.getAttribute('href')).toMatch(/\/v1\/campaigns\/campaign_ashes_of_kestrel_vale\/world-export\?format=pdf$/);
  });
});
