/** @vitest-environment jsdom */
import { afterEach, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../src/mocks/server";
import { Dialog } from "../src/components/Dialog";
import App from "../src/App";

afterEach(cleanup);

it("contains modal focus and restores the opener", () => {
  const opener = document.createElement("button");
  document.body.append(opener); opener.focus();
  const view = render(<Dialog labelledBy="test-dialog" onClose={() => {}}><h2 id="test-dialog">Test dialog</h2><button>First</button><button>Last</button></Dialog>);
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "First" }));
  screen.getByRole("button", { name: "Last" }).focus();
  fireEvent.keyDown(document, { key: "Tab" });
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "First" }));
  fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "Last" }));
  view.unmount(); expect(document.activeElement).toBe(opener); opener.remove();
});

it("clears local sign-in state when remote logout fails", async () => {
  server.use(http.post("*/v1/auth/logout", () => HttpResponse.json({ error: { message: "Unavailable" } }, { status: 503 })));
  window.history.pushState({}, "", "/campaigns?preview=dashboard");
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Open profile menu" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Log out" }));
  expect(await screen.findByRole("heading", { name: "Log in to your campaigns" })).toBeTruthy();
  expect(screen.getByRole("alert").textContent).toMatch(/Signed out on this page/);
});
