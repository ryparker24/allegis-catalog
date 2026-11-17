import type { PageUser } from "@/lib/pageauth";

/** Header + tabs. Gaps is shown disabled: "not built (R-006)". Handles the sign-in / denied states. */
export function Shell({ user, active, children }: { user: PageUser; active: "find" | "review"; children: React.ReactNode }) {
  return (
    <div className="shell">
      <header className="top">
        <div className="brand">Allegis Catalog</div>
        <nav className="tabs" aria-label="Screens">
          <a href="/" className={active === "find" ? "tab on" : "tab"}>Find</a>
          <a href="/review" className={active === "review" ? "tab on" : "tab"}>Review queue</a>
          <span className="tab off" aria-disabled="true" title="Gaps is not built yet (R-006)">Gaps <small>not built (R-006)</small></span>
        </nav>
        <div className="who">
          {user.state === "ok" ? (
            <>
              <span>{user.email}</span>
              <form method="post" action="/api/auth/logout"><button className="link">Sign out</button></form>
            </>
          ) : null}
        </div>
      </header>
      <main>
        {user.state === "ok" ? children : user.state === "signin" ? (
          <div className="center">
            <h1>Sign in</h1>
            <p>Use your allegiscapital.com Google account. The app asks for read-only Drive metadata access; label writes ask again on first use.</p>
            <a className="btn primary" href={`/api/auth/login?next=${active === "review" ? "/review" : "/"}`}>Sign in with Google</a>
          </div>
        ) : (
          <div className="center">
            <h1>403 - not allowed</h1>
            <p>This app is limited to allow-listed allegiscapital.com accounts behind Cloudflare Access.</p>
            <p><code>{user.reason}</code></p>
          </div>
        )}
      </main>
    </div>
  );
}
