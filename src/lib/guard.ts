import type { AppEnv } from "./env";
import { checkAccess } from "./access";
import { decideIdentity } from "./authz";
import { canWrite, getCookie, readSession, SESSION_COOKIE, type Session } from "./session";
import { logEvent } from "./log";

export type Guarded = { ok: true; session: Session } | { ok: false; response: Response };

export function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers },
  });
}

/**
 * Every API route starts here: (1) Cloudflare Access, (2) a live session, (3) domain + allowlist
 * re-checked on every request (so removing someone from ALLOWLIST takes effect at once), (4) write scope if asked.
 */
export async function requireUser(req: Request, env: AppEnv, opts: { write?: boolean; route?: string } = {}): Promise<Guarded> {
  const acc = await checkAccess(req, env);
  if (!acc.ok) {
    logEvent("denied", { route: opts.route, reason: acc.reason, http_status: 403 });
    return { ok: false, response: json({ error: "forbidden", reason: acc.reason }, 403) };
  }
  const s = await readSession(getCookie(req.headers.get("cookie"), SESSION_COOKIE), env.SESSION_SECRET);
  if (!s) return { ok: false, response: json({ error: "signin_required", login: "/api/auth/login" }, 401) };
  const d = decideIdentity({ email: s.email, email_verified: true, hd: s.hd }, { allowlist: env.ALLOWLIST, hd: env.ALLOWED_HD });
  if (!d.ok) {
    logEvent("denied", { route: opts.route, reason: d.reason, http_status: 403 });
    return { ok: false, response: json({ error: "forbidden", reason: d.reason }, 403) };
  }
  if (acc.mode === "access" && acc.email !== s.email.toLowerCase()) {
    logEvent("denied", { route: opts.route, reason: "access_google_mismatch", http_status: 403 });
    return { ok: false, response: json({ error: "forbidden", reason: "access_google_mismatch" }, 403) };
  }
  if (opts.write && !canWrite(s)) {
    return { ok: false, response: json({ error: "consent_required", login: "/api/auth/login?scope=write&next=/review" }, 409) };
  }
  return { ok: true, session: s };
}
