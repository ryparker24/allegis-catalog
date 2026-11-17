import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { buildLabelsPanel } from "@/lib/labelinfo";

export const dynamic = "force-dynamic";

/** GET: the Labels panel (item 3). Read-only. Entity and portco meanings come from ref through the app views. */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "labels" });
  if (!g.ok) return g.response;
  const D = db(env);
  const [ent, pco] = await Promise.all([
    D.rows<{ entity_code: string; display_name: string }>("SELECT entity_code, display_name FROM app.v_entity"),
    D.rows<{ portco_code: string; display_name: string }>("SELECT portco_code, display_name FROM app.v_portco"),
  ]);
  const labels = buildLabelsPanel({
    entity: new Map(ent.map((r) => [r.entity_code, r.display_name])),
    portco: new Map(pco.map((r) => [r.portco_code, r.display_name])),
  });
  return json({ labels }, 200, { "cache-control": "private, max-age=300" });
}
