import { createRemoteJWKSet, jwtVerify, type JWTVerifyGetKey } from "jose";
import type { AppEnv } from "./env";
import { parseAllowlist } from "./authz";

/**
 * Cloudflare Access gate (R3). BOTH Access and Google sign-in must pass.
 * Fails closed: without CF_ACCESS_TEAM_DOMAIN + CF_ACCESS_AUD every request is refused, except when
 * ACCESS_MODE=local-dev AND the request is addressed to localhost/127.0.0.1 (next dev on Ryan's machine).
 */
export type AccessResult = { ok: true; email: string | null; mode: "access" | "local-dev" } | { ok: false; status: 403; reason: string };

const jwksCache = new Map<string, JWTVerifyGetKey>();
function jwks(team: string): JWTVerifyGetKey {
  let k = jwksCache.get(team);
  if (!k) {
    k = createRemoteJWKSet(new URL(`https://${team}/cdn-cgi/access/certs`));
    jwksCache.set(team, k);
  }
  return k;
}

function normTeam(t: string): string {
  const s = t.replace(/^https?:\/\//, "").replace(/\/+$/, "");
  return s.includes(".") ? s : `${s}.cloudflareaccess.com`;
}

export function isLocalhost(req: Request): boolean {
  const host = new URL(req.url).hostname;
  return host === "localhost" || host === "127.0.0.1" || host === "[::1]";
}

export async function checkAccess(req: Request, env: AppEnv, getKey?: JWTVerifyGetKey): Promise<AccessResult> {
  if (env.CF_ACCESS_TEAM_DOMAIN && env.CF_ACCESS_AUD) {
    const token = req.headers.get("cf-access-jwt-assertion");
    if (!token) return { ok: false, status: 403, reason: "access_jwt_missing" };
    const team = normTeam(env.CF_ACCESS_TEAM_DOMAIN);
    try {
      const { payload } = await jwtVerify(token, getKey ?? jwks(team), { issuer: `https://${team}`, audience: env.CF_ACCESS_AUD });
      const email = typeof payload.email === "string" ? payload.email.toLowerCase() : null;
      if (!email || !parseAllowlist(env.ALLOWLIST).has(email)) return { ok: false, status: 403, reason: "access_email_not_allowlisted" };
      return { ok: true, email, mode: "access" };
    } catch {
      return { ok: false, status: 403, reason: "access_jwt_invalid" };
    }
  }
  if (env.ACCESS_MODE === "local-dev" && isLocalhost(req)) return { ok: true, email: null, mode: "local-dev" };
  return { ok: false, status: 403, reason: "access_not_configured" };
}
