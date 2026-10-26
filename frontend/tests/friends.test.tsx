/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../src/mocks/server";
import { FriendsPanel } from "../src/components/FriendsPanel";
import { CampaignMembersPanel } from "../src/components/CampaignMembersPanel";
import { LoginPage } from "../src/pages/LoginPage";

afterEach(cleanup);

it("accepts an incoming friendship and a campaign invitation", async () => {
  let accepted = false;
  let joined = false;
  const onJoined = vi.fn();
  server.use(
    http.get("*/v1/friends", () => HttpResponse.json({ data: [{ id: "friend", user: { id: "peer", name: "Rin", email: "rin@example.com" }, incoming: true, status: accepted ? "accepted" : "pending" }] })),
    http.post("*/v1/friends/friend/accept", () => { accepted = true; return HttpResponse.json({ data: null }); }),
    http.get("*/v1/invitations", () => HttpResponse.json({ data: joined ? [] : [{ id: "invite", campaignName: "Moonfall", sender_name: "Rin", role: "player" }] })),
    http.post("*/v1/invitations/invite/accept", () => { joined = true; return HttpResponse.json({ data: null }); }),
  );
  render(<FriendsPanel onJoined={onJoined} />);
  fireEvent.click(await screen.findByRole("button", { name: /^accept$/i }));
  expect(await screen.findByText("Friend request accepted.")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /join campaign/i }));
  expect(await screen.findByText(/campaign joined/i)).toBeTruthy();
  expect(onJoined).toHaveBeenCalledOnce();
  expect(screen.queryByRole("button", { name: /join campaign/i })).toBeNull();
});

it("shows a rejected friend request without reporting success", async () => {
  server.use(http.post("*/v1/friends", () => HttpResponse.json({ error: { message: "No account found for that email." } }, { status: 404 })));
  render(<FriendsPanel onJoined={() => {}} />);
  await screen.findByText(/no friends yet/i);
  fireEvent.change(screen.getByLabelText(/friend’s email/i), { target: { value: "missing@example.com" } });
  fireEvent.click(screen.getByRole("button", { name: /send friend request/i }));
  expect(await screen.findByText(/no account found/i)).toBeTruthy();
});

it("invites an accepted friend with an explicit campaign role", async () => {
  let received: unknown;
  server.use(
    http.get("*/v1/friends", () => HttpResponse.json({ data: [{ id: "friend", user: { id: "peer", name: "Rin", email: "rin@example.com" }, incoming: false, status: "accepted" }] })),
    http.post("*/v1/campaigns/world/invitations", async ({ request }) => { received = await request.json(); return HttpResponse.json({ data: null }); }),
  );
  render(<CampaignMembersPanel campaignId="world" />);
  fireEvent.change(await screen.findByLabelText(/choose a friend/i), { target: { value: "rin@example.com" } });
  fireEvent.change(screen.getByLabelText(/^role$/i), { target: { value: "viewer" } });
  fireEvent.click(screen.getByRole("button", { name: /send invitation/i }));
  expect(await screen.findByText(/invitation created/i)).toBeTruthy();
  expect(received).toEqual({ email: "rin@example.com", role: "viewer" });
});

it("registers an account", async () => {
  const onSignIn = vi.fn();
  server.use(http.post("*/v1/auth/register", async ({ request }) => {
    expect(await request.json()).toEqual({ name: "Rin", email: "rin@example.com", password: "long-password" });
    return HttpResponse.json({ data: { id: "rin", name: "Rin", email: "rin@example.com" } });
  }));
  render(<LoginPage onSignIn={onSignIn} />);
  fireEvent.click(screen.getByRole("button", { name: /new here/i }));
  fireEvent.change(screen.getByLabelText(/display name/i), { target: { value: "Rin" } });
  fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "rin@example.com" } });
  fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "long-password" } });
  fireEvent.click(screen.getByRole("button", { name: /^create account$/i }));
  await screen.findByRole("button", { name: /^create account$/i });
  expect(onSignIn).toHaveBeenCalledWith({ id: "rin", name: "Rin", email: "rin@example.com" });
});
