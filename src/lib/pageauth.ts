import { cookies, headers } from "next/headers";
import { getEnv } from "./env";
import { checkAccess } from "./access";
import { decideIdentity } from "./authz";
import { canWrite, readSession, SESSION_COOKIE } from "./session";

export type PageUser = { state: "ok"; email: string; canWrite: boolean } | { state: "signin" } | { state: "denied"; reason: string };

/** Same gates as the API guard, for server-rendered pages (the page shell holds no data; the APIs re-check). */
export async function pageUser(): Promise<PageUser> {
  const env = await getEnv();
  const h = await headers();
  const host = h.get("host") ?? "invalid";
  const proto = h.get("x-forwarded-proto") ?? "https";
  const hdrs: Record<string, string> = {};
  const jwt = h.get("cf-access-jwt-assertion");
  if (jwt) hdrs["cf-access-jwt-assertion"] = jwt;
  const acc = await checkAccess(new Request(`${proto}://${host}/`, { headers: hdrs }), env);
  if (!acc.ok) return { state: "denied", reason: acc.reason };
  const s = await readSession((await cookies()).get(SESSION_COOKIE)?.value, env.SESSION_SECRET);
  if (!s) return { state: "signin" };
  const d = decideIdentity({ email: s.email, email_verified: true, hd: s.hd }, { allowlist: env.ALLOWLIST, hd: env.ALLOWED_HD });
  if (!d.ok) return { state: "denied", reason: d.reason };
  if (acc.mode === "access" && acc.email !== s.email.toLowerCase()) return { state: "denied", reason: "access_google_mismatch" };
  return { state: "ok", email: s.email, canWrite: canWrite(s) };
}
