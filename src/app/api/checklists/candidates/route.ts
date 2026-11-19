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
  const scope = await D.rows<{ file_id: string; location: string | null; location_folder_id: string | null; other_locations: number }>(
    "SELECT file_id, location, location_folder_id, other_locations FROM app.v_find_x WHERE file_id = ANY($1::text[])", [cands.map((c) => c.file_id)]);
  const inScope = new Map(scope.map((x) => [x.file_id, x]));
  const kept = cands.filter((c) => inScope.has(c.file_id));
  const acc = await accessFor(g.session.at, kept.map((c) => c.file_id));
  if (acc.expired) return json({ error: "signin_required", login: "/api/auth/login" }, 401);
  return json({
    candidates: kept.map(({ file_id, document_id: _d, ...c }) => {
      // CAT-WO-03.1 Location: like the name, only when the live check as the user passed
      const ok = acc.map.get(file_id)?.state === "ok";
      const l = inScope.get(file_id)!;
      return { ...c, doc: shownDoc(file_id, acc.map.get(file_id)),
        location: ok ? l.location : null, location_folder_id: ok ? l.location_folder_id : null, other_locations: ok ? l.other_locations : 0 };
    }),
    not_in_scope: cands.length - kept.length,
  });
}
