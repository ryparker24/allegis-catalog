export interface AppEnv {
  APP_ORIGIN?: string;
  ALLOWED_HD?: string;
  ALLOWLIST?: string;
  GOOGLE_CLIENT_ID?: string;
  GOOGLE_CLIENT_SECRET?: string;
  SESSION_SECRET?: string;
  CATALOG_APP_DB_URL?: string;
  CF_ACCESS_TEAM_DOMAIN?: string;
  CF_ACCESS_AUD?: string;
  /** "local-dev" skips the Access JWT check for localhost requests only. Never set in production. */
  ACCESS_MODE?: string;
}

const KEYS: (keyof AppEnv)[] = [
  "APP_ORIGIN", "ALLOWED_HD", "ALLOWLIST", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "SESSION_SECRET",
  "CATALOG_APP_DB_URL", "CF_ACCESS_TEAM_DOMAIN", "CF_ACCESS_AUD", "ACCESS_MODE",
];

/** Server-only: Worker bindings (vars + secrets) via OpenNext, falling back to process.env (next dev / tests). */
export async function getEnv(): Promise<AppEnv> {
  const out: AppEnv = {};
  let cf: Record<string, unknown> = {};
  try {
    const { getCloudflareContext } = await import("@opennextjs/cloudflare");
    cf = (getCloudflareContext().env ?? {}) as Record<string, unknown>;
  } catch {
    /* not running inside the Worker / dev context */
  }
  for (const k of KEYS) {
    const v = (cf[k] as string | undefined) ?? process.env[k];
    if (typeof v === "string" && v !== "") out[k] = v;
  }
  return out;
}
