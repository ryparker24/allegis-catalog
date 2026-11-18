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
 * CSRF (CISO review): SameSite=Lax does not stop a same-SITE page (another *.allegis.app host). Every
 * state-changing request must carry Origin == the app origin, and a POST body must be application/json
 * (a cross-site form cannot send that without a CORS preflight, which this app never answers).
 * Returns a reason code, or null when the request is fine.
 */
export function checkSameOrigin(req: Request, env: AppEnv): string | null {
  const m = req.method.toUpperCase();
  if (m === "GET" || m === "HEAD" || m === "OPTIONS") return null;
  const expected = env.APP_ORIGIN || new URL(req.url).origin;
  if (req.headers.get("origin") !== expected) return "bad_origin";
  if (m === "POST" && !(req.headers.get("content-type") ?? "").toLowerCase().startsWith("application/json")) return "bad_content_type";
  return null;
}

/**
 * Every API route starts here: (1) Cloudflare Access, (2) a live session, (3) domain + allowlist
 * re-checked on every request (so removing someone from ALLOWLIST takes effect at once), (4) write scope if asked.
 */
export async function requireUser(req: Request, env: AppEnv, opts: { write?: boolean; route?: string; next?: "/" | "/review" } = {}): Promise<Guarded> {
  const acc = await checkAccess(req, env);
  if (!acc.ok) {
    logEvent("denied", { route: opts.route, reason: acc.reason, http_status: 403 });
    return { ok: false, response: json({ error: "forbidden", reason: acc.reason }, 403) };
  }
  const csrf = checkSameOrigin(req, env);
  if (csrf) {
    logEvent("denied", { route: opts.route, reason: csrf, http_status: 403 });
    return { ok: false, response: json({ error: "forbidden", reason: csrf }, 403) };
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
    return { ok: false, response: json({ error: "consent_required", login: `/api/auth/login?scope=write&next=${opts.next ?? "/review"}` }, 409) };
  }
  return { ok: true, session: s };
}
