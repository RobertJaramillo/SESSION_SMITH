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

it.each([
  ["pending", true, "Decline"],
  ["pending", false, "Cancel request"],
  ["accepted", false, "Remove friend"],
])("removes a %s friendship (incoming=%s) and refreshes the list", async (status, incoming, label) => {
  let removed = false;
  server.use(
    http.get("*/v1/friends", () => HttpResponse.json({ data: removed ? [] : [
      { id: "friend", user: { id: "peer", name: "Rin", email: "rin@example.com" }, status, incoming },
    ] })),
    http.delete("*/v1/friends/friend", () => { removed = true; return HttpResponse.json({ data: null }); }),
  );
  render(<FriendsPanel onJoined={vi.fn()} />);
  const button = await screen.findByRole("button", { name: label });
  if (!incoming) expect(screen.queryByRole("button", { name: /^accept$/i })).toBeNull();
  fireEvent.click(button);
  await screen.findByText(/no friends yet/i);
  expect(removed).toBe(true);
  expect(screen.queryByText("rin@example.com")).toBeNull();
});

it("does not report a join when accepting an invitation fails", async () => {
  const onJoined = vi.fn();
  server.use(
    http.get("*/v1/invitations", () => HttpResponse.json({ data: [
      { id: "invite", campaignName: "Moonfall", sender_name: "Rin", role: "viewer" },
    ] })),
    http.post("*/v1/invitations/invite/accept", () => HttpResponse.json({ error: { message: "Invitation not found or expired." } }, { status: 404 })),
  );
  render(<FriendsPanel onJoined={onJoined} />);
  fireEvent.click(await screen.findByRole("button", { name: /join campaign/i }));
  await screen.findByText(/invitation not found or expired/i);
  expect(onJoined).not.toHaveBeenCalled();
  expect(screen.queryByText(/campaign joined/i)).toBeNull();
  expect((screen.getByRole("button", { name: /join campaign/i }) as HTMLButtonElement).disabled).toBe(false);
});

it("only offers accepted friends and preserves invitation details after failure", async () => {
  server.use(
    http.get("*/v1/friends", () => HttpResponse.json({ data: [
      { id: "accepted", user: { id: "peer", name: "Rin", email: "rin@example.com" }, incoming: false, status: "accepted" },
      { id: "pending", user: { id: "other", name: "Pending", email: "pending@example.com" }, incoming: true, status: "pending" },
    ] })),
    http.post("*/v1/campaigns/world/invitations", () => HttpResponse.json({ error: { message: "An invitation is already pending." } }, { status: 409 })),
  );
  render(<CampaignMembersPanel campaignId="world" />);
  fireEvent.change(await screen.findByLabelText(/choose a friend/i), { target: { value: "rin@example.com" } });
  expect(screen.queryByRole("option", { name: "Pending" })).toBeNull();
  fireEvent.change(screen.getByLabelText(/^role$/i), { target: { value: "viewer" } });
  fireEvent.click(screen.getByRole("button", { name: /send invitation/i }));
  await screen.findByText(/an invitation is already pending/i);
  expect((screen.getByLabelText(/^email$/i) as HTMLInputElement).value).toBe("rin@example.com");
  expect((screen.getByLabelText(/^role$/i) as HTMLSelectElement).value).toBe("viewer");
  expect(screen.queryByText(/invitation created/i)).toBeNull();
});

it("refreshes the roster after removing a member and revoking an invitation", async () => {
  let removed = false;
  let revoked = false;
  server.use(
    http.get("*/v1/campaigns/world/members", () => HttpResponse.json({ data: {
      members: [
        { id: "owner", name: "Owner", email: "owner@example.com", role: "owner" },
        ...(removed ? [] : [{ id: "peer", name: "Rin", email: "rin@example.com", role: "viewer" }]),
      ],
      invitations: revoked ? [] : [{ id: "invite", email: "new@example.com", role: "player" }],
    } })),
    http.delete("*/v1/campaigns/world/members/peer", () => { removed = true; return HttpResponse.json({ data: null }); }),
    http.delete("*/v1/invitations/invite", () => { revoked = true; return HttpResponse.json({ data: null }); }),
  );
  render(<CampaignMembersPanel campaignId="world" />);
  expect(await screen.findAllByRole("button", { name: /remove member/i })).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: /remove member/i }));
  await screen.findByText("Member removed.");
  expect(screen.queryByText("rin@example.com")).toBeNull();
  expect(screen.getByText("owner@example.com")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /revoke/i }));
  await screen.findByText("Invitation revoked.");
  expect(screen.queryByText("new@example.com")).toBeNull();
});
