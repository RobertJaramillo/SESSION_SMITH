/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../src/mocks/server";
import App from "../src/App";

const ASHES = "campaign_ashes_of_kestrel_vale";

describe("routing", () => {
  afterEach(cleanup);

  it("redirects an unauthenticated deep link to the login page", async () => {
    window.history.pushState({}, "", "/campaigns");
    render(<App />);

    expect(
      await screen.findByRole("heading", { name: /log in to your campaigns/i }),
    ).toBeTruthy();
  });

  it("deep-links straight into a workspace page when authenticated", async () => {
    window.history.pushState(
      {},
      "",
      `/campaigns/${ASHES}/canon-browser?preview=dashboard`,
    );
    render(<App />);

    expect(
      await screen.findByRole("heading", {
        name: /search approved campaign truth/i,
      }),
    ).toBeTruthy();
  });

  it("opens a campaign from the dashboard into its overview", async () => {
    window.history.pushState({}, "", "/campaigns?preview=dashboard");
    render(<App />);

    const openButtons = await screen.findAllByRole("button", {
      name: /open campaign/i,
    });
    fireEvent.click(openButtons[0]);

    expect(
      await screen.findByRole("heading", { name: /at a glance/i }),
    ).toBeTruthy();
  });

  it("shows the unavailable Google option with an explanation", async () => {
    window.history.pushState({}, "", "/login");
    render(<App />);
    const google = await screen.findByRole("button", { name: "Continue with Google" });
    expect(google.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(/Google sign-in is unavailable in this environment/)).toBeTruthy();
  });

  it("offers Google alongside password sign-in when configured", async () => {
    server.use(http.get("*/auth/config", () => HttpResponse.json({ data: { googleEnabled: true } })));
    window.history.pushState({}, "", "/login");
    render(<App />);
    expect((await screen.findByRole("link", { name: "Continue with Google" })).getAttribute("href")).toMatch(/\/auth\/google\/login$/);
    expect(screen.getByRole("button", { name: /^sign in$/i })).toBeTruthy();
  });

  it("signs in with account credentials", async () => {
    window.history.pushState({}, "", "/login");
    render(<App />);

    await screen.findByRole("button", { name: /^sign in$/i });
    fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "gm@example.com" } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "long-demo-password" } });
    fireEvent.click(screen.getByRole("button", { name: /^sign in$/i }));

    expect(
      await screen.findByRole("heading", { name: /drowkiroth/i }),
    ).toBeTruthy();
  });

  it("creates a campaign and opens its workspace", async () => {
    window.history.pushState({}, "", "/campaigns?preview=dashboard");
    render(<App />);

    fireEvent.click(
      await screen.findByRole("button", { name: /create campaign/i }),
    );
    fireEvent.change(
      await screen.findByPlaceholderText(/shadows of vaeloria/i),
      { target: { value: "Emberfall" } },
    );
    fireEvent.click(screen.getByRole("button", { name: /^create campaign$/i }));

    expect(
      await screen.findByRole("heading", { name: /at a glance/i }),
    ).toBeTruthy();
  });
});


it("opens the party dropdown and dismisses it with Escape or an outside click", async () => {
  window.history.pushState({}, "", "/campaigns?preview=dashboard");
  render(<App />);
  const toggle = await screen.findByRole("button", { name: "Friends & invitations" });
  fireEvent.click(toggle);
  expect(await screen.findByRole("region", { name: "Friends and invitations" })).toBeTruthy();
  expect(toggle.getAttribute("aria-expanded")).toBe("true");
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("region", { name: "Friends and invitations" })).toBeNull();
  expect(document.activeElement).toBe(toggle);
  fireEvent.click(toggle);
  await screen.findByRole("region", { name: "Friends and invitations" });
  fireEvent.pointerDown(screen.getByRole("heading", { name: "Your campaigns" }));
  expect(screen.queryByRole("region", { name: "Friends and invitations" })).toBeNull();
  expect(toggle.getAttribute("aria-expanded")).toBe("false");
  cleanup();
});
