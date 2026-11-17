import type { PageUser } from "@/lib/pageauth";
import { AppShell } from "./AppShell";

/** Datum-style shell (CAT-WO-02 item 1). Gaps is shown disabled: "R-006". Handles the sign-in / denied states. */
export function Shell({ user, active, children }: { user: PageUser; active: "find" | "review"; children: React.ReactNode }) {
  const ok = user.state === "ok";
  return (
    <AppShell email={ok ? user.email : null} active={active} signedIn={ok}>
      {ok ? children : user.state === "signin" ? (
        <div className="center">
          <div className="crumb">Allegis Capital · Catalog</div>
          <h1>Sign in</h1>
          <p className="muted">Use your allegiscapital.com Google account. The app asks for read-only Drive metadata access; label writes ask again on first use.</p>
          <a className="btn primary" href={`/api/auth/login?next=${active === "review" ? "/review" : "/"}`}>Sign in with Google</a>
        </div>
      ) : (
        <div className="center">
          <div className="crumb">Allegis Capital · Catalog</div>
          <h1>403 · not allowed</h1>
          <p className="muted">This app is limited to allow-listed allegiscapital.com accounts behind Cloudflare Access.</p>
          <p><code>{user.reason}</code></p>
        </div>
      )}
    </AppShell>
  );
}
