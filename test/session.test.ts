import { describe, expect, it } from "vitest";
import { authUrl, exchangeCode } from "@/lib/google";
import { handleCallback } from "@/lib/authflow";
import { readSession, seal, sealSession, unseal, nowS, SESSION_COOKIE, FLOW_COOKIE, type Session } from "@/lib/session";
import { ENV, SECRET } from "./helpers";

const GOOGLE_TOKEN_RESPONSE = { access_token: "ya29.ACCESS", expires_in: 3599, scope: "openid email", id_token: "id.tok.en", refresh_token: "1//SHOULD-NEVER-BE-KEPT", token_type: "Bearer" };

describe("G5 test_no_refresh_token_persisted", () => {
  it("sign-in URL asks for online access only and never forces offline consent", () => {
    const u = new URL(authUrl({ clientId: "c", redirectUri: "http://localhost:3000/api/auth/callback", state: "s", codeChallenge: "x", write: false, hd: "allegiscapital.com" }));
    expect(u.searchParams.get("access_type")).toBe("online");
    expect(u.searchParams.get("prompt")).not.toBe("consent");
    expect(u.searchParams.get("scope")).toBe("openid email https://www.googleapis.com/auth/drive.metadata.readonly");
  });
  it("write consent adds drive.metadata incrementally, still online", () => {
    const u = new URL(authUrl({ clientId: "c", redirectUri: "r", state: "s", codeChallenge: "x", write: true, hd: "allegiscapital.com" }));
    expect(u.searchParams.get("scope")).toContain("https://www.googleapis.com/auth/drive.metadata");
    expect(u.searchParams.get("include_granted_scopes")).toBe("true");
    expect(u.searchParams.get("access_type")).toBe("online");
  });
  it("exchangeCode drops any refresh token Google might send", async () => {
    const t = await exchangeCode({ code: "c", verifier: "v", clientId: "c", clientSecret: "s", redirectUri: "r" }, async () => new Response(JSON.stringify(GOOGLE_TOKEN_RESPONSE)));
    expect(Object.keys(t).sort()).toEqual(["accessToken", "expiresIn", "idToken", "scopes"]);
    expect(JSON.stringify(t)).not.toContain("SHOULD-NEVER-BE-KEPT");
  });
  it("sealSession persists only whitelisted fields even if extra fields are passed", async () => {
    const dirty = { v: 1, email: "ryan@allegiscapital.com", sub: "1", hd: "allegiscapital.com", at: "ya29.x", scopes: [], exp: nowS() + 600, refresh_token: "1//LEAK" } as unknown as Session;
    const c = await sealSession(dirty, SECRET);
    const back = await unseal<Record<string, unknown>>(c, SECRET, "session");
    expect(Object.keys(back!).sort()).toEqual(["at", "email", "exp", "hd", "scopes", "sub", "v"]);
    expect(JSON.stringify(back)).not.toContain("LEAK");
  });
  it("end-to-end callback: the session cookie decrypts to no refresh token, and expires with the access token", async () => {
    const flow = { v: 1, state: "st8", verifier: "v", next: "/", exp: nowS() + 600 };
    const req = new Request("http://localhost:3000/api/auth/callback?code=c&state=st8", { headers: { cookie: `${FLOW_COOKIE}=${await seal(flow, SECRET, "flow")}` } });
    const r = await handleCallback(req, ENV, { fetch: async () => new Response(JSON.stringify(GOOGLE_TOKEN_RESPONSE)), verifyIdToken: async () => ({ sub: "1", email: "ryan@allegiscapital.com", email_verified: true, hd: "allegiscapital.com" }) });
    const setCookie = r.headers.get("set-cookie")!;
    const m = new RegExp(`${SESSION_COOKIE}=([^;]+);[^,]*Max-Age=(\\d+)`).exec(setCookie)!;
    expect(setCookie).toMatch(/HttpOnly/);
    expect(Number(m[2])).toBeLessThanOrEqual(3599);
    const s = await unseal<Record<string, unknown>>(m[1], SECRET, "session");
    expect(JSON.stringify(s)).not.toMatch(/refresh|SHOULD-NEVER-BE-KEPT/);
    expect(setCookie).not.toContain("SHOULD-NEVER-BE-KEPT");
  });
  it("an expired or tampered session is refused", async () => {
    const base: Session = { v: 1, email: "ryan@allegiscapital.com", sub: "1", hd: "allegiscapital.com", at: "ya29.x", scopes: [], exp: nowS() - 1 };
    expect(await readSession(await sealSession(base, SECRET), SECRET)).toBeNull();
    const good = await sealSession({ ...base, exp: nowS() + 600 }, SECRET);
    expect(await readSession(good, SECRET)).not.toBeNull();
    expect(await readSession(good.slice(0, -2) + (good.endsWith("A") ? "BB" : "AA"), SECRET)).toBeNull();
    expect(await readSession(good, SECRET.replace("t", "T"))).toBeNull();
  });
});
