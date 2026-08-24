import { describe, expect, it } from "vitest";
import { describeBuildFailure } from "../src/features/workspace/buildFeedback";

describe("world build feedback", () => {
  it("turns OpenAI credit errors into safe, actionable guidance", () => {
    const feedback = describeBuildFailure(
      "Error code: 429 - credit_balance_exhausted",
    );

    expect(feedback).toMatchObject({
      kind: "error",
      title: "OpenAI credits are unavailable",
    });
    expect(feedback.message).toMatch(/no available credits/i);
    if (feedback.kind === "error") {
      expect(feedback.guidance).toMatch(/ChatGPT subscription/i);
    }
  });

  it("does not echo an invalid provider key in the UI", () => {
    const feedback = describeBuildFailure(
      "Incorrect API key provided: sk-secret-value",
    );

    expect(feedback).toMatchObject({
      kind: "error",
      title: "Your OpenAI key was not accepted",
    });
    expect(JSON.stringify(feedback)).not.toContain("sk-secret-value");
  });
});
