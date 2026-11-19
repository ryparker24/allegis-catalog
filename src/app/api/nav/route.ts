import { getEnv } from "@/lib/env";
import { json, requireUser } from "@/lib/guard";
import { db } from "@/lib/db";

export const dynamic = "force-dynamic";

/** Sidebar badge: open Review-queue count (DB only; the queue page itself live-checks its rows) + the nightly run health. */
export async function GET(req: Request) {
  const env = await getEnv();
  const g = await requireUser(req, env, { route: "nav" });
  if (!g.ok) return g.response;
  const D = db(env);
  const r = await D.rows<{ open_total: number }>("SELECT open_total FROM app.v_review_counts");
  // CAT-WO-03.1: the nightly run's health for the shell banner (failed, or no successful run in 36 hours)
  let nightly: { status: string; failed_step: string | null; started_at: string | null; last_ok_at: string | null } | null = null;
  try {
    const n = await D.rows<{ status: string; failed_step: string | null; started_at: string | null; last_ok_at: string | null }>(
      "SELECT status, failed_step, started_at::text, last_ok_at::text FROM app.v_nightly_status");
    nightly = n[0] ?? { status: "never", failed_step: null, started_at: null, last_ok_at: null };
  } catch { nightly = null; }                          // view not there yet: no banner
  return json({ reviewOpen: Number(r[0]?.open_total ?? 0), nightly });
}
