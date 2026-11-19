import { useEffect, useRef, useState } from "react";
import { ApiError, getAuthConfig, googleLoginUrl, authenticate, forgotPassword, resendVerification, type Account } from "../api/client";

export function LoginPage({ onSignIn }: { onSignIn: (account: Account) => void }) {
  const formRef = useRef<HTMLFormElement>(null);
  const [managed, setManaged] = useState(false);
  const [verificationRequired, setVerificationRequired] = useState(false);
  const [recovering, setRecovering] = useState(false);
  const [googleEnabled, setGoogleEnabled] = useState(false);
  useEffect(() => {
    let active = true;
    getAuthConfig()
      .then((config) => { if (active) { setGoogleEnabled(config.googleEnabled); setManaged(config.provider === "firebase"); } })
      .catch(() => {});
    return () => { active = false; };
  }, []);
  const [notice, setNotice] = useState("");
  const [register, setRegister] = useState(false);
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

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
          <h2>{recovering ? "Reset your password" : register ? "Create your account" : "Log in to your campaigns"}</h2>
          <p>Sign in to pick up your campaigns right where you left off.</p>
        </div>

        {googleEnabled ? (
          <a className="button-link login-submit" href={googleLoginUrl()}>Continue with Google</a>
        ) : (
          <>
            <button className="login-submit" type="button" disabled aria-describedby="google-signin-unavailable">Continue with Google</button>
            <p id="google-signin-unavailable" className="login-footnote">Google sign-in is unavailable in this environment. Use email and password below.</p>
          </>
        )}

        <form ref={formRef}
          onSubmit={async (event) => {
            event.preventDefault();
            if (busy) return;
            const fields = new FormData(event.currentTarget);
            setBusy(true);
            setNotice("");
            try {
              if (recovering) {
                setNotice((await forgotPassword(String(fields.get("email")))).message);
              } else {
                const result = await authenticate(register, { email: String(fields.get("email")), password: String(fields.get("password")), name: String(fields.get("name") ?? "") });
                if ("verificationRequired" in result) { setNotice(result.message); setRegister(false); setVerificationRequired(true); }
                else onSignIn(result);
              }
            } catch (error) {
              setVerificationRequired(error instanceof ApiError && error.code === "email_verification_required");
              setNotice(error instanceof Error ? error.message : "Could not sign in.");
            }
            finally { setBusy(false); }
          }}
        >
          {register && <label>Display name<input name="name" required maxLength={80} autoComplete="nickname" /></label>}
          <label>
            Email address
            <input
              onChange={() => setVerificationRequired(false)}
              autoComplete="email"
              name="email" required
              inputMode="email"
              placeholder="you@example.com"
              type="email"
            />
          </label>
          {!recovering && <div className="login-password-field">
            <label htmlFor="login-password">Password</label>
            <div className="password-input-wrap">
            <input
              id="login-password"
              autoComplete={register ? "new-password" : "current-password"}
              name="password" required minLength={register ? 12 : undefined} maxLength={256}
              placeholder="••••••••••••"
              type={showPassword ? "text" : "password"}
            />
            <button className="password-visibility-toggle" type="button"
              aria-label={showPassword ? "Hide password" : "Show password"}
              aria-pressed={showPassword} aria-controls="login-password"
              onClick={() => setShowPassword(!showPassword)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
                <circle cx="12" cy="12" r="3" />
                {showPassword && <path d="m3 3 18 18" />}
              </svg>
            </button>
            </div>
          </div>
          }
          {register && <p>Use a password with at least 12 characters.</p>}
          <button className="login-submit" disabled={busy} type="submit">
            {busy ? "Please wait…" : recovering ? "Send reset link" : register ? "Create account" : "Sign in"}
          </button>
        </form>

        {managed && !register && !recovering && <div className="login-footnote login-help-actions">
          <button className="link-button" type="button" disabled={busy} onClick={() => { setShowPassword(false); setRecovering(true); setVerificationRequired(false); setNotice(""); }}>Forgot your password?</button>
          {verificationRequired && <button className="link-button" type="button" disabled={busy} onClick={async () => {
            const fields = new FormData(formRef.current!);
            if (!fields.get("email") || !fields.get("password")) { setNotice("Enter your email and password above to resend verification."); return; }
            setBusy(true);
            try { setNotice((await resendVerification(String(fields.get("email")), String(fields.get("password")))).message); }
            catch (error) { setNotice(error instanceof Error ? error.message : "Could not send verification."); }
            finally { setBusy(false); }
          }}>Resend verification email</button>}
        </div>}
        {recovering && <p className="login-footnote">We’ll email a secure link to set a new password. After resetting, return here to sign in.</p>}
        {notice && (
          <p className="empty-state" role="status">
            {notice}
          </p>
        )}
        <p className="login-footnote">
          <button className="link-button" disabled={busy} onClick={() => { setShowPassword(false); if (recovering) setRecovering(false); else setRegister(!register); setVerificationRequired(false); setNotice(""); }} type="button">
            {recovering || register ? "Already have an account? Sign in" : "New here? Create an account"}
          </button>
        </p>
      </section>
    </main>
  );
}
