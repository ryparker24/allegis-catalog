import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { FILE_ID_RE } from "@/lib/google";
import { liveWritable } from "@/lib/editflow";
import { logEvent } from "@/lib/log";

export const dynamic = "force-dynamic";

/**
 * GET /api/party?file_id=<id>  -> the roster (codes + display names, app.v_party) of THAT document's entities only,
 * for the Subject pickers. CISO review: write scope (only the edit forms use it) and the user must be able to open and
 * label the file (live check), so the roster can't be pulled wholesale. Names are never logged.
 */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "party", write: true });
  if (!g.ok) return g.response;
  const fileId = new URL(req.url).searchParams.get("file_id") ?? "";
  if (!FILE_ID_RE.test(fileId)) return json({ error: "bad_file_id" }, 400);
  const D = db(env);
  const f = await D.rows<{ entities: string[]; issuing_entity: string | null }>("SELECT entities, issuing_entity FROM app.v_find_x WHERE file_id = $1", [fileId]);
  if (!f.length) return json({ error: "no_access" }, 403);
  const acc = await liveWritable(g.session.at, [fileId]);
  if (acc.expired) return json({ error: "signin_required", login: "/api/auth/login" }, 401);
  if (!acc.ok.length) return json({ error: "no_access" }, 403);
  const ents = [...new Set([...(f[0].entities ?? []), ...(f[0].issuing_entity ? [f[0].issuing_entity] : [])])];
  const rows = await D.rows<{ entity_code: string; partner_code: string; display_name: string; interest_kind: string; is_company_gp: boolean }>(
    `SELECT entity_code, partner_code, display_name, interest_kind, is_company_gp FROM app.v_party
     WHERE entity_code = ANY($1::text[]) ORDER BY entity_code, partner_code LIMIT 500`, [ents]);
  logEvent("party_read", { file_id: fileId, count: rows.length });
  return json({ parties: rows });
}
