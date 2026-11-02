import { googleLoginUrl } from "../api/client";

export function LoginPage() {
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
          <p>Sign in with Google to pick up your campaigns right where you left off.</p>
        </div>

        <a className="button-link login-submit" href={googleLoginUrl()}>
          Continue with Google
        </a>

        <p className="login-footnote">
          New to Session Smith? Beta access is granted manually right now — sign in with
          the Google account your beta contact registered.
        </p>
      </section>
    </main>
  );
}
