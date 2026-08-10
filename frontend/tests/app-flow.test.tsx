/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import App from '../src/App';

describe('app entry flow', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/');
  });

  afterEach(() => {
    cleanup();
  });

  it('starts on the login page and moves to the campaign dashboard after sign in', async () => {
    render(<App />);

    expect(screen.getByRole('heading', { name: /your living campaign memory/i })).toBeTruthy();
    expect(screen.getByRole('heading', { name: /log in to your campaigns/i })).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /^sign in$/i }));

    expect(screen.getByRole('heading', { name: /drowkiroth/i })).toBeTruthy();
    // Campaign columns load from the API (MSW), so wait for them.
    expect(await screen.findByRole('heading', { name: /^owned$/i })).toBeTruthy();
    expect(screen.getByRole('heading', { name: /in progress/i })).toBeTruthy();
    expect(screen.queryByText(/three clean lanes/i)).toBeNull();
  });

  it('can open directly to the dashboard for page review', () => {
    window.history.pushState({}, '', '/?preview=dashboard');
    render(<App />);

    expect(screen.getByRole('heading', { name: /drowkiroth/i })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: /log in to your campaigns/i })).toBeNull();
  });

  it('opens a profile menu with settings and log out', () => {
    window.history.pushState({}, '', '/?preview=dashboard');
    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: /open profile menu/i }));

    expect(screen.getByRole('menuitem', { name: /settings/i })).toBeTruthy();
    expect(screen.getByRole('menuitem', { name: /log out/i })).toBeTruthy();
  });

  it('opens an account settings modal with one update control for each editable option', () => {
    window.history.pushState({}, '', '/?preview=dashboard');
    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: /open profile menu/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /settings/i }));

    expect(screen.getByRole('dialog', { name: /^settings$/i })).toBeTruthy();
    expect(screen.getByText(/user name/i)).toBeTruthy();
    expect(screen.getByText(/account tier/i)).toBeTruthy();
    expect(screen.getByText(/email/i)).toBeTruthy();
    expect(screen.getByText(/password reset/i)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /^cancel$/i })).toBeNull();
    expect(screen.getAllByRole('button', { name: /^update$/i })).toHaveLength(3);
    expect(screen.queryByRole('button', { name: /^ok$/i })).toBeNull();
    expect(screen.getByText(/current plan/i)).toBeTruthy();
  });

  it('requires matching update values before save is enabled', () => {
    window.history.pushState({}, '', '/?preview=dashboard');
    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: /open profile menu/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /settings/i }));
    fireEvent.click(screen.getAllByRole('button', { name: /^update$/i })[0]);

    expect(screen.getByRole('dialog', { name: /update user name/i })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /^approve$/i })).toBeNull();
    const saveButton = screen.getByRole('button', { name: /^save$/i });
    expect(saveButton.hasAttribute('disabled')).toBe(true);

    fireEvent.change(screen.getByPlaceholderText(/enter new user name/i), { target: { value: 'DrowGM' } });
    expect(saveButton.hasAttribute('disabled')).toBe(true);

    fireEvent.change(screen.getByPlaceholderText(/confirm new user name/i), { target: { value: 'Mismatch' } });
    expect(saveButton.hasAttribute('disabled')).toBe(true);
    expect(screen.getByText(/both fields must be filled in and match/i)).toBeTruthy();

    fireEvent.change(screen.getByPlaceholderText(/confirm new user name/i), { target: { value: 'DrowGM' } });
    expect(saveButton.hasAttribute('disabled')).toBe(false);

    fireEvent.click(saveButton);
    expect(screen.getByText('DrowGM')).toBeTruthy();
    expect(screen.queryByRole('dialog', { name: /update user name/i })).toBeNull();
  });
});
