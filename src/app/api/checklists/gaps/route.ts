import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";
import { gapsQuery, SpecError } from "@/lib/checklists";

export const dynamic = "force-dynamic";

/** GET /api/checklists/gaps?rule=AUDITED-FS|K1-SET|PCAP-Q[&entity=][&cadence=] -> entity x period cells, counts by result (codes only). */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "checklists_gaps" });
  if (!g.ok) return g.response;
  const u = new URL(req.url);
  let q;
  try { q = gapsQuery(u.searchParams.get("rule") ?? "", u.searchParams.get("entity") || null, u.searchParams.get("cadence") || null); }
  catch (e) { return json({ error: "bad_spec", reason: e instanceof SpecError ? e.message : "invalid" }, 400); }
  const cells = await db(env).rows<{ entity_code: string; cadence: string | null; fiscal_year: number | null; fiscal_quarter: number | null; result: string; n: number }>(q.sql, q.params);
  return json({ cells });
}
