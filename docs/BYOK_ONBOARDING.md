# Bring Your Own Key (BYOK) onboarding

Session Smith offers an OpenAI bring-your-own-key flow today, with Gemini and a
hosted plan shown as upcoming options. The UI makes clear who pays for
generation and where campaign notes are sent.

| Option | Who pays for AI use? | Availability | Best for |
| --- | --- | --- | --- |
| OpenAI BYOK | The user's OpenAI account | Available now, per browser session | Private-beta GMs who want live generation |
| Gemini BYOK | The user's Google account | Provider setup guide only; adapter is not implemented | Users who want to prepare for Gemini support |
| Session Smith hosted AI | Session Smith, with plan limits | Not available | Future convenience plan |

## User-facing setup instructions

### Connect an OpenAI key

1. Sign in to the [OpenAI API platform](https://platform.openai.com/).
2. Create a project API key from the [API keys page](https://platform.openai.com/api-keys).
3. Review that project's budget and usage limits before using the key.
4. In Session Smith, choose **Use my OpenAI API key**, paste the key, acknowledge
   the session-only policy, and select **Use OpenAI this session**.

The key is never placed in the URL, browser storage, Session Smith's database,
or AI job history. It is held in the running browser tab and sent only to the
same-origin backend when an AI job is requested. Refreshing the page or logging
out removes it. In production this flow must be served over HTTPS.

### Prepare a Gemini key

1. Open [Google AI Studio's API key page](https://aistudio.google.com/app/apikey).
2. Create a Gemini API key and check the current free-tier model and rate limits.
3. Keep the key private. Do **not** paste it into Session Smith until the Gemini
   provider adapter is released.

Google AI Studio can create an API key for a new user. Gemini Developer API free
tiers have limited access and may use submitted content to improve Google's
products; users should read the current [Gemini API pricing and data-use
terms](https://ai.google.dev/gemini-api/docs/pricing) before sending campaign
notes. Google's eligible-new-customer Cloud trial is different: it currently
provides $300 of credit for 90 days, rather than a permanent $300 Gemini API
allowance. See the [Google Cloud Free Trial FAQ](https://cloud.google.com/signup-faqs).

## Product recommendation

For the private beta, offer **OpenAI BYOK**. It avoids charging Session Smith
for unbounded generation while users validate the product.

A $5/month hosted-AI plan should be considered only after these controls exist:

- A real authenticated user identity and ownership checks on every request.
- A server-side secrets vault: envelope encryption, a KMS-managed master key,
  key rotation, no plaintext key logs, and no API-key readback endpoint.
- A strict included monthly allowance (requests or tokens), hard spend caps,
  rate limits, and clear overage behavior. Do not market the plan as unlimited.
- A payment system, cancellation/refund flow, usage ledger, and support process.

The key point is that a $5 subscription pays for a bounded service level; it
does not make the underlying LLM usage free.

## Engineering boundary

This repository's sign-in screen is currently a UI-only beta gate, not real
authentication. Therefore Session Smith intentionally does **not** persist a
user's provider key. The implemented OpenAI flow is session-only BYOK. The
offline demo provider remains an internal development and test fallback; it is
not offered as a user-facing onboarding choice.

Before adding persistent keys or Gemini execution, implement authentication,
authorized user/campaign ownership, encrypted credential storage, and an
auditable provider-connection model. Never put a provider key in localStorage,
sessionStorage, IndexedDB, analytics, logs, error reports, database job payloads,
or query strings.
