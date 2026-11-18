import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { accessFor, REQ_KEY, shownDoc } from "@/lib/checklists";

export const dynamic = "force-dynamic";
type Cand = { document_id: number; file_id: string; kind: string; stage: string | null; status: string | null; date: string | null; satisfying: boolean; partner_conf: string | null; is_primary: boolean };

/** GET /api/checklists/candidates?key=<req_key> -> the row's candidates (runners-up included), each live-checked as the user. */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "checklists_candidates" });
  if (!g.ok) return g.response;
  const key = new URL(req.url).searchParams.get("key") ?? "";
  if (!REQ_KEY.test(key)) return json({ error: "bad_input", reason: "key" }, 400);
  const D = db(env);
  const r = await D.rows<{ candidates: Cand[] }>("SELECT candidates FROM app.v_requirement WHERE req_key = $1", [key]);
  if (!r.length) return json({ error: "not_found" }, 404);
  const cands = (r[0].candidates ?? []).slice(0, 10);
  // still in the app's scope (labelled, not secret) - a candidate that left it is not shown at all
  const inScope = new Set((await D.rows<{ file_id: string }>("SELECT file_id FROM app.v_find_x WHERE file_id = ANY($1::text[])", [cands.map((c) => c.file_id)])).map((x) => x.file_id));
  const kept = cands.filter((c) => inScope.has(c.file_id));
  const acc = await accessFor(g.session.at, kept.map((c) => c.file_id));
  if (acc.expired) return json({ error: "signin_required", login: "/api/auth/login" }, 401);
  return json({
    candidates: kept.map(({ file_id, document_id: _d, ...c }) => ({ ...c, doc: shownDoc(file_id, acc.map.get(file_id)) })),
    not_in_scope: cands.length - kept.length,
  });
}
