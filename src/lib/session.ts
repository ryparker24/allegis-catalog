/**
 * Session = an AES-GCM-sealed, HttpOnly cookie holding the Google ACCESS token and identity, and nothing else.
 * Condition 2: no refresh token is ever stored. The payload type has no field for one, sealSession() copies
 * only the whitelisted fields, and the cookie's Max-Age = the access token's remaining life, so the session
 * dies with the token. Nothing is stored server-side.
 */
export const SESSION_COOKIE = "__Host-cat_s";
export const FLOW_COOKIE = "__Host-cat_f";
export const DRIVE_READ = "https://www.googleapis.com/auth/drive.metadata.readonly";
export const DRIVE_WRITE = "https://www.googleapis.com/auth/drive.metadata";

export interface Session {
  v: 1;
  email: string;
  sub: string;
  hd: string;
  at: string; // Google access token (online access)
  scopes: string[];
  exp: number; // epoch seconds - access token expiry
}

export interface Flow {
  v: 1;
  state: string;
  verifier: string;
  next: string;
  exp: number;
}

const enc = new TextEncoder();
const dec = new TextDecoder();

function b64u(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function unb64u(s: string): Uint8Array {
  const pad = s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4);
  const bin = atob(pad);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function key(secret: string, purpose: string): Promise<CryptoKey> {
  if (!secret || secret.length < 32) throw new Error("SESSION_SECRET missing or too short");
  const base = await crypto.subtle.importKey("raw", enc.encode(secret), "HKDF", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    { name: "HKDF", hash: "SHA-256", salt: enc.encode("allegis-catalog/v1"), info: enc.encode(purpose) },
    base, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"],
  );
}

export async function seal(obj: unknown, secret: string, purpose: string): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await key(secret, purpose), enc.encode(JSON.stringify(obj))));
  return `${b64u(iv)}.${b64u(ct)}`;
}

export async function unseal<T>(token: string | undefined | null, secret: string, purpose: string): Promise<T | null> {
  if (!token) return null;
  const [ivs, cts] = token.split(".");
  if (!ivs || !cts) return null;
  try {
    const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv: unb64u(ivs) as BufferSource }, await key(secret, purpose), unb64u(cts) as BufferSource);
    return JSON.parse(dec.decode(pt)) as T;
  } catch {
    return null;
  }
}

export const nowS = () => Math.floor(Date.now() / 1000);

/** Copies ONLY the whitelisted fields: whatever else the caller holds (e.g. a token response) is not persisted. */
export async function sealSession(s: Session, secret: string): Promise<string> {
  const clean: Session = { v: 1, email: s.email, sub: s.sub, hd: s.hd, at: s.at, scopes: [...s.scopes], exp: s.exp };
  return seal(clean, secret, "session");
}

export async function readSession(cookieValue: string | undefined | null, secret: string | undefined): Promise<Session | null> {
  if (!secret) return null;
  const s = await unseal<Session>(cookieValue, secret, "session");
  if (!s || s.v !== 1 || typeof s.exp !== "number" || s.exp <= nowS() + 5) return null;
  return s;
}

export function sessionCookie(value: string, maxAgeS: number): string {
  return `${SESSION_COOKIE}=${value}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${Math.max(0, Math.floor(maxAgeS))}`;
}
export function clearCookie(name: string): string {
  return `${name}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`;
}

export function getCookie(header: string | null | undefined, name: string): string | undefined {
  if (!header) return undefined;
  for (const part of header.split(/;\s*/)) {
    const i = part.indexOf("=");
    if (i > 0 && part.slice(0, i) === name) return part.slice(i + 1);
  }
  return undefined;
}

export function canWrite(s: Session | null): boolean {
  return !!s && s.scopes.includes(DRIVE_WRITE);
}
