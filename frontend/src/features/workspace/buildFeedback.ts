export type BuildFeedback =
  | {
      kind: "success";
      title: string;
      message: string;
    }
  | {
      kind: "error";
      title: string;
      message: string;
      guidance: string;
    };

export function describeBuildFailure(error?: string | null): BuildFeedback {
  const detail = error?.toLowerCase() ?? "";

  if (
    detail.includes("credit_balance_exhausted") ||
    detail.includes("insufficient_quota") ||
    detail.includes("no credits remaining")
  ) {
    return {
      kind: "error",
      title: "OpenAI credits are unavailable",
      message: "OpenAI declined this build because the API project has no available credits.",
      guidance:
        "Add credits to the OpenAI Platform project that owns this key, then wait a few minutes and try again. A ChatGPT subscription does not cover API usage.",
    };
  }

  if (detail.includes("invalid_api_key") || detail.includes("incorrect api key")) {
    return {
      kind: "error",
      title: "Your OpenAI key was not accepted",
      message: "OpenAI could not authenticate the key connected to this browser session.",
      guidance:
        "Go to Campaigns → profile → Settings → AI provider → Manage, then connect a newly created API key from the OpenAI Platform.",
    };
  }

  if (detail.includes("rate limit") || detail.includes("error code: 429")) {
    return {
      kind: "error",
      title: "OpenAI is temporarily rate-limiting this build",
      message: "The provider accepted your key but cannot process this request right now.",
      guidance: "Wait a moment, then try building the world again.",
    };
  }

  if (detail.includes("timed out") || detail.includes("timeout")) {
    return {
      kind: "error",
      title: "The build took too long",
      message: "The world-building job did not finish within the available time.",
      guidance:
        "Try again in a moment. If it keeps happening, reduce provider load or check the API service logs.",
    };
  }

  return {
    kind: "error",
    title: "We could not build this world",
    message: "The build did not complete, and no campaign changes were made.",
    guidance:
      "Try again. If the problem continues, check your AI provider connection and the API service logs.",
  };
}
