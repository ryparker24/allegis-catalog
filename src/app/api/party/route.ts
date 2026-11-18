import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";

export const dynamic = "force-dynamic";
const ENT = /^[A-Za-z0-9()_ -]{1,40}$/;
const CODE = /^(LP|GM|GPM)-[0-9]{2,6}(-[A-Z]{1,4})?$/;

/**
 * GET /api/party?entity=A&entity=B | ?code=LP-0001&code=...  -> roster codes with display names, from app.v_party only.
 * Names are for the screen (pickers, "name beside the code"); this response is no-store and never logged.
 */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "party" });
  if (!g.ok) return g.response;
  const u = new URL(req.url);
  const ents = u.searchParams.getAll("entity").filter((e) => ENT.test(e)).slice(0, 20);
  const codes = u.searchParams.getAll("code").map((c) => c.toUpperCase()).filter((c) => CODE.test(c)).slice(0, 500);
  if (!ents.length && !codes.length) return json({ parties: [] });
  const rows = await db(env).rows<{ entity_code: string; partner_code: string; display_name: string; interest_kind: string; is_company_gp: boolean }>(
    `SELECT entity_code, partner_code, display_name, interest_kind, is_company_gp FROM app.v_party
     WHERE ($1::text[] = '{}' OR entity_code = ANY($1::text[])) AND ($2::text[] = '{}' OR partner_code = ANY($2::text[]))
     ORDER BY entity_code, partner_code LIMIT 2000`, [ents, codes]);
  return json({ parties: rows });
}
