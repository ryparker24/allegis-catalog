import { describe, expect, it } from "vitest";
import { generateKeyPair, SignJWT } from "jose";
import { decideIdentity } from "@/lib/authz";
import { handleCallback } from "@/lib/authflow";
import { checkAccess } from "@/lib/access";
import { requireUser } from "@/lib/guard";
import { seal, sealSession, SESSION_COOKIE, FLOW_COOKIE, nowS } from "@/lib/session";
import { ENV, SECRET } from "./helpers";

const ALLOW = { allowlist: "ryan@allegiscapital.com", hd: "allegiscapital.com" };

describe("G6 test_non_allegis_and_non_allowlisted_get_403", () => {
  it("decideIdentity: personal gmail account -> 403", () => {
    expect(decideIdentity({ email: "someone@gmail.com", email_verified: true }, ALLOW)).toEqual({ ok: false, status: 403, reason: "wrong_domain" });
  });
  it("decideIdentity: other Workspace domain -> 403", () => {
    expect(decideIdentity({ email: "a@other.com", email_verified: true, hd: "other.com" }, ALLOW)).toMatchObject({ ok: false, status: 403 });
  });
  it("decideIdentity: allegiscapital.com address without hd claim -> 403", () => {
    expect(decideIdentity({ email: "ryan@allegiscapital.com", email_verified: true }, ALLOW)).toMatchObject({ ok: false, status: 403, reason: "wrong_domain" });
  });
  it("decideIdentity: allegiscapital.com but NOT allowlisted -> 403", () => {
    expect(decideIdentity({ email: "colleague@allegiscapital.com", email_verified: true, hd: "allegiscapital.com" }, ALLOW)).toEqual({ ok: false, status: 403, reason: "not_allowlisted" });
  });
  it("decideIdentity: unverified email -> 403", () => {
    expect(decideIdentity({ email: "ryan@allegiscapital.com", email_verified: false, hd: "allegiscapital.com" }, ALLOW)).toMatchObject({ ok: false, status: 403 });
  });
  it("decideIdentity: allowlisted allegiscapital.com account -> ok (control)", () => {
    expect(decideIdentity({ email: "Ryan@allegiscapital.com", email_verified: true, hd: "allegiscapital.com" }, ALLOW)).toEqual({ ok: true, email: "ryan@allegiscapital.com" });
  });

  async function callback(claims: Record<string, unknown>) {
    const flow = { v: 1, state: "st8", verifier: "v", next: "/", exp: nowS() + 600 };
    const req = new Request("http://localhost:3000/api/auth/callback?code=c0de&state=st8", { headers: { cookie: `${FLOW_COOKIE}=${await seal(flow, SECRET, "flow")}` } });
    const fakeFetch = async () => new Response(JSON.stringify({ access_token: "ya29.ACCESS", expires_in: 3599, scope: "openid email https://www.googleapis.com/auth/drive.metadata.readonly", id_token: "id.tok.en", refresh_token: "1//SHOULD-NEVER-BE-KEPT" }), { status: 200 });
    return handleCallback(req, ENV, { fetch: fakeFetch, verifyIdToken: async () => ({ sub: "1", ...claims }) });
  }
  it("callback route: gmail account -> 403 and no session cookie", async () => {
    const r = await callback({ email: "someone@gmail.com", email_verified: true });
    expect(r.status).toBe(403);
    expect(r.headers.get("set-cookie") ?? "").not.toMatch(new RegExp(`${SESSION_COOKIE}=[^;]`));
  });
  it("callback route: allegiscapital.com non-allowlisted -> 403 and no session cookie", async () => {
    const r = await callback({ email: "colleague@allegiscapital.com", email_verified: true, hd: "allegiscapital.com" });
    expect(r.status).toBe(403);
    expect(r.headers.get("set-cookie") ?? "").not.toMatch(new RegExp(`${SESSION_COOKIE}=[^;]`));
  });
  it("callback route: allowlisted -> 302 with session cookie (control)", async () => {
    const r = await callback({ email: "ryan@allegiscapital.com", email_verified: true, hd: "allegiscapital.com" });
    expect(r.status).toBe(302);
    expect(r.headers.get("set-cookie")).toMatch(new RegExp(`${SESSION_COOKIE}=[^;]+`));
  });

  it("every API request: a still-valid session for an account REMOVED from the allowlist -> 403", async () => {
    const c = await sealSession({ v: 1, email: "ryan@allegiscapital.com", sub: "1", hd: "allegiscapital.com", at: "ya29.x", scopes: [], exp: nowS() + 600 }, SECRET);
    const req = new Request("http://localhost:3000/api/find", { headers: { cookie: `${SESSION_COOKIE}=${c}` } });
    const g = await requireUser(req, { ...ENV, ALLOWLIST: "someone-else@allegiscapital.com" });
    expect(g.ok).toBe(false);
    if (!g.ok) expect(g.response.status).toBe(403);
    const ok = await requireUser(req, ENV);
    expect(ok.ok).toBe(true);
  });
});

describe("Cloudflare Access gate (fails closed)", () => {
  it("no Access config and not localhost -> 403", async () => {
    const r = await checkAccess(new Request("https://catalog.allegis.app/"), { ...ENV, ACCESS_MODE: "local-dev" });
    expect(r).toMatchObject({ ok: false, status: 403, reason: "access_not_configured" });
  });
  it("Access configured but JWT missing -> 403", async () => {
    const r = await checkAccess(new Request("https://catalog.allegis.app/"), { ...ENV, CF_ACCESS_TEAM_DOMAIN: "team", CF_ACCESS_AUD: "aud1" });
    expect(r).toMatchObject({ ok: false, reason: "access_jwt_missing" });
  });
  it("valid Access JWT for a non-allowlisted email -> 403; allowlisted -> ok", async () => {
    const { publicKey, privateKey } = await generateKeyPair("RS256");
    const mk = (email: string) => new SignJWT({ email }).setProtectedHeader({ alg: "RS256" }).setIssuer("https://team.cloudflareaccess.com").setAudience("aud1").setExpirationTime("5m").sign(privateKey);
    const env = { ...ENV, CF_ACCESS_TEAM_DOMAIN: "team", CF_ACCESS_AUD: "aud1" };
    const key = async () => publicKey;
    const bad = await checkAccess(new Request("https://catalog.allegis.app/", { headers: { "cf-access-jwt-assertion": await mk("x@gmail.com") } }), env, key);
    expect(bad).toMatchObject({ ok: false, status: 403 });
    const good = await checkAccess(new Request("https://catalog.allegis.app/", { headers: { "cf-access-jwt-assertion": await mk("ryan@allegiscapital.com") } }), env, key);
    expect(good).toMatchObject({ ok: true, mode: "access" });
  });
});
