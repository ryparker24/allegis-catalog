import type { AppEnv } from "./env";
import { checkAccess } from "./access";
import { decideIdentity, DEFAULT_HD } from "./authz";
import { authUrl, exchangeCode, pkce, randomToken, verifyIdToken, type FetchLike, type IdTokenVerifier } from "./google";
import { clearCookie, FLOW_COOKIE, getCookie, nowS, readSession, seal, sealSession, SESSION_COOKIE, sessionCookie, unseal, type Flow } from "./session";
import { logEvent } from "./log";

export interface Deps {
  fetch?: FetchLike;
  verifyIdToken?: IdTokenVerifier;
}

function origin(req: Request, env: AppEnv): string {
  return env.APP_ORIGIN || new URL(req.url).origin;
}
function safeNext(n: string | null): string {
  return n && /^\/[A-Za-z0-9/_\-?=&.]*$/.test(n) && !n.startsWith("//") ? n : "/";
}
function page403(reason: string): Response {
  return new Response(
    `<!doctype html><meta charset="utf-8"><title>Not allowed</title><body style="font:15px system-ui;margin:3rem">` +
      `<h1>403 - not allowed</h1><p>This app is limited to allow-listed allegiscapital.com accounts.</p><p><code>${reason}</code></p>` +
      `<p><a href="/api/auth/login">Sign in with a different account</a></p></body>`,
    { status: 403, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store", "set-cookie": clearCookie(SESSION_COOKIE) } },
  );
}

/** GET /api/auth/login[?scope=write][&next=/path] */
export async function handleLogin(req: Request, env: AppEnv): Promise<Response> {
  const acc = await checkAccess(req, env);
  if (!acc.ok) return page403(acc.reason);
  if (!env.GOOGLE_CLIENT_ID || !env.SESSION_SECRET) return new Response("OAuth client not configured (R2)", { status: 503 });
  const u = new URL(req.url);
  const write = u.searchParams.get("scope") === "write";
  const { verifier, challenge } = await pkce();
  const flow: Flow = { v: 1, state: randomToken(), verifier, next: safeNext(u.searchParams.get("next")), exp: nowS() + 600 };
  const current = await readSession(getCookie(req.headers.get("cookie"), SESSION_COOKIE), env.SESSION_SECRET);
  const loc = authUrl({
    clientId: env.GOOGLE_CLIENT_ID, redirectUri: `${origin(req, env)}/api/auth/callback`, state: flow.state, codeChallenge: challenge,
    write, hd: env.ALLOWED_HD || DEFAULT_HD, loginHint: current?.email,
  });
  return new Response(null, {
    status: 302,
    headers: { location: loc, "cache-control": "no-store", "set-cookie": `${FLOW_COOKIE}=${await seal(flow, env.SESSION_SECRET, "flow")}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=600` },
  });
}

/** GET /api/auth/callback?code&state */
export async function handleCallback(req: Request, env: AppEnv, deps: Deps = {}): Promise<Response> {
  const acc = await checkAccess(req, env);
  if (!acc.ok) return page403(acc.reason);
  if (!env.GOOGLE_CLIENT_ID || !env.GOOGLE_CLIENT_SECRET || !env.SESSION_SECRET) return new Response("OAuth client not configured (R2)", { status: 503 });
  const u = new URL(req.url);
  const flow = await unseal<Flow>(getCookie(req.headers.get("cookie"), FLOW_COOKIE), env.SESSION_SECRET, "flow");
  const state = u.searchParams.get("state");
  const code = u.searchParams.get("code");
  if (!flow || flow.exp < nowS() || !state || state !== flow.state || !code) {
    logEvent("signin_failed", { reason: "bad_state" });
    return new Response("Sign-in expired or invalid. Start again at /api/auth/login", { status: 400, headers: { "set-cookie": clearCookie(FLOW_COOKIE) } });
  }
  let tok;
  try {
    tok = await exchangeCode({ code, verifier: flow.verifier, clientId: env.GOOGLE_CLIENT_ID, clientSecret: env.GOOGLE_CLIENT_SECRET, redirectUri: `${origin(req, env)}/api/auth/callback` }, deps.fetch);
  } catch (e) {
    logEvent("signin_failed", { reason: (e as Error).message });
    return new Response("Sign-in failed", { status: 502 });
  }
  let claims;
  try {
    claims = await (deps.verifyIdToken ?? verifyIdToken)(tok.idToken, env.GOOGLE_CLIENT_ID);
  } catch {
    logEvent("signin_failed", { reason: "id_token_invalid" });
    return page403("id_token_invalid");
  }
  const d = decideIdentity(claims as never, { allowlist: env.ALLOWLIST, hd: env.ALLOWED_HD });
  if (!d.ok) {
    logEvent("signin_denied", { reason: d.reason, http_status: 403 });
    return page403(d.reason);
  }
  if (acc.mode === "access" && acc.email !== d.email) {
    logEvent("signin_denied", { reason: "access_google_mismatch", http_status: 403 });
    return page403("access_google_mismatch");
  }
  const cookie = await sealSession(
    { v: 1, email: d.email, sub: String(claims.sub ?? ""), hd: String(claims.hd ?? ""), at: tok.accessToken, scopes: tok.scopes, exp: nowS() + tok.expiresIn },
    env.SESSION_SECRET,
  );
  logEvent("signin_ok", { can_write: tok.scopes.includes("https://www.googleapis.com/auth/drive.metadata") });
  const h = new Headers({ location: flow.next, "cache-control": "no-store" });
  h.append("set-cookie", sessionCookie(cookie, tok.expiresIn - 30));
  h.append("set-cookie", clearCookie(FLOW_COOKIE));
  return new Response(null, { status: 302, headers: h });
}

export function handleLogout(): Response {
  return new Response(null, { status: 303, headers: { location: "/", "set-cookie": clearCookie(SESSION_COOKIE), "cache-control": "no-store" } });
}
