import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { editOne } from "@/lib/editflow";
import { editFields } from "@/lib/edit";
import { canWrite } from "@/lib/session";

export const dynamic = "force-dynamic";

/** POST /api/edit {file_id, set:{field: value}} -> writes the R-023 labels on one file as the user (item 8). */
export async function POST(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "edit", write: true, next: "/" });
  if (!g.ok) return g.response;
  const body = await req.json().catch(() => null);
  const r = await editOne(body, { session: g.session, db: db(env), source: (body as { source?: string } | null)?.source === "review_edit" ? "review_edit" : "find_single" });
  return json(r.body, r.status);
}

/** GET /api/edit -> the editable fields, their choices (code + meaning) and whether each label is published. Read-only. */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "edit" });
  if (!g.ok) return g.response;
  const D = db(env);
  const [ent, pco] = await Promise.all([
    D.rows<{ entity_code: string; display_name: string }>("SELECT entity_code, display_name FROM app.v_entity"),
    D.rows<{ portco_code: string; display_name: string }>("SELECT portco_code, display_name FROM app.v_portco"),
  ]);
  const fields = editFields({ entity: new Map(ent.map((r) => [r.entity_code, r.display_name])), portco: new Map(pco.map((r) => [r.portco_code, r.display_name])) });
  return json({ fields, canWrite: canWrite(g.session) }, 200, { "cache-control": "private, max-age=300" });
}
