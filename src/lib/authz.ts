/** Who may use the app (v1: Ryan only). Checked at sign-in AND on every request. */
export const DEFAULT_HD = "allegiscapital.com";

export interface IdentityClaims {
  email?: string;
  email_verified?: boolean | string;
  hd?: string;
}
export type Decision = { ok: true; email: string } | { ok: false; status: 403; reason: string };

export function parseAllowlist(s: string | undefined): Set<string> {
  return new Set((s ?? "").split(/[,\s]+/).map((x) => x.trim().toLowerCase()).filter(Boolean));
}

export function decideIdentity(c: IdentityClaims, cfg: { allowlist: string | undefined; hd?: string }): Decision {
  const hd = (cfg.hd || DEFAULT_HD).toLowerCase();
  const email = (c.email ?? "").toLowerCase();
  if (!email) return { ok: false, status: 403, reason: "no_email" };
  if (c.email_verified !== true && c.email_verified !== "true") return { ok: false, status: 403, reason: "email_unverified" };
  // Workspace domain: the hd claim is authoritative (a personal account has none); the address must match too.
  if ((c.hd ?? "").toLowerCase() !== hd || !email.endsWith("@" + hd)) return { ok: false, status: 403, reason: "wrong_domain" };
  const allow = parseAllowlist(cfg.allowlist);
  if (!allow.has(email)) return { ok: false, status: 403, reason: "not_allowlisted" };
  return { ok: true, email };
}
