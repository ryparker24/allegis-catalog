import { neon } from "@neondatabase/serverless";
import type { AppEnv } from "./env";

/** catalog_app role only (CATALOG_APP_DB_URL, a Worker secret). It can read app views and nothing in cat/ref/ops. */
export function db(env: AppEnv) {
  if (!env.CATALOG_APP_DB_URL) throw new Error("CATALOG_APP_DB_URL not set");
  const sql = neon(env.CATALOG_APP_DB_URL);
  return {
    async rows<T = Record<string, unknown>>(text: string, params: unknown[] = []): Promise<T[]> {
      return (await sql.query(text, params)) as T[];
    },
    async exec(text: string, params: unknown[] = []): Promise<number> {
      const r = (await sql.query(text, params, { fullResults: true })) as { rowCount: number | null };
      return r.rowCount ?? 0;
    },
  };
}
export type Db = ReturnType<typeof db>;
