import { useState } from "react";

export function LoginPage({ onSignIn }: { onSignIn: () => void }) {
  const [notice, setNotice] = useState("");

  return (
    <main className="login-page">
      <section className="login-hero-panel" aria-labelledby="login-title">
        <div className="login-brand-row">
          <div className="brand-mark" aria-hidden="true">
            ✦
          </div>
          <div>
            <span className="eyebrow">Session Smith</span>
            <strong>AI campaign orchestration</strong>
          </div>
        </div>

        <div className="login-copy">
          <span className="eyebrow">Private beta</span>
          <h1 id="login-title">
            Your living campaign memory, ready before the table sits down.
          </h1>
          <p>
            Sign in to organize session notes, approve AI-suggested canon, and
            keep every campaign world consistent from the first session to the
            last.
          </p>
        </div>

        <div className="login-preview-card" aria-label="Product preview">
          <div className="preview-toolbar">
            <span></span>
            <span></span>
            <span></span>
            <strong>Tonight's prep</strong>
          </div>
          <div className="preview-stack">
            <div>
              <small>Canon confidence</small>
              <strong>96%</strong>
            </div>
            <div>
              <small>Pending GM review</small>
              <strong>3 memories</strong>
            </div>
            <div>
              <small>Next session</small>
              <strong>Bell Vault Fallout</strong>
            </div>
          </div>
        </div>
      </section>

      <section className="login-card" aria-label="Sign in form">
        <div className="login-card-header">
          <span className="eyebrow">Welcome back</span>
          <h2>Log in to your campaigns</h2>
          <p>Sign in to pick up your campaigns right where you left off.</p>
        </div>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            onSignIn();
          }}
        >
          <label>
            Email address
            <input
              autoComplete="email"
              defaultValue="gm@example.com"
              inputMode="email"
              placeholder="you@example.com"
              type="email"
            />
          </label>
          <label>
            Password
            <input
              autoComplete="current-password"
              defaultValue="campaign-memory"
              placeholder="••••••••••••"
              type="password"
            />
          </label>
          <div className="login-options-row">
            <label className="checkbox-label">
              <input defaultChecked type="checkbox" />
              <span>Remember this device</span>
            </label>
            <button
              className="link-button"
              onClick={() =>
                setNotice(
                  "Password reset isn’t available in the private beta yet — reach out to your beta contact.",
                )
              }
              type="button"
            >
              Forgot password?
            </button>
          </div>
          <button className="login-submit" type="submit">
            Sign in
          </button>
        </form>

        <div className="sso-divider">
          <span>or continue with</span>
        </div>
        <div className="sso-row">
          <button className="secondary" onClick={onSignIn} type="button">
            Google
          </button>
          <button className="secondary" onClick={onSignIn} type="button">
            Discord
          </button>
        </div>
        {notice && (
          <p className="empty-state" role="status">
            {notice}
          </p>
        )}
        <p className="login-footnote">
          New to Session Smith?{" "}
          <button
            className="link-button"
            onClick={() =>
              setNotice(
                "Thanks for your interest — beta access is granted manually right now, so we’ll be in touch.",
              )
            }
            type="button"
          >
            Request beta access
          </button>
        </p>
      </section>
    </main>
  );
}
