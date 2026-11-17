import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";

export const dynamic = "force-dynamic";

/** Sidebar badge: open Review-queue count (DB only; the queue page itself live-checks its rows). */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "nav" });
  if (!g.ok) return g.response;
  const r = await db(env).rows<{ open_total: number }>("SELECT open_total FROM app.v_review_counts");
  return json({ reviewOpen: Number(r[0]?.open_total ?? 0) });
}
