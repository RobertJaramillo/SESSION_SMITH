/** @vitest-environment jsdom */
import { afterEach, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../src/mocks/server";
import * as client from "../src/api/client";

const fakeKey = "sk-test-not-a-real-key";
afterEach(() => { client.clearSessionAIProvider(); vi.restoreAllMocks(); });

it("keeps the API key out of browser storage and sends it only with AI jobs", async () => {
  const storage = vi.spyOn(Storage.prototype, "setItem");
  const requests: { path: string; key: string | null; provider: string | null; body: string; credentials: string }[] = [];
  server.use(http.all("http://localhost/v1/*", async ({ request }) => {
    requests.push({ path: new URL(request.url).pathname, key: request.headers.get("X-Session-Smith-API-Key"), provider: request.headers.get("X-Session-Smith-Provider"), body: await request.text(), credentials: request.credentials });
    return HttpResponse.json({ data: {} });
  }));
  client.setSessionOpenAIKey(`  ${fakeKey}  `);
  await client.submitSessionNotes("world", { content: "A note", sessionNumber: "1", title: "Session" });
  await client.submitPrepJob("world", { goal: "Prepare", tone: "balanced", memories: "" });
  await client.submitBuildWorld("world", { generateCategories: [] });
  await client.getAccount();
  await client.getCampaignSections();
  await client.createCampaign({ name: "World", description: "" });
  expect(requests.slice(0, 3).every(r => r.key === fakeKey && r.provider === "openai")).toBe(true);
  expect(requests.slice(3).every(r => r.key === null && r.provider === null)).toBe(true);
  expect(requests.every(r => !r.body.includes(fakeKey) && !r.path.includes(fakeKey))).toBe(true);
  expect(requests.every(r => r.credentials === "include")).toBe(true);
  expect(storage).not.toHaveBeenCalled();
  client.clearSessionAIProvider();
  await client.submitBuildWorld("world", { generateCategories: [] });
  expect(requests.at(-1)?.key).toBeNull();
});

it("forgets the key when the client module is loaded in a fresh page context", async () => {
  const keys: (string | null)[] = [];
  server.use(http.post("http://localhost/v1/campaigns/world/build-world", ({ request }) => {
    keys.push(request.headers.get("X-Session-Smith-API-Key"));
    return HttpResponse.json({ data: {} });
  }));
  client.setSessionOpenAIKey(fakeKey);
  await client.submitBuildWorld("world", { generateCategories: [] });
  vi.resetModules();
  const freshClient = await import("../src/api/client");
  freshClient.setApiBase("http://localhost");
  await freshClient.submitBuildWorld("world", { generateCategories: [] });
  expect(keys).toEqual([fakeKey, null]);
});
