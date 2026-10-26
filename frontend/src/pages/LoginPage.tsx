import { useState } from "react";
import { authenticate, type Account } from "../api/client";

export function LoginPage({ onSignIn }: { onSignIn: (account: Account) => void }) {
  const [notice, setNotice] = useState("");
  const [register, setRegister] = useState(false);
  const [busy, setBusy] = useState(false);

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
          <h2>{register ? "Create your account" : "Log in to your campaigns"}</h2>
          <p>Sign in to pick up your campaigns right where you left off.</p>
        </div>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            if (busy) return;
            const fields = new FormData(event.currentTarget);
            setBusy(true);
            setNotice("");
            try {
              onSignIn(await authenticate(register, { email: String(fields.get("email")), password: String(fields.get("password")), name: String(fields.get("name") ?? "") }));
            } catch (error) { setNotice(error instanceof Error ? error.message : "Could not sign in."); }
            finally { setBusy(false); }
          }}
        >
          {register && <label>Display name<input name="name" required maxLength={80} autoComplete="nickname" /></label>}
          <label>
            Email address
            <input
              autoComplete="email"
              name="email" required
              inputMode="email"
              placeholder="you@example.com"
              type="email"
            />
          </label>
          <label>
            Password
            <input
              autoComplete="current-password"
              name="password" required minLength={12} maxLength={256}
              placeholder="••••••••••••"
              type="password"
            />
          </label>
          {register && <p>Use a password with at least 12 characters.</p>}
          <button className="login-submit" disabled={busy} type="submit">
            {busy ? "Please wait…" : register ? "Create account" : "Sign in"}
          </button>
        </form>

        {notice && (
          <p className="empty-state" role="status">
            {notice}
          </p>
        )}
        <p className="login-footnote">
          <button className="link-button" onClick={() => { setRegister(!register); setNotice(""); }} type="button">
            {register ? "Already have an account? Sign in" : "New here? Create an account"}
          </button>
        </p>
      </section>
    </main>
  );
}
