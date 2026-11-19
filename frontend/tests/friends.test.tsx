/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../src/mocks/server";
import { FriendsPanel } from "../src/components/FriendsPanel";
import { CampaignMembersPanel } from "../src/components/CampaignMembersPanel";
import { CampaignDashboardPage } from "../src/pages/CampaignDashboardPage";
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
  fireEvent.click(screen.getByRole("button", { name: /send invitation/i }));
  expect(await screen.findByText(/invitation created/i)).toBeTruthy();
  expect(received).toEqual({ email: "rin@example.com", role: "player" });
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
      { id: "invite", campaignName: "Moonfall", sender_name: "Rin", role: "player" },
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
  fireEvent.click(screen.getByRole("button", { name: /send invitation/i }));
  await screen.findByText(/an invitation is already pending/i);
  expect((screen.getByLabelText(/^email$/i) as HTMLInputElement).value).toBe("rin@example.com");
  expect(screen.queryByText(/invitation created/i)).toBeNull();
});

it("refreshes the roster after removing a member and revoking an invitation", async () => {
  let removed = false;
  let revoked = false;
  server.use(
    http.get("*/v1/campaigns/world/members", () => HttpResponse.json({ data: {
      members: [
        { id: "owner", name: "Owner", email: "owner@example.com", role: "owner" },
        ...(removed ? [] : [{ id: "peer", name: "Rin", email: "rin@example.com", role: "player" }]),
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

it("shares an owned campaign directly from its dashboard card", async () => {
  const prototype = HTMLDialogElement.prototype;
  const show = Object.getOwnPropertyDescriptor(prototype, "showModal");
  const close = Object.getOwnPropertyDescriptor(prototype, "close");
  Object.defineProperty(prototype, "showModal", { configurable: true, value: function (this: HTMLDialogElement) { this.setAttribute("open", ""); } });
  Object.defineProperty(prototype, "close", { configurable: true, value: function (this: HTMLDialogElement) { this.removeAttribute("open"); } });
  const openCampaign = vi.fn();
  let invited: unknown;
  server.use(
    http.get("*/v1/campaigns", () => HttpResponse.json({ data: [{ id: "owned", title: "Owned", subtitle: "Your worlds", campaigns: [
      { campaignId: "world", name: "Moonfall", role: "owner", status: "planning", description: "A world", lastSessionNumber: 0, players: [{ id: "rin", name: "Rin" }] },
      { campaignId: "shared", name: "Shared world", role: "player", status: "active", description: "Another world", lastSessionNumber: 1 },
    ] }] })),
    http.post("*/v1/campaigns/world/invitations", async ({ request }) => { invited = await request.json(); return HttpResponse.json({ data: null }); }),
  );
  try {
    render(<CampaignDashboardPage account={{ id: "me", name: "GM", email: "gm@example.com" }} onAccountUpdated={() => {}} onOpenCampaign={openCampaign} onLogout={() => {}} provider="demo" onManageProvider={() => {}} />);
    await screen.findByRole("button", { name: "Share Moonfall" });
    expect(screen.getByText("1 player")).toBeTruthy();
    expect(screen.getByText("Rin")).toBeTruthy();
    expect(screen.getByText("No players yet")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Share Moonfall" }));
    expect(screen.queryByRole("button", { name: "Share Shared world" })).toBeNull();
    expect(screen.getByRole("dialog", { name: "Share Moonfall" })).toBeTruthy();
    expect(openCampaign).not.toHaveBeenCalled();
    fireEvent.change(await screen.findByLabelText(/^email$/i), { target: { value: "friend@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    await screen.findByText(/invitation created/i);
    expect(invited).toEqual({ email: "friend@example.com", role: "player" });
    fireEvent.click(screen.getByRole("button", { name: "Close sharing" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  } finally {
    cleanup();
    if (show) Object.defineProperty(prototype, "showModal", show); else Reflect.deleteProperty(prototype, "showModal");
    if (close) Object.defineProperty(prototype, "close", close); else Reflect.deleteProperty(prototype, "close");
  }
});

it("requests managed password recovery without requiring a password", async () => {
  let email: unknown;
  server.use(
    http.get("*/auth/config", () => HttpResponse.json({ data: { googleEnabled: true, provider: "firebase" } })),
    http.post("*/v1/auth/forgot-password", async ({ request }) => {
      email = await request.json();
      return HttpResponse.json({ data: { message: "If an account exists for that email, a password reset link has been sent." } });
    }),
  );
  const signIn = vi.fn();
  render(<LoginPage onSignIn={signIn} />);
  await screen.findByRole("button", { name: "Forgot your password?" });
  expect(screen.queryByRole("button", { name: "Resend verification email" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Forgot your password?" }));
  expect(screen.queryByLabelText(/^password$/i)).toBeNull();
  fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "gm@example.com" } });
  fireEvent.click(screen.getByRole("button", { name: "Send reset link" }));
  await screen.findByText(/If an account exists/);
  expect(email).toEqual({ email: "gm@example.com" });
  expect(signIn).not.toHaveBeenCalled();
});

it("requires email verification after Firebase signup instead of opening campaigns", async () => {
  server.use(
    http.get("*/auth/config", () => HttpResponse.json({ data: { googleEnabled: true, provider: "firebase" } })),
    http.post("*/v1/auth/register", () => HttpResponse.json({ data: { verificationRequired: true, message: "Check your inbox to verify your email, then sign in." } })),
    http.post("*/v1/auth/resend-verification", () => HttpResponse.json({ data: { message: "If the details are correct, a verification email has been sent." } })),
  );
  const signIn = vi.fn();
  render(<LoginPage onSignIn={signIn} />);
  fireEvent.click(screen.getByRole("button", { name: /New here/ }));
  fireEvent.change(screen.getByLabelText(/display name/i), { target: { value: "GM" } });
  fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "gm@example.com" } });
  fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "strong-test-password" } });
  fireEvent.click(screen.getByRole("button", { name: "Create account" }));
  await screen.findByText(/Check your inbox to verify/);
  expect(signIn).not.toHaveBeenCalled();
  fireEvent.click(await screen.findByRole("button", { name: "Resend verification email" }));
  await screen.findByText(/If the details are correct/);
});

it("offers resend only after an unverified sign-in and hides it when the email changes", async () => {
  server.use(
    http.get("*/auth/config", () => HttpResponse.json({ data: { googleEnabled: true, provider: "firebase" } })),
    http.post("*/v1/auth/login", () => HttpResponse.json({ error: { code: "email_verification_required", message: "Verify your email before signing in." } }, { status: 403 })),
  );
  render(<LoginPage onSignIn={() => {}} />);
  await screen.findByRole("button", { name: "Forgot your password?" });
  expect(screen.queryByRole("button", { name: "Resend verification email" })).toBeNull();
  fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "gm@example.com" } });
  fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "strong-test-password" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  await screen.findByRole("button", { name: "Resend verification email" });
  fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "other@example.com" } });
  expect(screen.queryByRole("button", { name: "Resend verification email" })).toBeNull();
});

it("applies the 12-character rule to signup, not existing-password sign-in", () => {
  render(<LoginPage onSignIn={() => {}} />);
  expect(screen.getByLabelText(/^password$/i).hasAttribute("minlength")).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: /New here/ }));
  expect(screen.getByLabelText(/^password$/i).getAttribute("minlength")).toBe("12");
});

it("requires confirmation before transferring ownership to an accepted friend", async () => {
  const transferred = vi.fn();
  let received: unknown;
  server.use(
    http.get("*/v1/friends", () => HttpResponse.json({ data: [
      { id: "friend", user: { id: "rin", name: "Rin", email: "rin@example.com" }, status: "accepted", incoming: false },
      { id: "pending", user: { id: "other", name: "Pending friend", email: "other@example.com" }, status: "pending", incoming: false },
    ] })),
    http.post("*/v1/campaigns/world/transfer-ownership", async ({ request }) => { received = await request.json(); return HttpResponse.json({ data: { ownerId: "rin", previousOwnerRole: "player" } }); }),
  );
  render(<CampaignMembersPanel campaignId="world" onTransferred={transferred} />);
  const select = await screen.findByLabelText("New owner");
  expect(screen.queryByRole("option", { name: "Pending friend" })).toBeNull();
  fireEvent.change(select, { target: { value: "rin" } });
  fireEvent.click(screen.getByRole("button", { name: "Transfer ownership" }));
  expect(screen.getByRole("alert").textContent).toMatch(/private notes and session prep/);
  expect(received).toBeUndefined();
  fireEvent.click(screen.getByRole("button", { name: "Cancel transfer" }));
  expect(screen.queryByRole("button", { name: "Confirm transfer" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Transfer ownership" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm transfer" }));
  await screen.findByText(/Ownership transferred/);
  expect(received).toEqual({ friendId: "rin" });
  expect(transferred).toHaveBeenCalledOnce();
});
