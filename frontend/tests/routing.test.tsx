/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import App from '../src/App';

const ASHES = 'campaign_ashes_of_kestrel_vale';

describe('routing', () => {
  afterEach(cleanup);

  it('redirects an unauthenticated deep link to the login page', async () => {
    window.history.pushState({}, '', '/campaigns');
    render(<App />);

    expect(await screen.findByRole('heading', { name: /log in to your campaigns/i })).toBeTruthy();
  });

  it('deep-links straight into a workspace page when authenticated', async () => {
    window.history.pushState({}, '', `/campaigns/${ASHES}/canon-browser?preview=dashboard`);
    render(<App />);

    expect(await screen.findByRole('heading', { name: /search approved campaign truth/i })).toBeTruthy();
  });

  it('opens a campaign from the dashboard into its overview', async () => {
    window.history.pushState({}, '', '/campaigns?preview=dashboard');
    render(<App />);

    const openButtons = await screen.findAllByRole('button', { name: /open campaign/i });
    fireEvent.click(openButtons[0]);

    expect(await screen.findByRole('heading', { name: /at a glance/i })).toBeTruthy();
  });

  it('signs in through an SSO provider', async () => {
    window.history.pushState({}, '', '/login');
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /google/i }));

    expect(await screen.findByRole('heading', { name: /drowkiroth/i })).toBeTruthy();
  });

  it('creates a campaign and opens its workspace', async () => {
    window.history.pushState({}, '', '/campaigns?preview=dashboard');
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /create campaign/i }));
    fireEvent.change(await screen.findByPlaceholderText(/shadows of vaeloria/i), { target: { value: 'Emberfall' } });
    fireEvent.click(screen.getByRole('button', { name: /^create campaign$/i }));

    expect(await screen.findByRole('heading', { name: /at a glance/i })).toBeTruthy();
  });
});
