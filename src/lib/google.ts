import { createRemoteJWKSet, jwtVerify, type JWTPayload, type JWTVerifyGetKey } from "jose";
import { DRIVE_READ, DRIVE_WRITE } from "./session";

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;
const gfetch: FetchLike = (i, init) => fetch(i, init);

// ------------------------------------------------------------------ OAuth (online access only)
export const SIGNIN_SCOPES = ["openid", "email", DRIVE_READ];
export const WRITE_SCOPES = ["openid", "email", DRIVE_WRITE];

export function authUrl(p: { clientId: string; redirectUri: string; state: string; codeChallenge: string; write: boolean; hd: string; loginHint?: string }): string {
  const u = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  u.searchParams.set("client_id", p.clientId);
  u.searchParams.set("redirect_uri", p.redirectUri);
  u.searchParams.set("response_type", "code");
  u.searchParams.set("scope", (p.write ? WRITE_SCOPES : SIGNIN_SCOPES).join(" "));
  u.searchParams.set("access_type", "online"); // condition 2: Google issues no refresh token for online access
  u.searchParams.set("include_granted_scopes", "true"); // incremental consent for drive.metadata on first write
  u.searchParams.set("state", p.state);
  u.searchParams.set("code_challenge", p.codeChallenge);
  u.searchParams.set("code_challenge_method", "S256");
  u.searchParams.set("hd", p.hd); // UI hint only; the hd claim is enforced in decideIdentity()
  if (p.loginHint) u.searchParams.set("login_hint", p.loginHint);
  else u.searchParams.set("prompt", "select_account");
  return u.toString();
}

export interface TokenResult {
  accessToken: string;
  expiresIn: number;
  scopes: string[];
  idToken: string;
}

/** Exchanges the code. Returns ONLY access token, lifetime, scopes and id token - any other field Google sends is dropped here. */
export async function exchangeCode(p: { code: string; verifier: string; clientId: string; clientSecret: string; redirectUri: string }, f: FetchLike = gfetch): Promise<TokenResult> {
  const r = await f("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ code: p.code, code_verifier: p.verifier, client_id: p.clientId, client_secret: p.clientSecret, redirect_uri: p.redirectUri, grant_type: "authorization_code" }),
  });
  if (!r.ok) throw new Error(`token_exchange_failed_${r.status}`);
  const j = (await r.json()) as Record<string, unknown>;
  const accessToken = typeof j.access_token === "string" ? j.access_token : "";
  const idToken = typeof j.id_token === "string" ? j.id_token : "";
  const expiresIn = Number(j.expires_in) || 0;
  if (!accessToken || !idToken || expiresIn <= 0) throw new Error("token_exchange_incomplete");
  return { accessToken, idToken, expiresIn: Math.min(expiresIn, 3600), scopes: String(j.scope ?? "").split(/\s+/).filter(Boolean) };
}

const googleJwks = createRemoteJWKSet(new URL("https://www.googleapis.com/oauth2/v3/certs"));
export type IdTokenVerifier = (idToken: string, clientId: string) => Promise<JWTPayload>;
export const verifyIdToken: IdTokenVerifier = async (idToken, clientId) => {
  const { payload } = await jwtVerify(idToken, googleJwks as JWTVerifyGetKey, { issuer: ["https://accounts.google.com", "accounts.google.com"], audience: clientId });
  return payload;
};

export async function pkce(): Promise<{ verifier: string; challenge: string }> {
  const b = crypto.getRandomValues(new Uint8Array(32));
  const verifier = b64u(b);
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
  return { verifier, challenge: b64u(digest) };
}
export function randomToken(n = 24): string {
  return b64u(crypto.getRandomValues(new Uint8Array(n)));
}
function b64u(bytes: Uint8Array): string {
  let s = "";
  for (const x of bytes) s += String.fromCharCode(x);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

// ------------------------------------------------------------------ Drive
export const FILE_ID_RE = /^[A-Za-z0-9_-]{10,128}$/;
export interface BatchItem {
  status: number;
  body: Record<string, unknown> | null;
}

/**
 * One Drive batch request (multipart/mixed) of files.get as the signed-in user.
 * Returns status + parsed JSON per file id. Any id missing from the response is reported as status 0.
 */
export async function driveBatchGet(accessToken: string, ids: string[], opts: { fields: string; includeLabels?: string }, f: FetchLike = gfetch): Promise<Map<string, BatchItem>> {
  const out = new Map<string, BatchItem>();
  const valid = ids.filter((id) => FILE_ID_RE.test(id));
  if (!valid.length) return out;
  if (valid.length > 100) throw new Error("drive batch limit is 100");
  const boundary = "catalog_" + randomToken(12);
  const parts = valid.map((id, i) => {
    const q = new URLSearchParams({ fields: opts.fields, supportsAllDrives: "true" });
    if (opts.includeLabels) q.set("includeLabels", opts.includeLabels);
    return `--${boundary}\r\nContent-Type: application/http\r\nContent-ID: <item${i}>\r\n\r\nGET /drive/v3/files/${encodeURIComponent(id)}?${q}\r\n\r\n`;
  });
  const r = await f("https://www.googleapis.com/batch/drive/v3", {
    method: "POST",
    headers: { authorization: `Bearer ${accessToken}`, "content-type": `multipart/mixed; boundary=${boundary}` },
    body: parts.join("") + `--${boundary}--\r\n`,
  });
  if (!r.ok) {
    // Batch-level failure: nothing was checked. 401 stays 401 (session expired); anything else is "check failed",
    // never "no access".
    for (const id of valid) out.set(id, { status: r.status === 401 ? 401 : 0, body: null });
    return out;
  }
  const parsed = parseBatchResponse(r.headers.get("content-type") ?? "", await r.text());
  valid.forEach((id, i) => out.set(id, parsed.get(i) ?? { status: 0, body: null }));
  return out;
}

export function parseBatchResponse(contentType: string, text: string): Map<number, BatchItem> {
  const m = /boundary="?([^";]+)"?/i.exec(contentType);
  const res = new Map<number, BatchItem>();
  if (!m) return res;
  for (const raw of text.split(`--${m[1]}`)) {
    const part = raw.replace(/^\r?\n/, "");
    if (!part.trim() || part.startsWith("--")) continue;
    const cid = /Content-ID:\s*<response-item(\d+)>/i.exec(part);
    const st = /HTTP\/1\.1\s+(\d{3})/.exec(part);
    if (!cid || !st) continue;
    const httpIdx = part.indexOf(st[0]);
    const after = part.slice(httpIdx);
    const sep = after.search(/\r?\n\r?\n/);
    const bodyText = sep >= 0 ? after.slice(sep).trim() : "";
    let body: Record<string, unknown> | null = null;
    try {
      body = bodyText ? (JSON.parse(bodyText) as Record<string, unknown>) : null;
    } catch {
      body = null;
    }
    res.set(Number(cid[1]), { status: Number(st[1]), body });
  }
  return res;
}

export async function driveGet(accessToken: string, id: string, fields: string, f: FetchLike = gfetch): Promise<BatchItem> {
  if (!FILE_ID_RE.test(id)) return { status: 400, body: null };
  const q = new URLSearchParams({ fields, supportsAllDrives: "true" });
  const r = await f(`https://www.googleapis.com/drive/v3/files/${encodeURIComponent(id)}?${q}`, { headers: { authorization: `Bearer ${accessToken}` } });
  return { status: r.status, body: (await r.json().catch(() => null)) as Record<string, unknown> | null };
}

export async function modifyLabels(accessToken: string, id: string, labelModifications: unknown[], f: FetchLike = gfetch): Promise<BatchItem> {
  if (!FILE_ID_RE.test(id)) return { status: 400, body: null };
  const r = await f(`https://www.googleapis.com/drive/v3/files/${encodeURIComponent(id)}/modifyLabels`, {
    method: "POST",
    headers: { authorization: `Bearer ${accessToken}`, "content-type": "application/json" },
    body: JSON.stringify({ kind: "drive#modifyLabelsRequest", labelModifications }),
  });
  return { status: r.status, body: (await r.json().catch(() => null)) as Record<string, unknown> | null };
}

/** Rate-limit / transient reasons: the file was not checked (not the same as "no access"). */
export function isTransient(item: BatchItem): boolean {
  if (item.status === 0 || item.status === 429 || item.status >= 500) return true;
  if (item.status === 403) {
    const reason = ((item.body?.error as { errors?: { reason?: string }[] } | undefined)?.errors?.[0]?.reason ?? "").toLowerCase();
    return /ratelimit|limitexceeded|quota|backenderror/.test(reason);
  }
  return false;
}

// ------------------------------------------------------------------ Drive name search (CAT-WO-02 item 1, top-bar search)
export const NAME_SEARCH_CAP = 2000;
/** Drive query literal: backslash and single quote escaped, per the Drive search-query grammar. */
export function driveQueryLiteral(s: string): string {
  return `'${s.replace(/\\/g, "\\\\").replace(/'/g, "\\'")}'`;
}
/**
 * File IDs whose NAME contains the term, by a Drive files.list as the signed-in user: Google enforces access, and no
 * file name ever reaches the catalog DB or the logs. IDs only, capped at NAME_SEARCH_CAP.
 */
export async function driveNameSearch(accessToken: string, term: string, f: FetchLike = gfetch): Promise<{ ids: string[]; capped: boolean; status: number }> {
  const ids: string[] = [];
  let pageToken = "";
  for (let i = 0; i < 2; i++) {
    const q = new URLSearchParams({
      q: `name contains ${driveQueryLiteral(term)} and trashed = false`,
      corpora: "allDrives", includeItemsFromAllDrives: "true", supportsAllDrives: "true",
      fields: "nextPageToken,files(id)", pageSize: "1000",
    });
    if (pageToken) q.set("pageToken", pageToken);
    let j: { files?: { id?: string }[]; nextPageToken?: string };
    try {
      const r = await f(`https://www.googleapis.com/drive/v3/files?${q}`, { headers: { authorization: `Bearer ${accessToken}` } });
      if (!r.ok) return { ids, capped: false, status: r.status };
      j = (await r.json()) as typeof j;
    } catch {
      return { ids, capped: false, status: 0 }; // network / parse failure: the caller falls back to codes only
    }
    for (const x of j.files ?? []) if (x.id && FILE_ID_RE.test(x.id)) ids.push(x.id);
    pageToken = j.nextPageToken ?? "";
    if (!pageToken) return { ids, capped: false, status: 200 };
  }
  return { ids: ids.slice(0, NAME_SEARCH_CAP), capped: true, status: 200 };
}
